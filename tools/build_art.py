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


# The square panel claps instead of tapping: two hands, palms facing, coming
# together on the beat. Turning the top-down hand a quarter turn was the
# cheap way to get one and it did not work — a shape drawn to be read from
# above becomes a paw seen from the side — so the clapping hand is its own
# drawing, in the same flat vocabulary.
#
# Drawn at 2x and reduced, because the fingers are 7 px apart at final size
# and rounding them by hand at that scale gives lumps. Reducing a flat sprite
# leaves a grey fringe, which on a black panel reads as blur, so it is
# thresholded straight back to two colours. drawPng can neither rotate nor
# mirror, so the right hand is baked out too.
CLAP = (60, 62)


def flatten(img, size):
    small = img.resize(size, Image.LANCZOS).convert("L").point(
        lambda v: 255 if v > 96 else 0)
    out = Image.new("RGB", size, BG)
    out.paste(FG, (0, 0), small)
    return out


def clap_left():
    """A left hand seen edge-on, palm facing right: forearm out of the screen
    edge, four fingers reaching in toward the other hand, thumb over the top."""
    img = Image.new("RGB", (CLAP[0] * 2, CLAP[1] * 2), BG)
    d = ImageDraw.Draw(img)
    rr(d, (0, 48, 42, 82), 14, FG)          # forearm, out of the left edge
    rr(d, (30, 30, 84, 100), 18, FG)        # palm
    for y in (34, 51, 68, 85):              # four fingers, reaching in
        rr(d, (76, y, 116, y + 13), 6, FG)
    rr(d, (50, 14, 86, 34), 9, FG)          # thumb, laid over the top
    return flatten(img, CLAP)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for name, fn in (("hand_up", hand_up), ("hand_tap", hand_tap)):
        img = fn()
        path = os.path.join(OUT, name + ".png")
        img.save(path, optimize=True)
        print("%-10s %dx%d  %5d bytes -> %s"
              % (name, img.width, img.height, os.path.getsize(path), path))

    left = clap_left()
    for suffix, variant in (("_l", left),
                            ("_r", left.transpose(Image.FLIP_LEFT_RIGHT))):
        path = os.path.join(OUT, "clap" + suffix + ".png")
        variant.save(path, optimize=True)
        print("%-10s %dx%d  %5d bytes -> %s"
              % ("clap" + suffix, variant.width, variant.height,
                 os.path.getsize(path), path))
    # a preview strip for humans
    strip = Image.new("RGB", (W * 2 + CLAP[0] * 2 + 40, H + 16), (24, 24, 24))
    strip.paste(hand_up(), (8, 8))
    strip.paste(hand_tap(), (W + 16, 8))
    _l = clap_left()
    strip.paste(_l, (W * 2 + 24, 8))
    strip.paste(_l.transpose(Image.FLIP_LEFT_RIGHT), (W * 2 + CLAP[0] + 32, 8))
    prev = os.path.join(OUT, "..", "sim", "shots", "_hands.png")
    os.makedirs(os.path.dirname(prev), exist_ok=True)
    strip.resize((strip.width * 2, strip.height * 2), Image.NEAREST).save(prev)
    print("preview -> %s" % prev)
