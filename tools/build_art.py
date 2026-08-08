"""Render the hand sprites — flat, chunky, original art in the spirit of
the OP-1's Finger sequencer (a hand that plays the beat), not a copy of it.

    python3 tools/build_art.py     # writes lib/hand_up.png, lib/hand_tap.png

Black background baked in (the screen ground is black, so no alpha needed),
FG white for the hand. Deployed flat next to main.py like everything else.
"""

import os
import sys

from PIL import Image, ImageDraw

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib")
W, H = 100, 96
BG = (0, 0, 0)
FG = (240, 240, 240)


def canvas():
    img = Image.new("RGB", (W, H), BG)
    return img, ImageDraw.Draw(img)


def rr(d, box, r, fill):
    d.rounded_rectangle(box, radius=r, fill=fill)


def hand_up():
    """Hovering: palm high, fingers relaxed and slightly spread."""
    img, d = canvas()
    # forearm enters from the top edge
    rr(d, (34, 0, 66, 26), 8, FG)
    # palm
    rr(d, (22, 18, 78, 62), 16, FG)
    # four fingers, gently curled (short), fanned by 1-2 px
    for i, (x, ln) in enumerate(((24, 16), (38, 20), (52, 20), (66, 16))):
        rr(d, (x, 58, x + 11, 58 + ln), 5, FG)
    # thumb off the left side
    rr(d, (8, 34, 26, 50), 7, FG)
    return img


def hand_tap():
    """The hit: hand dropped, index finger extended onto the pad."""
    img, d = canvas()
    # forearm follows the hand down
    rr(d, (36, 0, 68, 40), 8, FG)
    # palm, lower and tilted-feeling (slightly narrower)
    rr(d, (26, 32, 80, 74), 16, FG)
    # index finger extended long — the one that plays
    rr(d, (28, 68, 40, 94), 5, FG)
    # the rest curled tight under the palm
    for x in (44, 57, 69):
        rr(d, (x, 68, x + 10, 80), 5, FG)
    # thumb tucked
    rr(d, (14, 44, 30, 58), 7, FG)
    return img


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for name, fn in (("hand_up", hand_up), ("hand_tap", hand_tap)):
        img = fn()
        path = os.path.join(OUT, name + ".png")
        img.save(path, optimize=True)
        print("%-10s %dx%d  %5d bytes -> %s"
              % (name, img.width, img.height, os.path.getsize(path), path))
    # a preview strip for humans
    strip = Image.new("RGB", (W * 2 + 24, H + 16), (24, 24, 24))
    strip.paste(hand_up(), (8, 8))
    strip.paste(hand_tap(), (W + 16, 8))
    prev = os.path.join(OUT, "..", "sim", "shots", "_hands.png")
    os.makedirs(os.path.dirname(prev), exist_ok=True)
    strip.resize((strip.width * 2, strip.height * 2), Image.NEAREST).save(prev)
    print("preview -> %s" % prev)
