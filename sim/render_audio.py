"""Render OP-CP's audio to WAV files on the host, so it can be listened to.

    make audio        # then play sim/audio/*.wav

The visual loop (`make shots`) let the UI be seen without flashing. This is the
same idea for sound: it runs the real synthesis code from lib/opcp_synth.py and
mixes it exactly the way the device will — same buffers, same sample rate, same
repitch-by-playback-rate trick — then writes:

    old-kit.wav     what M5.Speaker.tone() produces: bare square waves
    new-kit.wav     the same two bars through the PCM synth
    drums.wav       every drum one-shot in turn, so each can be judged alone
    voices.wav      a scale on each melodic voice

`old-kit.wav` is there on purpose. "Does this sound better" is not answerable in
the abstract, only against what it replaces.
"""

import math
import os
import struct
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "lib"))

import opcp_conf as C          # noqa: E402
import opcp_synth as SY        # noqa: E402

OUT_RATE = 22050
OUT = os.path.join(_HERE, "audio")
os.makedirs(OUT, exist_ok=True)


class Mix:
    """A mono float bus, long enough for the whole piece."""

    def __init__(self, seconds):
        self.n = int(OUT_RATE * seconds)
        self.buf = [0.0] * self.n

    def add_pcm(self, pcm, rate, at_ms, gain=1.0):
        """Play a signed 16-bit buffer at `rate`, exactly as playRaw would."""
        start = int(OUT_RATE * at_ms / 1000)
        dur = len(pcm) / rate
        count = int(dur * OUT_RATE)
        for k in range(count):
            j = start + k
            if j >= self.n:
                break
            src = int(k * rate / OUT_RATE)
            if src >= len(pcm):
                break
            self.buf[j] += (pcm[src] / 32768.0) * gain

    def add_square(self, freq, ms, at_ms, gain=1.0):
        """Emulate M5.Speaker.tone(): a square wave, flat, no envelope."""
        start = int(OUT_RATE * at_ms / 1000)
        count = int(OUT_RATE * ms / 1000)
        for k in range(count):
            j = start + k
            if j >= self.n:
                break
            ph = (k * freq / OUT_RATE) % 1.0
            self.buf[j] += (1.0 if ph < 0.5 else -1.0) * gain

    def stats(self):
        peak = 0.0
        sq = 0.0
        clipped = 0
        for v in self.buf:
            a = abs(v)
            if a > peak:
                peak = a
            if a > 1.0:
                clipped += 1
            sq += v * v
        rms = math.sqrt(sq / max(1, self.n))
        return peak, rms, clipped

    def write(self, name, headroom=0.89):
        peak, rms, clipped = self.stats()
        norm = (headroom / peak) if peak > 0.001 else 1.0
        path = os.path.join(OUT, name)
        frames = bytearray()
        for v in self.buf:
            s = int(v * norm * 32767)
            if s > 32767:
                s = 32767
            elif s < -32768:
                s = -32768
            frames += struct.pack("<h", s)
        with open(path, "wb") as f:
            f.write(b"RIFF" + struct.pack("<I", 36 + len(frames)) + b"WAVE")
            f.write(b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, OUT_RATE,
                                          OUT_RATE * 2, 2, 16))
            f.write(b"data" + struct.pack("<I", len(frames)) + bytes(frames))
        print("  %-14s %5.1fs  peak %.2f  rms %.3f  clipped %d samples"
              % (name, self.n / OUT_RATE, peak, rms, clipped))
        return path


# ------------------------------------------------------------------ the kit
print("rendering synth buffers...")
DRUMS = {}
for nm in C.DRUMS:
    DRUMS[nm[0]] = SY.render_drum(nm[0])
    print("  drum %-3s %5d samples (%d ms, %d bytes)"
          % (nm[0], len(DRUMS[nm[0]]), 1000 * len(DRUMS[nm[0]]) // SY.RATE,
             len(DRUMS[nm[0]]) * 2))
VOICES = [SY.render_voice(t) for t in range(3)]
for t in range(3):
    print("  voice %-5s %5d samples" % (C.TRACK_NAMES[t], len(VOICES[t])))
total = (sum(len(b) for b in DRUMS.values()) + sum(len(b) for b in VOICES)) * 2
print("  total buffer RAM: %d bytes (int16)" % total)


# ------------------------------------------------------------------ a piece
N = None
PATTERN = {
    0: [0, N, 3, N, 5, N, 7, N, 0, N, 3, N, 7, N, 5, N],
    1: [0, N, N, N, 5, N, N, N, 3, N, N, N, 7, N, N, N],
    2: [7, N, N, 5, N, N, 3, N, 0, N, N, 5, N, N, 7, N],
    3: [0, 2, 1, 2, 0, 2, 1, 2, 0, 2, 1, 8, 0, 2, 1, 4],
}
BPM = 112
OCT = [0, -1, 0, 0]
ROOT = 57
BARS = 2


def step_times():
    """Sixteenth grid with the same swing the device applies."""
    base = 60000.0 / (BPM * 4)
    t = 0.0
    for bar in range(BARS):
        for i in range(C.STEPS):
            yield bar * C.STEPS + i, i, t
            iv = base * ((1.0 - C.SWING_PCT / 100.0) if i % 2
                         else (1.0 + C.SWING_PCT / 100.0))
            t += iv


DUR = BARS * C.STEPS * (60000.0 / (BPM * 4)) / 1000 + 1.0

# One PCM buffer per track means one mixer channel per track — the old engine
# needed up to seven because each drum layer was its own tone(). Four channels
# share the budget, exactly as opcp_audio.balance() does on the device: a lone
# note gets the whole headroom, a dense step gets divided down. Modelling that
# here is what makes this preview match the hardware instead of flattering it.
TRIM = (1.0, 1.0, 0.80, 1.0)

print("\nnew kit (PCM synth):")
new = Mix(DUR)
for _, i, t in step_times():
    live = [tr for tr in range(4) if PATTERN[tr][i] is not None]
    if not live:
        continue
    total = sum(TRIM[tr] for tr in live)
    for tr in live:
        g = TRIM[tr] / total
        v = PATTERN[tr][i]
        if tr == 3:
            nm = C.DRUMS[v % len(C.DRUMS)][0]
            new.add_pcm(DRUMS[nm], SY.RATE, t, g)
        else:
            midi = ROOT + v + 12 * OCT[tr]
            new.add_pcm(VOICES[tr], SY.rate_for(midi), t, g)
new.write("new-kit.wav")

print("\nold kit (M5.Speaker.tone, for comparison):")
old = Mix(DUR)
gate = max(30, int(60000 / (BPM * 4) * 0.7))
for _, i, t in step_times():
    for tr in range(4):
        v = PATTERN[tr][i]
        if v is None:
            continue
        if tr == 3:
            for f, ms in C.DRUMS[v % len(C.DRUMS)][1]:
                old.add_square(f, ms, t, 0.5)
        else:
            midi = ROOT + v + 12 * OCT[tr]
            hz = 440.0 * (2.0 ** ((midi - 69) / 12.0))
            old.add_square(hz, gate if tr != 1 else int(gate * 1.4), t, 0.5)
old.write("old-kit.wav")

print("\nisolated:")
kit = Mix(len(C.DRUMS) * 0.45 + 0.5)
for k, nm in enumerate(C.DRUMS):
    kit.add_pcm(DRUMS[nm[0]], SY.RATE, k * 450, 0.9)
kit.write("drums.wav")

vo = Mix(3.6)
step = 0
for tr in range(3):
    for semi in (0, 4, 7, 12):
        vo.add_pcm(VOICES[tr], SY.rate_for(ROOT + semi + 12 * OCT[tr]),
                   step * 280, 0.8)
        step += 1
vo.write("voices.wav")

print("\nwrote to %s" % OUT)
