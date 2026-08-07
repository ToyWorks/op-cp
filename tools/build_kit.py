"""Render the drum kit and voices on the host into lib/opcp_kit.bin.

    make kit

The synthesis itself is far too slow to run on the board — measured at ~5.4 s
for the whole kit, which is not an acceptable boot cost. The noise source is a
seeded xorshift precisely so this is reproducible: the same source always
produces the same blob, so the shipped .bin is a build artifact rather than a
recording someone has to keep safe.

Sizes are printed because they are the binding constraint. There is ~66 KB free
on the device with the app running, and the blob has to live in RAM for
playRaw. Anything approaching 40 KB should be trimmed in DRUM_SPECS.
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "lib"))

import opcp_synth as SY          # noqa: E402

OUT = os.path.join(_ROOT, "lib", "opcp_kit.bin")

print("rendering at %d Hz, signed 16-bit" % SY.RATE)
entries = SY.render_all()

total = 0
for name, buf in entries:
    n = len(buf)
    total += n * 2
    print("  %-4s %5d samples  %5d bytes  %4d ms"
          % (name, n, n * 2, 1000 * n // SY.RATE))

blob = SY.pack(entries)
with open(OUT, "wb") as f:
    f.write(blob)

print("\n  samples   %6d bytes" % total)
print("  file      %6d bytes -> %s" % (len(blob), os.path.relpath(OUT, _ROOT)))
budget = 66000
print("  device has ~%d bytes free with the app running; this leaves ~%d"
      % (budget, budget - len(blob)))
if len(blob) > 40000:
    print("  WARNING: over 40 KB — trim DRUM_SPECS lengths or VOICE_MS")
