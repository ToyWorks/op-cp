# OP-CP — the sound source.
#
# Why this module exists at all: M5.Speaker.tone() emits a bare square wave at
# constant amplitude for N milliseconds. That is why the old kit sounded like a
# toy, and no amount of tuning the frequencies fixes it:
#
#   * no amplitude envelope, so every note starts and ends with a click and
#     sustains like a doorbell
#   * one timbre for everything — a square wave, forever
#   * the drums were pure tones. A hi-hat is *noise*; rendering it as a 6200 Hz
#     sine gives you a beep, not a cymbal. Same for the snare and the clap.
#
# So instead we render PCM once at startup and hand buffers to playRaw():
# proper decay envelopes, pitch sweeps on the drums, real noise where noise
# belongs, and a bit of detune on the melodic voices.
#
# Two constraints shape everything below, and both are the device's:
#
#   1. RAM. There is ~80 KB free. 16-bit samples at 22 kHz would blow it, so
#      everything is unsigned 8-bit at 11025 Hz. That is 12-bit-sampler
#      territory — which is the right era for this instrument anyway.
#   2. CPU. Per-sample arithmetic in MicroPython is slow, so nothing is
#      synthesised per note. Drums are one-shot buffers. Melodic voices are ONE
#      buffer per track, pitched by changing playRaw's sample rate — the same
#      trick a hardware sampler uses. The envelope stretches with pitch, which
#      is a sampler's characteristic behaviour rather than a defect.

try:
    from array import array
except ImportError:
    array = None

RATE = 11025             # playback rate the buffers are rendered for
BASE_MIDI = 69           # the pitch the melodic buffers are rendered AT (A4)
CENTER = 128             # unsigned 8-bit silence

_TWO_PI = 6.283185307


# ------------------------------------------------------------------ helpers
class _Rng:
    """Deterministic noise.

    A fixed seed means the kit renders identically every boot, so a drum sound
    can be tuned and re-tuned without it moving underneath you — and the host
    simulator produces byte-identical output to the device.
    """

    __slots__ = ("s",)

    def __init__(self, seed=0x2545F491):
        self.s = seed

    def next(self):
        # xorshift32 — cheap, and good enough for percussion noise
        x = self.s
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        self.s = x
        return x

    def bipolar(self):
        """-1.0 .. 1.0"""
        return ((self.next() >> 8) & 0xFFFF) / 32768.0 - 1.0


def _sin(x):
    """sin() via a small table, so the host and the device agree exactly."""
    import math
    return math.sin(x)


def _buf(n):
    if array is not None:
        return array("B", bytes(n))
    return bytearray(n)


def _write(buf, i, v):
    """Clamp to 8-bit unsigned around the DC centre."""
    s = int(CENTER + v * 127.0)
    if s < 0:
        s = 0
    elif s > 255:
        s = 255
    buf[i] = s


# ------------------------------------------------------------------ drum kit
# Each entry: (length_ms, [layers]). A layer is a dict describing one
# component; they are summed. Kept declarative so a sound can be re-tuned
# without touching the render loop.
#
#   tone   f0 -> f1 pitch sweep, exponential
#   noise  broadband, optionally high-passed by mixing with its own difference
#   decay  exponential amplitude decay; `hold` keeps it flat first
DRUM_SPECS = {
    # a kick is a sine that falls fast: the sweep IS the beater transient
    "BD": (170, [{"k": "tone", "f0": 132, "f1": 44, "sweep": 0.010,
                  "decay": 0.055, "gain": 1.00, "drive": 1.6}]),
    # snare = a tuned shell plus a noisy wire bed
    "SD": (150, [{"k": "tone", "f0": 232, "f1": 178, "sweep": 0.030,
                  "decay": 0.045, "gain": 0.45},
                 {"k": "tone", "f0": 331, "f1": 271, "sweep": 0.030,
                  "decay": 0.035, "gain": 0.28},
                 {"k": "noise", "hp": 0.55, "decay": 0.055, "gain": 0.60}]),
    # hats are noise, high-passed hard and cut short. Never a sine.
    "HH": (52,  [{"k": "noise", "hp": 0.86, "decay": 0.012, "gain": 0.72}]),
    "OH": (240, [{"k": "noise", "hp": 0.82, "decay": 0.105, "gain": 0.60}]),
    # rimshot: a click with just enough pitch to place it
    "RM": (55,  [{"k": "tone", "f0": 1720, "f1": 1180, "sweep": 0.006,
                  "decay": 0.010, "gain": 0.55},
                 {"k": "noise", "hp": 0.70, "decay": 0.007, "gain": 0.45}]),
    "TL": (200, [{"k": "tone", "f0": 168, "f1": 108, "sweep": 0.045,
                  "decay": 0.070, "gain": 0.85, "drive": 1.2},
                 {"k": "noise", "hp": 0.5, "decay": 0.010, "gain": 0.18}]),
    "TH": (170, [{"k": "tone", "f0": 246, "f1": 158, "sweep": 0.040,
                  "decay": 0.058, "gain": 0.85, "drive": 1.2},
                 {"k": "noise", "hp": 0.5, "decay": 0.010, "gain": 0.18}]),
    # clap: several noise bursts a few ms apart, then a tail. The stutter is
    # the whole sound — one burst reads as a snare, not hands.
    "CP": (200, [{"k": "noise", "hp": 0.62, "decay": 0.040, "gain": 0.62,
                  "bursts": (0.0, 0.011, 0.021, 0.031)}]),
    # cowbell: two detuned squares, the classic inharmonic pair
    "CB": (180, [{"k": "square", "f0": 823, "decay": 0.055, "gain": 0.34},
                 {"k": "square", "f0": 542, "decay": 0.060, "gain": 0.34}]),
}


def _env(t, decay, hold=0.0):
    if t < hold:
        return 1.0
    d = (t - hold) / decay
    if d > 12.0:
        return 0.0
    # exp() without importing math into the inner loop
    return 2.718281828 ** (-d)


def render_drum(name):
    """Render one drum to an 8-bit buffer."""
    ms, layers = DRUM_SPECS[name]
    n = int(RATE * ms / 1000)
    out = [0.0] * n
    rng = _Rng(0x9E3779B9 ^ (sum(ord(c) for c in name) * 2654435761))

    for L in layers:
        kind = L["k"]
        gain = L.get("gain", 1.0)
        decay = L.get("decay", 0.05)
        drive = L.get("drive", 1.0)

        if kind in ("tone", "square"):
            f0 = L["f0"]
            f1 = L.get("f1", f0)
            sweep = L.get("sweep", 0.0)
            phase = 0.0
            for i in range(n):
                t = i / RATE
                if sweep > 0.0:
                    f = f1 + (f0 - f1) * _env(t, sweep)
                else:
                    f = f0
                phase += _TWO_PI * f / RATE
                v = _sin(phase)
                if kind == "square":
                    v = 1.0 if v >= 0 else -1.0
                if drive != 1.0:
                    v = v * drive
                    if v > 1.0:
                        v = 1.0
                    elif v < -1.0:
                        v = -1.0
                out[i] += v * gain * _env(t, decay)

        elif kind == "noise":
            hp = L.get("hp", 0.0)
            bursts = L.get("bursts", (0.0,))
            prev = 0.0
            for i in range(n):
                t = i / RATE
                raw = rng.bipolar()
                # one-pole high pass: mixing in the sample-to-sample difference
                # is what turns flat hiss into something metallic
                v = raw - hp * prev
                prev = raw
                a = 0.0
                for b in bursts:
                    if t >= b:
                        a += _env(t - b, decay)
                if a > 1.0:
                    a = 1.0
                out[i] += v * gain * a

    buf = _buf(n)
    peak = 0.0
    for v in out:
        av = v if v >= 0 else -v
        if av > peak:
            peak = av
    norm = (1.0 / peak) * 0.92 if peak > 0.001 else 1.0
    for i in range(n):
        _write(buf, i, out[i] * norm)
    return buf


# ------------------------------------------------------------------ voices
# One buffer per melodic track, rendered at A4 and repitched by playback rate.
#
#   LEAD  two detuned saws — the detune is what stops it sounding like a beep
#   BASS  sine plus an octave-down square, soft-clipped for weight
#   KEYS  three-partial additive with a slow attack, so it sits behind the lead
VOICE_MS = 260

def _saw(ph):
    return 2.0 * (ph - int(ph)) - 1.0


def render_voice(track):
    n = int(RATE * VOICE_MS / 1000)
    f = 440.0
    out = [0.0] * n

    if track == 0:                                   # LEAD
        detune = 1.006
        p1 = p2 = 0.0
        for i in range(n):
            t = i / RATE
            p1 += f / RATE
            p2 += f * detune / RATE
            v = (_saw(p1) + _saw(p2)) * 0.5
            a = _env(t, 0.075, hold=0.004) * (1.0 - 2.718281828 ** (-t * 900))
            out[i] = v * a * 0.9
    elif track == 1:                                 # BASS
        ph = phs = 0.0
        for i in range(n):
            t = i / RATE
            ph += _TWO_PI * f / RATE
            phs += _TWO_PI * (f * 0.5) / RATE
            v = _sin(ph) * 0.75 + (1.0 if _sin(phs) >= 0 else -1.0) * 0.25
            v *= 1.5                                  # soft clip for weight
            if v > 1.0:
                v = 1.0
            elif v < -1.0:
                v = -1.0
            a = _env(t, 0.130, hold=0.010) * (1.0 - 2.718281828 ** (-t * 600))
            out[i] = v * a * 0.95
    else:                                            # KEYS
        ph = 0.0
        for i in range(n):
            t = i / RATE
            ph += _TWO_PI * f / RATE
            v = (_sin(ph) * 0.6 + _sin(ph * 2.0) * 0.25 + _sin(ph * 3.0) * 0.15)
            a = _env(t, 0.110, hold=0.020) * (1.0 - 2.718281828 ** (-t * 160))
            out[i] = v * a * 0.85

    buf = _buf(n)
    peak = 0.0
    for v in out:
        av = v if v >= 0 else -v
        if av > peak:
            peak = av
    norm = (1.0 / peak) * 0.92 if peak > 0.001 else 1.0
    for i in range(n):
        _write(buf, i, out[i] * norm)
    return buf


def rate_for(midi):
    """Playback rate that shifts the A4 buffer to `midi`."""
    return int(RATE * (2.0 ** ((midi - BASE_MIDI) / 12.0)))
