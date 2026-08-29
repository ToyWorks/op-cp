"""Render the drum kit and voices on the host into lib/opcp_kit.bin.

    make kit

The synthesis itself is far too slow to run on the board — measured at ~5.4 s
for the whole kit, which is not an acceptable boot cost. The noise source is a
seeded xorshift precisely so this is reproducible: the same source always
produces the same blob, so the shipped .bin is a build artifact rather than a
recording someone has to keep safe.

Sizes are printed because they are the binding constraint. There is ~66 KB free
on the device with the app running, the kit is resident for the life of the
program, and it is competing with the WiFi driver that ESP-NOW needs. That is
why the samples are 8-bit: see opcp_synth.to_u8(). Anything approaching 24 KB
should be trimmed in DRUM_SPECS.
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "lib"))

import opcp_synth as SY          # noqa: E402

OUT = os.path.join(_ROOT, "lib", "opcp_kit.bin")

print("rendering at %d Hz, unsigned 8-bit WAV" % SY.RATE)
entries = SY.render_all()

total = 0
for name, buf in entries:
    n = len(buf)
    total += n + SY.WAV_HDR
    print("  %-4s %5d samples  %5d bytes  %4d ms"
          % (name, n, n + SY.WAV_HDR, 1000 * n // SY.RATE))

blob = SY.pack(entries)
with open(OUT, "wb") as f:
    f.write(blob)

print("\n  sounds    %6d bytes (was %d as int16)" % (total, total * 2))
print("  file      %6d bytes -> %s" % (len(blob), os.path.relpath(OUT, _ROOT)))
budget = 66000
print("  device has ~%d bytes free with the app running; this leaves ~%d"
      % (budget, budget - len(blob)))
if len(blob) > 24000:
    print("  WARNING: over 24 KB — trim DRUM_SPECS lengths or VOICE_MS")
