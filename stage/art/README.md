# Sprite art

`../glove.png` is the figure the panel draws: a **60×62 two-ink PNG, 459
bytes**, deployed flat beside `main.py` and blitted with `M5.Lcd.drawPng` —
the mechanism `dance/lib/*.png` uses, verified on the board.

## The style

Teenage Engineering's OP-1 draws its effect screens as **neon line art**:
thin saturated strokes on black, a big thin numeral, small-caps labels, and a
lot of empty space. Not white fills. The figure is roughly a third of the
panel — that space is the style, and an earlier version that filled the screen
with a solid white hand read as a different product entirely.

## Where it came from

`punch-strip-source.png` is the raw generation: eight cells of a boxing-glove
punch made with OpenAI `gpt-image-2`, prompted for OP-1 neon line art —
magenta glove outline, cyan wrist band and arm, no fills, no text.

**Only one pose is used.** Generated frames drift in size and position
between cells, so playing them back would swim. The motion is a translation
of a single sprite with the arm and the impact drawn at run time, which is
also how `dance` animates its hands.

## What the code copies off the art, rather than inventing

- **Arm spacing.** The two cyan strokes are 47 px apart against a 108 px
  glove in the source — a bit over two fifths of its width. A third, guessed,
  looked wrong.
- **Arm alignment.** The arm attaches to the wrist BAND, whose centre sits
  5 px left of the sprite's bounding-box centre because the thumb bulges
  right. `_BAND_DX` in `stage_anim.py` carries that measurement; re-measure it
  if the art changes.
- **The impact is a starburst**, not a bar under the glove — but it throws
  SIDEWAYS. A burst aimed mostly downward reads as the glove leaking, and on
  a 135 px panel there is far more room left and right than below.

## The processing that matters

The generator's output cannot go on the panel as it is:

1. **Downscale with a real filter, then quantise.** In that order. Anti-
   aliased neon on an RGB565 panel becomes mud; resampling first and then
   snapping every lit pixel to one of the two inks keeps the strokes clean.
   The lines survive because the glove is only ~110 px wide in the source, so
   this is barely a reduction.
2. **Cut the glove away from the arm.** The arm stretches at run time, so
   only the glove is a sprite. The cut is the widest cyan row — the band.
3. **Bake the black ground in.** No alpha. A sprite paints every pixel of its
   own box, so unlike a rounded primitive it cannot leave a corner behind, and
   only the sliver its box vacated needs clearing.

`stage_anim` reads the sprite's real size from the PNG header (IHDR, bytes
16..24) rather than assuming it.

## Fallback

If `glove.png` is missing, the panel draws the hand from primitives instead
(`_fist_primitive`). `tools/animcheck.py` covers both paths and is what
caught the sprite being positioned from the primitive geometry, and the
impact overrunning the step ruler.
