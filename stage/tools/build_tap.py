"""Turn the generated tap-motion strip into panel sprites.

    python3 tools/build_tap.py      # writes lib/tap_1.png .. lib/tap_7.png

The source (`art/tap-strip-source.png`) is seven 270x480 cells of neon line
art: a cyan forearm, a magenta robotic hand, an amber pad it taps. 270x480 is
exactly twice the StickS3 panel, so the reduction below is a clean 2:1 and
nothing has to be guessed about a resampling ratio.

Why sprites and not vectors
---------------------------
The obvious reading of "make it vector" is a tracer such as PNGToSVG. That
one is a PIXEL-ART tracer — it emits a rect per run of identical pixels — and
this input is anti-aliased glow, so it would emit tens of thousands of paths
describing the blur. A centreline tracer is the tool that fits the input, but
it does not fit the OUTPUT: vector buys resolution independence, and this
display has exactly one resolution. What it costs is real — the hand carries
about a hundred separate contours (finger segments, knuckle jewels, the two
wrist rings), so a frame becomes a few hundred `drawLine` calls where a
sprite is one `drawPng`, and a partially drawn frame is visible tearing.

So: raster, at exactly the size the panel shows. The one thing vector would
have bought that is genuinely missed is tinting, and the art has its own
three-ink scheme anyway, which is the OP-1 idiom the panel already follows.

Quantise first, then resample
-----------------------------
`art/README.md` says downscale first and quantise after. That is right for
TWO inks and wrong here, and the failure is instructive: magenta and cyan
strokes cross, and resampling RGB averages them into a grey-white that is
neither ink, which the quantiser then has to guess about. So each ink is
separated into its own mask FIRST, each mask is reduced on its own, and they
are composited back. No blend can invent a colour that was not in the source.

Reducing a mask with BOX gives coverage per destination pixel, and the
threshold is deliberately low: a 2 px stroke halved covers half a pixel, so
anything near 50% has to survive or the line art thins into dashes.
"""

import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, "..", "art", "tap-strip-source.png")
OUT = os.path.join(HERE, "..", "lib")

FRAMES = 7
CELL = (270, 480)

# The panel's inks. Cyan and magenta match stage_anim; amber is the pad and
# the impact, and is the third ink the older two-ink glove did not have.
CYAN = (0x20, 0xC8, 0xF8)
MAGENTA = (0xF0, 0x40, 0xC0)
AMBER = (0xF8, 0xA0, 0x20)

# Crop, in source pixels, applied identically to all seven cells — the frames
# must stay registered against each other or the hand swims. Full width,
# because the impact burst spans x 15..269 and clipping it would cut the one
# frame the whole animation is for. The top of the forearm is what gets
# sacrificed: it runs off the corner in the source anyway, and cropping there
# makes the arm enter from the panel edge, which reads as deliberate.
CROP = (0, 160, 270, 480)
SIZE = (135, 160)                    # exactly half of the crop

LIT = 62                 # below this a source pixel is glow, not ink
COVER = 64               # destination coverage a stroke must reach to survive


def classify(px):
    """Which ink a source pixel is, or None for glow and ground.

    Hue against the pixel's own maximum rather than absolute thresholds: the
    strokes have bright cores and dim skirts, and both are the same ink.
    """
    r, g, b = px
    mx = max(r, g, b)
    if mx < LIT:
        return None
    if b < mx * 0.45 and g < mx * 0.85:
        return "A"
    if b > mx * 0.5 and g < mx * 0.65:
        return "M"
    if r < mx * 0.65:
        return "C"
    return "M"           # the near-white cores sit inside magenta strokes


def sprite(cell):
    """One source cell -> one panel-sized, three-ink, black-ground sprite."""
    cell = cell.crop(CROP)
    w, h = cell.size
    px = cell.load()
    masks = {k: Image.new("L", (w, h), 0) for k in "CMA"}
    data = {k: masks[k].load() for k in "CMA"}
    for y in range(h):
        for x in range(w):
            ink = classify(px[x, y])
            if ink:
                data[ink][x, y] = 255
    out = Image.new("RGB", SIZE, (0, 0, 0))
    # Amber last: the impact is in front of the hand in the source, and the
    # finger that caused it should not paint over its own splash.
    for key, ink in (("C", CYAN), ("M", MAGENTA), ("A", AMBER)):
        small = masks[key].resize(SIZE, Image.BOX).point(
            lambda v: 255 if v >= COVER else 0)
        out.paste(ink, (0, 0), small)
    return out


if __name__ == "__main__":
    strip = Image.open(ART).convert("RGB")
    assert strip.size == (CELL[0] * FRAMES, CELL[1]), strip.size
    os.makedirs(OUT, exist_ok=True)
    total = 0
    frames = []
    for i in range(FRAMES):
        img = sprite(strip.crop((i * CELL[0], 0, (i + 1) * CELL[0], CELL[1])))
        frames.append(img)
        path = os.path.join(OUT, "tap_%d.png" % (i + 1))
        img.save(path, optimize=True)
        n = os.path.getsize(path)
        total += n
        print("tap_%d  %dx%d  %5d bytes -> %s"
              % (i + 1, img.width, img.height, n, os.path.normpath(path)))
    print("%d frames, %d bytes total" % (FRAMES, total))

    pad = 6
    prev = Image.new("RGB", ((SIZE[0] + pad) * FRAMES + pad,
                             SIZE[1] + 2 * pad), (40, 40, 40))
    for k, img in enumerate(frames):
        prev.paste(img, (pad + k * (SIZE[0] + pad), pad))
    path = os.path.join(HERE, "..", "art", "tap-frames.png")
    prev.resize((prev.width * 2, prev.height * 2), Image.NEAREST).save(path)
    print("preview -> %s" % os.path.normpath(path))
