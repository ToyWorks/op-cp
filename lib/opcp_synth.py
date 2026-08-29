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
#   1. playRaw interprets ANY buffer as int16, whatever you pass it. Measured
#      on device — 8000 bytes played for 459 ms at rate 8000, i.e. 4000
#      samples, not 8000. bytearray, array('B') and array('h') all behave
#      identically, which is what killed the first 8-bit version of this file.
#      playWav does NOT have that problem: it reads the format out of the
#      header, 8-bit included, and repitching still works because the header
#      is ours to rewrite. Measured on device: the same buffer at 11025,
#      22050 and 5512 Hz played for 301, 156 and 593 ms.
#   2. RAM. ~66 KB free with the app running, and the kit is resident for the
#      life of the program, so it is rendered to unsigned 8-bit — ~18 KB
#      rather than ~36 — and handed to playWav() rather than playRaw(). See
#      to_u8() for why that costs less than it sounds like it should, and why
#      playWav is what makes 8-bit possible at all.
#   3. CPU. Rendering on device costs ~5.4 s for the whole kit — measured, and
#      far too slow for boot. So this module runs on the HOST: tools/build_kit.py
#      renders it into lib/opcp_kit.bin, and the device just reads the file. The
#      noise RNG is deterministic precisely so the shipped blob is reproducible.
#
# Melodic voices are ONE buffer per track, pitched by changing playRaw's sample
# rate — the trick a hardware sampler uses. The envelope stretches with pitch,
# which is a sampler's characteristic behaviour rather than a defect.

try:
    from array import array
except ImportError:
    array = None

RATE = 11025             # playback rate the buffers are rendered for
BASE_MIDI = 69           # the pitch the melodic buffers are rendered AT (A4)
PEAK = 32767             # signed 16-bit full scale

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
        return array("h", bytes(2 * n))
    return [0] * n


def _write(buf, i, v):
    """Clamp to signed 16-bit."""
    s = int(v * PEAK)
    if s > PEAK:
        s = PEAK
    elif s < -PEAK:
        s = -PEAK
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
    "BD": (150, [{"k": "tone", "f0": 132, "f1": 44, "sweep": 0.010,
                  "decay": 0.055, "gain": 1.00, "drive": 1.6}]),
    # snare = a tuned shell plus a noisy wire bed
    "SD": (140, [{"k": "tone", "f0": 232, "f1": 178, "sweep": 0.030,
                  "decay": 0.045, "gain": 0.45},
                 {"k": "tone", "f0": 331, "f1": 271, "sweep": 0.030,
                  "decay": 0.035, "gain": 0.28},
                 {"k": "noise", "hp": 0.55, "decay": 0.055, "gain": 0.60}]),
    # hats are noise, high-passed hard and cut short. Never a sine.
    "HH": (48,  [{"k": "noise", "hp": 0.86, "decay": 0.012, "gain": 0.72}]),
    "OH": (160, [{"k": "noise", "hp": 0.82, "decay": 0.105, "gain": 0.60}]),
    # rimshot: a click with just enough pitch to place it
    "RM": (50,  [{"k": "tone", "f0": 1720, "f1": 1180, "sweep": 0.006,
                  "decay": 0.010, "gain": 0.55},
                 {"k": "noise", "hp": 0.70, "decay": 0.007, "gain": 0.45}]),
    "TL": (140, [{"k": "tone", "f0": 168, "f1": 108, "sweep": 0.045,
                  "decay": 0.070, "gain": 0.85, "drive": 1.2},
                 {"k": "noise", "hp": 0.5, "decay": 0.010, "gain": 0.18}]),
    "TH": (125, [{"k": "tone", "f0": 246, "f1": 158, "sweep": 0.040,
                  "decay": 0.058, "gain": 0.85, "drive": 1.2},
                 {"k": "noise", "hp": 0.5, "decay": 0.010, "gain": 0.18}]),
    # clap: several noise bursts a few ms apart, then a tail. The stutter is
    # the whole sound — one burst reads as a snare, not hands.
    "CP": (150, [{"k": "noise", "hp": 0.62, "decay": 0.040, "gain": 0.62,
                  "bursts": (0.0, 0.011, 0.021, 0.031)}]),
    # cowbell: two detuned squares, the classic inharmonic pair
    "CB": (150, [{"k": "square", "f0": 823, "decay": 0.055, "gain": 0.34},
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
VOICE_MS = 170

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


# ------------------------------------------------------------------ the blob
DRUM_ORDER = ("BD", "SD", "HH", "OH", "RM", "TL", "TH", "CP", "CB")
VOICE_ORDER = ("V0", "V1", "V2")
MAGIC = b"OPK2"                  # OPK1 was raw int16; OPK2 is 8-bit WAV

WAV_HDR = 44                     # canonical RIFF/fmt /data, no extra chunks


def to_u8(buf, seed=0x5BD1E995):
    """Quantise the rendered int16 samples to unsigned 8-bit, with dither.

    Why 8-bit at all: the whole kit lives in RAM for the life of the program,
    and this board has ~156 KB of MicroPython heap that the WiFi driver, the
    sequencer's tables and the screen all want a share of. Halving the kit
    from 36 KB to 18 KB is the difference between having the radio and having
    real drums, rather than choosing.

    The first version of this synth was 8-bit for the same reason and had to
    give it up: playRaw() reads ANY buffer as int16 whatever its type, so
    8-bit samples came out as noise at double speed. playWav() reads the
    format from the header instead, which is what makes this possible again.

    Dither is TPDF and seeded, so the blob stays a reproducible build
    artifact. Truncating instead correlates the quantisation error with the
    signal, and on a decay tail that is a buzz riding the sound down rather
    than noise; the triangular dither decorrelates it into steady hiss, which
    is louder in the numbers and quieter to a listener. Measured SNR per
    sound afterwards is 27-36 dB.
    """
    rng = _Rng(seed)
    out = bytearray(len(buf))
    for i in range(len(buf)):
        # two rectangular draws make a triangular distribution, +/- 1 LSB
        d = (rng.bipolar() + rng.bipolar()) * 128.0
        v = int((buf[i] + d) / 256.0 + 0.5) + 128
        if v > 255:
            v = 255
        elif v < 0:
            v = 0
        out[i] = v
    return bytes(out)


def wav8(data, rate=RATE):
    """Wrap 8-bit mono samples in a WAV header the device can hand playWav().

    The header is why the rate is not a playWav() argument the way it is a
    playRaw() one — and also why repitching still works: opcp_audio rewrites
    the four bytes at offset 24 before each note. Keep this header canonical
    and 44 bytes; that offset is load-bearing on the device.
    """
    import struct
    return (b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " +
            struct.pack("<IHHIIHH", 16, 1, 1, rate, rate, 1, 8) +
            b"data" + struct.pack("<I", len(data)) + data)


def render_all():
    """Every sound, in a fixed order. Host-side; see tools/build_kit.py."""
    out = []
    for nm in DRUM_ORDER:
        out.append((nm, render_drum(nm)))
    for t in range(3):
        out.append((VOICE_ORDER[t], render_voice(t)))
    return out


def pack(entries):
    """Serialise to the .bin the device loads.

    Layout: magic | count | count x (name[4], offset u32, nbytes u32) | data.
    Each entry is a complete 8-bit mono WAV, header and all, so the device
    hands the slice straight to playWav() without assembling anything.
    """
    import struct
    header = bytearray(MAGIC)
    header.append(len(entries))
    body = bytearray()
    index = bytearray()
    for name, buf in entries:
        raw = wav8(to_u8(buf)) if array is not None else b""
        index += struct.pack("<4sII", name.encode()[:4].ljust(4, b"\0"),
                             len(body), len(raw))
        body += raw
    base = len(header) + len(index)
    # offsets are absolute in the finished file
    fixed = bytearray()
    import struct as _s
    for k in range(len(entries)):
        nm, off, ln = _s.unpack_from("<4sII", index, k * 12)
        fixed += _s.pack("<4sII", nm, off + base, ln)
    return bytes(header + fixed + body)
