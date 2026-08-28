# Sprite art

Two pieces of art, made the same way and used differently.

| | |
| --- | --- |
| `../lib/tap_1.png` … `tap_7.png` | The **tap cycle**: seven 135×160 three-ink frames, 14 KB the lot, played back as an animation. `anim.style = "tap"`. |
| `../lib/glove.png` | The **punch**: one 60×62 two-ink frame, 459 bytes, translated at run time with the arm and impact drawn around it. `anim.style = "fist"`. |

Both are blitted with `M5.Lcd.drawPng` and deploy flat beside `main.py` — the
mechanism `dance/lib/*.png` uses, verified on the board.

## The style

Teenage Engineering's OP-1 draws its effect screens as **neon line art**:
thin saturated strokes on black, a big thin numeral, small-caps labels. Not
white fills — an earlier version that filled the screen with a solid white
hand read as a different product entirely.

Empty space is part of that style, but only up to a point. The punch keeps
the figure to about a third of the panel; the tap cycle deliberately does
not, because at that size the bottom two fifths of a 135×240 panel are black
in every frame, and that stops reading as composition and starts reading as a
bug. `stage_anim._place()` gives the tap a compact one-line header so the
figure can have the height.

## Where they came from

- `punch-strip-source.png` — eight cells of a boxing-glove punch, OpenAI
  `gpt-image-2`, prompted for OP-1 neon line art. **One pose is used**:
  generated cells drift in size and position, so playing them back swims.
- `tap-strip-source.png` — seven 270×480 cells of a robotic hand tapping a
  pad: cyan forearm, magenta hand, amber pad and impact. These *are* played
  back, because they were generated as a registered sequence and hold their
  position, and because the arm articulates in a way a translating sprite
  cannot fake. 270×480 is exactly twice the panel, so the reduction is a
  clean 2:1 with no resampling ratio to guess at.
- `tap-frames.png` — what `tools/build_tap.py` produced, for looking at.

## Why the tap is raster and not vector

The obvious reading of "trace it to vectors" is a tool like PNGToSVG. That
one is a **pixel-art** tracer — it emits a rect per run of identical pixels —
and this input is anti-aliased glow, so it would emit tens of thousands of
paths describing the blur. A centreline tracer is the tool that fits the
*input*; neither fits the *output*.

Vector buys resolution independence, and this display has exactly one
resolution. What it costs is measurable: the hand carries about a hundred
separate contours — finger segments, knuckle jewels, two wrist rings — so a
frame becomes a few hundred `drawLine` calls where a sprite is one
`drawPng`, and a partially drawn frame is visible tearing.

The one thing vector would genuinely have bought is tinting: `drawPng` cannot
recolour, so the tap keeps its own three inks and ignores `anim.palette`. The
manifest says so, because a caller that sets a palette and sees no change
should be able to find out why without guessing.

## The processing that matters

**Quantise first, then resample — with more than two inks.** This is the
reverse of what this file used to say, and the old advice is still right for
the glove. With two inks, resampling the RGB and snapping afterwards is
fine. With three, magenta and cyan strokes cross, and resampling averages
them into a grey-white that is neither ink; the quantiser then has to guess,
and guesses wrong at every crossing. So `build_tap.py` separates each ink
into its own mask *first*, reduces each mask on its own, and composites them
back. No blend can invent a colour that was not in the source.

Reducing a mask with `Image.BOX` gives coverage per destination pixel, and
the threshold is deliberately low (`COVER = 64`): a 2 px stroke halved covers
half a destination pixel, so anything near 50% has to survive or the line art
thins into dashes.

**Crop identically across every cell.** Registration is the whole reason
these frames can be played back at all. The crop is full-width because the
impact burst spans x 15..269, and clipping that would cut the one frame the
animation exists for; the top of the forearm is what gets sacrificed instead.

**Bake the black ground in.** No alpha. That is what makes the tap the only
subject on this panel that erases nothing: a frame covers the whole art box
in a single `drawPng`, so there is never a moment where the box has been
cleared and not yet painted. That moment *is* the flicker (op-cp rule 7).

## What the code copies off the art rather than inventing

- **Sprite size** comes from the PNG's own IHDR, not from a constant.
  `stage_anim._TAP_H` is overwritten by what actually loaded.
- **Arm spacing and alignment (punch).** The two cyan strokes are 47 px apart
  against a 108 px glove — a bit over two fifths, not the third first
  guessed. The arm attaches to the wrist BAND, whose centre sits 5 px left of
  the bounding-box centre because the thumb bulges right; `_BAND_DX` carries
  that measurement.
- **The impact throws SIDEWAYS.** True of the generated tap frames and made
  true of the drawn punch: a burst aimed downward reads as the hand leaking,
  and a 135 px panel has far more room left and right than below.

## Costs, measured on the board

`drawPng` of a 135×160 sprite takes **14 ms**, about seven times a beat.
Pre-decoding all seven into `newCanvas` buffers and pushing those costs
**392 KB** and still takes **9.7 ms** — so the bottleneck is the SPI bus, not
the PNG decode, and the memory buys nothing worth having. The node's loop
absorbs 14 ms: its microphone already digests a second of audio in one ~60 ms
gulp.

## Fallback

If `tap_*.png` did not deploy — all seven, or it is treated as none, because
a partial set plays a hand that jumps to a pose that never happened — the tap
style draws the punch instead, and if `glove.png` is missing too, the hand is
drawn from primitives (`_fist_primitive`). `tools/animcheck.py` covers every
path and is what caught the sprite being positioned from the primitive
geometry, and the impact overrunning the step ruler.
