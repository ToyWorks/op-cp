"""Render the dance face's states to PNGs so the design can be looked at.

    make shots                 # the CoreS3's 320x240
    make shots BOARD=cube      # the cube's 240x240
                               # then open sim/shots/

Runs the real scd_face draw functions against the Pillow-backed M5 stub with
device-measured font metrics. Geometry and colour quantisation are exact;
motion, panel gamma and the servos are hardware questions.

Usage: python3 sim/shoot.py [board] [scale]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)
sys.path.insert(0, os.path.join(_root, "lib"))

import m5stub                                        # noqa: E402

BOARD = sys.argv[1] if len(sys.argv) > 1 else "cores3"
SCALE = int(sys.argv[2]) if len(sys.argv) > 2 else 2
m5 = m5stub.install(BOARD)

from PIL import Image                                # noqa: E402

import scd_conf as C                                 # noqa: E402
import scd_face as F                                 # noqa: E402
from scd_state import S                              # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots", BOARD)
os.makedirs(OUT, exist_ok=True)

import M5                                            # noqa: E402

M5.begin()
F.layout()
M5.Lcd.fillScreen(C.BG)

shots = []


def snap(name):
    img = m5.Lcd.img.copy()
    big = img.resize((img.width * SCALE, img.height * SCALE), Image.NEAREST)
    path = os.path.join(OUT, name + ".png")
    big.save(path)
    shots.append((name, img))
    print("  %-14s %dx%d -> %s" % (name, img.width, img.height, path))


def state(groove, level, hit, gaze=0, blink=False, bpm=0, dx=0, inten=2,
          palette=0, naming=False):
    S.palette = palette
    S.palette_name, S.accent, S.accent_deep = C.PALETTE[palette]
    S.palette_shown = 1 << 60 if naming else 0
    S.grooving = groove
    S.level = level
    S.hit = hit
    S.hit_intensity = inten
    S.gaze = gaze
    S.side = 1 if dx >= 0 else -1
    S.dx = dx
    S.blink = 1 if blink else 0
    S.next_blink = 1 << 60          # keep draw() from scheduling its own
    S.bpm = bpm
    F._last.clear()
    M5.Lcd.fillScreen(C.BG)
    F.draw(0)


print("rendering %s %dx%d at %dx" % (BOARD, F.W, F.H, SCALE))

state(False, 0, 0)
snap("idle")

state(False, 0, 0, blink=True)
snap("idle-blink")

state(False, 0, 0, gaze=-8)
snap("idle-glance")

state(True, 70, 0, bpm=112)
snap("groove-low")

state(True, 200, 0, bpm=128, dx=14)
snap("groove-swing")

state(True, 230, C.HIT_MAX, bpm=128, dx=-14)
snap("beat-tap")

state(True, 255, C.HIT_MAX, bpm=128, dx=14, inten=3)
snap("beat-burst")

# the palette, which the cube's top button walks through
for i in (1, 3, 4):
    state(True, 230, C.HIT_MAX, bpm=128, dx=-14, inten=3, palette=i,
          naming=True)
    snap("palette-%s" % C.PALETTE[i][0].lower())

# contact sheet
COLS = 3
pad, label_h = 8, 16
cw, ch = F.W, F.H
rows = (len(shots) + COLS - 1) // COLS
sheet = Image.new("RGB", (COLS * (cw + pad) + pad,
                          rows * (ch + pad + label_h) + pad), (24, 24, 24))
from PIL import ImageDraw                            # noqa: E402
d = ImageDraw.Draw(sheet)
for i, (name, img) in enumerate(shots):
    c, r = i % COLS, i // COLS
    x = pad + c * (cw + pad)
    y = pad + r * (ch + pad + label_h)
    sheet.paste(img, (x, y))
    d.text((x + 1, y + ch + 2), name, fill=(170, 170, 170))
sheet.save(os.path.join(OUT, "_contact.png"))
print("\n  contact sheet -> %s/_contact.png  (%d shots)" % (OUT, len(shots)))
