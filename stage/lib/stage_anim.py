# The stage node's face — what a StickS3 does with a beat it can hear.
#
# Adapted from vendor/op-cp/dance/lib/scd_face.py, and simplified for this
# panel. Two things changed and both are the screen's doing:
#
#   * 135x240 is portrait and narrow, so the dancer's face-beside-hands
#     layout does not fit. The subject is stacked instead: header, one big
#     shape, step ticks, label.
#   * dance draws its hands from PNGs. Here everything is a flat primitive —
#     rectangles, circles, lines. That is cheaper than an asset pipeline and
#     it is also the look: one saturated colour at a time, hard edges, no
#     gradients, a lot of black.
#
# The palette rule is dance's, kept verbatim because it is what makes a flash
# legible: an accent is ONE hue at two brightnesses, and cycling it must never
# put a second colour on screen.
#
# Redraw discipline is op-cp's rule 7 — repaint only what changed, erase only
# the box about to be painted. Text is the expensive primitive, so the header
# and the label repaint only when their words actually change.

# Teenage Engineering's OP-1 draws its effect screens as NEON LINE ART: thin
# saturated strokes on black, big thin numerals, small-caps labels, and a lot
# of black. Not white fills. Everything below follows that.
BG = 0x000000
FG = 0xF0F0F0
DIM = 0x606060
FAINT = 0x202020
CYAN = 0x20C8F8
MAGENTA = 0xF040C0

# The impact SPLASHES SIDEWAYS. A burst aimed mostly downward reads as the
# glove leaking rather than striking, and on a panel this narrow there is far
# more room left and right than there is below. Unit vectors x100 plus a
# length factor, so the sideways strokes throw furthest and the downward ones
# stay short — integer maths throughout, this runs on a microcontroller.
_BURST = ((-100, 6, 100), (-94, 34, 92), (-78, 62, 76), (-52, 85, 55),
          (52, 85, 55), (78, 62, 76), (94, 34, 92), (100, 6, 100))

# The wrist band's centre sits 5 px left of the sprite's own centre, because
# the thumb bulges right and the crop is around the whole glove. Measured off
# examples/stage-node/glove.png; re-measure if the art changes. The arm has to
# attach to the BAND, not to the bounding box.
_BAND_DX = -5

# (name, lit, unlit) — one hue, two brightnesses.
PALETTE = (
    ("CYAN",    0x20C8F8, 0x082830),
    ("AMBER",   0xF8A020, 0x302008),
    ("LIME",    0x60E020, 0x142808),
    ("MAGENTA", 0xF040C0, 0x300828),
    ("VIOLET",  0x8060F8, 0x181030),
    ("RED",     0xF83820, 0x300808),
)
PALETTE_NAMES = [p[0] for p in PALETTE]

STYLES = ("face", "tap", "fist", "bars", "off")

# The tap sprites are a seven-frame cycle, and the beat only tells us where
# ONE of those frames belongs: the strike. So the frame is chosen from a
# phase that runs between beats, and every beat snaps the phase back to the
# strike. Prediction is only ever used for anticipation; the beat itself is
# always ground truth, so a tempo change costs at most one late landing.
#
# (percent of the measured beat interval, index into _tap_png). Reading the
# source strip: 4 is the impact, 5-7 the recoil, 1 the long hover, 2-3 the
# descent. So the strike sits at zero and the descent is the last fifth.
_TAP_PHASE = ((0, 3), (6, 4), (13, 5), (21, 6), (30, 0), (74, 1), (88, 2))
_TAP_FRAMES = 7
_TAP_H = 160                 # tools/build_tap.py owns this; read back below

# Frames a hit decays over. The node ticks at roughly 100 Hz, so 6 frames was
# a 60 ms punch — over before the eye caught it, which read as "the motion is
# too small" rather than "the motion is too fast". 20 frames is ~200 ms: a
# strike that lands hard and recovers visibly, still well inside a beat at
# any tempo this device plays.
HIT_MAX = 20
LEVEL_MAX = 255

_lcd = None
_glove_png = None            # the sprite, if it deployed with us
_glove_wh = (0, 0)           # its real size, read from the PNG header
_tap_png = []                # the seven-frame cycle, if it deployed with us
_tap_wh = (0, 0)
_font_small = None
_font_mid = None
_font_big = None
W = 135
H = 240

# geometry, filled by _place()
_HEAD_Y = 4
_HEAD_H = 48
_ART_Y = 30
_ART_H = 140
_TICK_Y = 182
_LABEL_Y = 210

_last = {}                   # region -> what was drawn there
_eye_box = None              # the exact boxes drawn last frame, so the next
_mouth_box = None            # one erases those and nothing else
_strike_box = None
_frame = 0
_gaze = 0
_gaze_until = 0
_lid_until = 0
_tap_prev_hit = 0            # for the rising edge that means "a beat landed"
_tap_since = 0               # ticks since that edge
_tap_period = 0              # ticks between the last two, measured not assumed
_tap_shown = -1              # which frame is on the panel right now

# Where the eyes wander to. A fixed ring rather than randomness: it is
# cheaper, it never picks the same place twice in a row, and on a panel this
# small the difference is invisible.
_GAZE_RING = (0, 5, 5, 0, -5, -5, 0, 3, -3, 0)


def _load(name):
    """Read a sprite. Deployed flat next to main.py on the device, and found
    beside this file on the host — same lookup dance uses."""
    here = __file__.rsplit("/", 1)[0] if "/" in __file__ else "."
    for path in (name, here + "/" + name,
                 "vendor/op-cp/stage/lib/" + name):
        try:
            with open(path, "rb") as f:
                return f.read()
        except OSError:
            pass
    return None


def _png_wh(blob):
    """A PNG's real size from its own header — IHDR puts width and height at
    bytes 16..24, big-endian. Sizing a sprite from the geometry around it
    instead is what put the impact strokes on the step ruler."""
    if blob and len(blob) > 24:
        return (int.from_bytes(blob[16:20], "big"),
                int.from_bytes(blob[20:24], "big"))
    return (0, 0)


def layout(lcd, w, h):
    """Read the panel; never hardcode a resolution or a font (op-cp rule 5).

    Font names are aliases on this firmware, so the two chosen here are the
    two that measured distinct: a small one for the header and a heavier one
    for the label. drawString on a panel with no font set silently draws
    nothing, which is exactly the bug the shot renderer caught.
    """
    global _lcd, W, H
    global _font_small, _font_mid, _font_big, _glove_png, _glove_wh
    global _tap_png, _tap_wh, _TAP_H
    global _frame, _gaze, _gaze_until, _lid_until
    global _tap_prev_hit, _tap_since, _tap_period, _tap_shown
    _lcd = lcd
    W, H = w, h
    _glove_png = _load("glove.png")
    _glove_wh = _png_wh(_glove_png)
    if not _glove_wh[0]:
        _glove_png = None
    # The tap cycle is all-or-nothing: a partial set would play a hand that
    # jumps back to a pose that never happened, which is worse than not
    # offering the style at all.
    tap = [_load("tap_%d.png" % (i + 1)) for i in range(_TAP_FRAMES)]
    if all(tap):
        _tap_png = tap
        _tap_wh = _png_wh(tap[0])
        _TAP_H = _tap_wh[1]
    else:
        _tap_png, _tap_wh = [], (0, 0)
    fonts = getattr(lcd, "FONTS", None)
    if fonts is not None:
        _font_small = getattr(fonts, "DejaVu12", None)
        _font_mid = getattr(fonts, "DejaVu18", None) or _font_small
        # The big numeral is the OP-1's signature. It must NOT also set the
        # footer word, which is how the style label ran off the bottom.
        _font_big = getattr(fonts, "DejaVu40", None) \
            or getattr(fonts, "DejaVu24", None) or _font_mid
    _place(None)
    _last.clear()
    # The face's wandering is driven by a free-running frame counter, so
    # laying out again restarts it. Without this the animation's phase
    # survives a re-layout and nothing that renders it is reproducible.
    _frame = _gaze = _gaze_until = _lid_until = 0
    # Same reason for the tap's beat phase: it is measured from the frames
    # that went before, so laying out again has to forget them or nothing
    # that renders this panel is reproducible.
    _tap_prev_hit = _tap_since = _tap_period = 0
    _tap_shown = -1


def _place(style):
    """Where the four regions sit, for the subject about to be drawn.

    Proportions, not pixels: header, subject, bar ruler, word. The panel is
    135 wide and there is no second column to put anything in.

    Two layouts, because one subject is a fixed-size sprite and the rest are
    drawn to fit. The drawn subjects get OP-1 proportions — a small-caps
    label, a big thin numeral under it, and a figure about a third of the
    panel, because that space IS the style. The tap cycle cannot be scaled
    (drawPng neither scales nor rotates), so instead the chrome yields to it:
    one compact header line, and the sprite gets its full height. Anything
    else leaves the bottom two fifths of the panel permanently black, which
    is the complaint this style exists to answer.

    Safe to run per frame because a style change repaints the whole panel —
    stage_table calls clear() when the subject changes, so no region ever
    inherits a box drawn under the other layout.
    """
    global _HEAD_H, _ART_Y, _ART_H, _TICK_Y, _LABEL_Y
    tall = style == "tap" and _tap_png
    _HEAD_H = 22 if tall else 48
    _ART_Y = _HEAD_Y + _HEAD_H
    _LABEL_Y = H - 28
    _TICK_Y = _LABEL_Y - 20
    _ART_H = _TAP_H if tall else (_TICK_Y - _ART_Y - 6)


def _stroke_round(x, y, w, h, r, colour):
    """A rounded outline, or a square one where that is all there is.

    The board has drawRoundRect; dance's host stub does not. op-cp's rule 1
    covers exactly this — reach for an optional API through getattr and
    degrade — and at these sizes the corner radius is a pixel or two anyway.
    """
    fn = getattr(_lcd, "drawRoundRect", None)
    if fn is not None:
        fn(x, y, w, h, r, colour)
        fn(x + 1, y + 1, max(1, w - 2), max(1, h - 2), max(0, r - 1), colour)
    else:
        _lcd.drawRect(x, y, w, h, colour)
        _lcd.drawRect(x + 1, y + 1, max(1, w - 2), max(1, h - 2), colour)


def _erase(box):
    if box is not None:
        _lcd.fillRect(box[0], box[1], box[2], box[3], BG)


def _changed(key, value):
    if _last.get(key) == value:
        return False
    _last[key] = value
    return True


def clear():
    """Full repaint. The only place a fillScreen is allowed: a subject change
    owns the whole panel, and everything after it erases only its own box."""
    if _lcd is None:
        return
    global _eye_box, _mouth_box, _strike_box, _tap_shown
    _lcd.fillScreen(BG)
    _last.clear()
    _eye_box = _mouth_box = _strike_box = None
    _tap_shown = -1          # nothing on the panel is the tap's any more


# ------------------------------------------------------------------ regions
def _header(name, bpm, fresh, accent):
    """A small-caps label with a big thin numeral under it — the OP-1's own
    way of putting a parameter on screen.

    Where the subject has claimed the height (the tap cycle), the same three
    facts go on one line at small-caps size instead. The numeral shrinking is
    a real loss of the OP-1 look; a figure with the bottom two fifths of the
    panel left black was a bigger one.
    """
    if not _changed("head", (name, bpm, fresh, accent, _HEAD_H)):
        return
    _lcd.fillRect(0, _HEAD_Y, W, _HEAD_H, BG)
    if _font_small is not None:
        _lcd.setFont(_font_small)
    _lcd.setTextColor(accent, BG)
    _lcd.drawString("BPM", 6, _HEAD_Y)
    _lcd.setTextColor(DIM, BG)
    label = name[:7]
    _lcd.drawString(label, W - 6 - _lcd.textWidth(label), _HEAD_Y)
    reading = "%d" % bpm if (bpm and fresh) else "--"
    if _HEAD_H < 40:
        # Measured, not guessed: the font is an alias on this firmware and a
        # hardcoded column ran the number into the word beside it.
        _lcd.setTextColor(FG if fresh else DIM, BG)
        _lcd.drawString(reading, 6 + _lcd.textWidth("BPM") + 5, _HEAD_Y)
        return
    if _font_big is not None:
        _lcd.setFont(_font_big)
    _lcd.setTextColor(FG if fresh else DIM, BG)
    _lcd.drawString(reading, 4, _HEAD_Y + 13)


def _ticks(step, accent, accent_deep, fresh):
    """Sixteen marks, the bar as a ruler. The lit one is where you are."""
    lit = step if fresh else -1
    if not _changed("ticks", (lit, accent)):
        return
    n = 16
    gap = 2
    cell = (W - 12 - gap * (n - 1)) // n
    _lcd.fillRect(0, _TICK_Y, W, 10, BG)
    for i in range(n):
        x = 6 + i * (cell + gap)
        on = i == lit
        if on:                              # the playhead: a filled tick
            _lcd.fillRect(x, _TICK_Y, cell, 10, accent)
        elif i % 4 == 0:                    # the beats: a taller hairline
            _lcd.fillRect(x + cell // 2, _TICK_Y + 1, 1, 8, accent_deep)
        else:                               # everything else: one pixel
            _lcd.fillRect(x + cell // 2, _TICK_Y + 4, 1, 2, FAINT)


def _label(text, accent):
    if not _changed("label", (text, accent)):
        return
    _lcd.fillRect(0, _LABEL_Y, W, H - _LABEL_Y, BG)
    if not text:
        return
    if _font_mid is not None:
        _lcd.setFont(_font_mid)
    _lcd.setTextColor(accent, BG)
    _lcd.drawString(text[:12], 6, _LABEL_Y)


# ------------------------------------------------------------------ subjects
def _face(hit, level, accent, accent_deep):
    """Eyes and a mouth, and neither of them a mask.

    Three things dance's face taught, and all three are here: the eyes WANDER
    (a face whose pupils never move is furniture), they BLINK, and the head
    pops on the beat instead of changing colour. The pupils also tighten when
    a hit lands — an excited face stares harder.

    Erasing is dance's method too: remember the exact box drawn last frame and
    clear only that, and use ONE box across both eyes, because two fills with
    a gap between them cost more than one fill over the gap.
    """
    global _eye_box, _mouth_box, _frame, _gaze, _gaze_until, _lid_until
    _frame += 1
    if _frame >= _gaze_until:
        _gaze_until = _frame + 26
        _gaze = _GAZE_RING[(_frame // 26) % len(_GAZE_RING)]
    if _frame >= _lid_until:
        _lid_until = _frame + 190          # a blink, now and then
    lid = _lid_until - _frame < 3

    cx = W // 2
    eye_r = (W * 17) // 100
    dx = W // 4 + 2
    # the head pops UP on the hit and settles — motion, not a colour change
    ey = _ART_Y + _ART_H // 3 - (hit * 4) // HIT_MAX
    pupil = eye_r // 3 if hit else eye_r // 2

    pose = (ey, lid, _gaze, pupil)
    if _changed("eyes", pose):
        _erase(_eye_box)
        for sgn in (-1, 1):
            ex = cx + sgn * dx
            if lid:
                _lcd.fillRect(ex - eye_r, ey - 1, 2 * eye_r, 2, CYAN)
            else:
                # outline, not a disc: the OP-1 draws with strokes, and a
                # filled eye next to a line-art glove reads as two projects
                _lcd.drawCircle(ex, ey, eye_r, CYAN)
                _lcd.drawCircle(ex, ey, eye_r - 1, CYAN)
                _lcd.fillCircle(ex + _gaze, ey + 2, pupil, MAGENTA)
        _eye_box = (cx - dx - eye_r - 1, ey - eye_r - 1,
                    2 * (dx + eye_r) + 3, 2 * eye_r + 3)

    my = _ART_Y + (_ART_H * 72) // 100
    mw = (W * 62) // 100
    mh = 8 + (level * 34) // LEVEL_MAX
    mh = (mh // 3) * 3                     # 3 px buckets: no sub-pixel jitter
    if _changed("mouth", (mh, accent)):
        _erase(_mouth_box)
        _stroke_round(cx - mw // 2, my - mh // 2, mw, mh,
                      min(6, mh // 2), accent)
        _mouth_box = (cx - mw // 2 - 1, my - mh // 2 - 1, mw + 3, mh + 3)


def _fist(hit, level, accent, accent_deep):
    """A boxing glove that lands on the beat, drawn OP-1 style.

    The glove is a sprite (examples/stage-node/art/README.md says where it
    came from); the arm and the impact are drawn, because they are literally
    straight lines and a line is cheaper and more exact than a bitmap of one.
    Generating seven frames and playing them back was the other option and it
    is worse: the figure drifts in size between generated frames, and the arm
    is the only thing that actually changes.

    The glove keeps its own two inks rather than following anim.palette. That
    is the OP-1 idiom — each effect screen has its own fixed colour scheme —
    and drawPng cannot tint anyway. The palette drives the type and the
    ruler, and the manifest says so.

    Deliberately not a colour flash: the beat is the arm extending, the glove
    dropping, and a few impact strokes. Nothing large changes hue.
    """
    global _strike_box
    if _glove_png is None:
        _fist_primitive(hit, level, accent, accent_deep)
        return

    gw, gh = _glove_wh
    cx = W // 2
    gx = cx - gw // 2
    # The figure is deliberately about a third of the panel: on an OP-1
    # screen the drawing is small and the space around it is the style. It
    # also has to leave room BELOW itself for the burst at full drop —
    # sized any bigger, the hardest hit got the smallest explosion, because
    # the clamp ate it.
    # Travel most of the band rather than nudging: the glove is a third of
    # the panel, so the space below it is there to be used, and a punch that
    # moves a fifth of its own height does not read as a punch.
    span = _ART_H - gh - 18             # the burst clamps itself per stroke
    drop = (hit * span) // HIT_MAX if hit else 0
    drop = (drop // 2) * 2                  # 2 px buckets: no jitter
    arm_y = _ART_Y
    top = _ART_Y + 2 + drop

    # The burst is centred just below the glove, not ON its bottom edge. Its
    # erase box is two pixels taller than the strokes, and centred on the
    # edge that box clipped the last rows of the glove every time the burst
    # faded — with the glove not redrawn, because it had not moved.
    iy = top + gh + 3
    reach = (12 + (hit * 26) // HIT_MAX) if hit else 0
    prev = _last.get("glove_top")
    moved = prev != top
    strike = (reach, iy, accent)
    if not (moved or _last.get("strike") != strike):
        return

    # All erasing before all drawing: the impact box is computed at the
    # previous glove position and sits right under it, so clearing it after
    # the glove was drawn takes a row off the knuckles.
    _erase(_strike_box)
    _strike_box = None
    if moved:
        if prev is not None:                # only the sliver its box vacated
            if top > prev:
                _lcd.fillRect(gx, prev, gw, top - prev, BG)
            else:
                _lcd.fillRect(gx, top + gh, gw, prev - top, BG)
        _last["glove_top"] = top
        # The arm: two thin strokes that stretch, spaced as in the source art
        # — the gap there is 47 px against a 108 px glove, so a bit over two
        # fifths of the glove's width, not the third I first guessed.
        half = (gw * 43) // 200
        ax = cx + _BAND_DX
        _lcd.fillRect(ax - half - 1, arm_y, 2, top - arm_y + 2, CYAN)
        _lcd.fillRect(ax + half - 1, arm_y, 2, top - arm_y + 2, CYAN)
        _lcd.drawPng(_glove_png, gx, top)

    _last["strike"] = strike
    if reach:
        # Same ink as the glove, as in the source: the impact is the glove's
        # own energy, and a third colour on a screen that allows two would be
        # the one thing that breaks the OP-1 look.
        # The burst must stay inside the art band. Unclamped it reached past
        # the step ruler, and its erase box then took a row off the ruler,
        # which does not repaint unless the step changes — so the damage
        # stayed on screen.
        # Clamp each stroke to the band, not the burst as a whole. Shrinking
        # the whole thing meant the hardest punch — which lands lowest — got
        # the smallest splash, and it threw away the sideways room, which is
        # the only room a 135 px panel has plenty of.
        r0 = 6
        floor = _ART_Y + _ART_H - 1
        bx = cx + _BAND_DX
        rmax = 0
        for dx, dy, ln in _BURST:
            r1 = r0 + (reach * ln) // 100
            if dy > 0 and iy + (dy * r1) // 100 > floor:
                r1 = ((floor - iy) * 100) // dy
            if r1 <= r0:
                continue
            rmax = max(rmax, r1)
            _lcd.drawLine(bx + dx * r0 // 100, iy + dy * r0 // 100,
                          bx + dx * r1 // 100, iy + dy * r1 // 100, accent)
        r = max(rmax, r0)
        _strike_box = (bx - r - 2, iy - 2, 2 * r + 4,
                       min(r, floor - iy) + 4)
    else:
        _strike_box = None


def _fist_primitive(hit, level, accent, accent_deep):
    """The hand, drawn without art. Kept so the panel still works if the
    sprite did not deploy, and exercised by tools/animcheck.py."""
    global _strike_box
    drop = (hit * 16) // HIT_MAX if hit else 0
    drop = (drop // 2) * 2
    HW = (W * 70) // 100
    HH = (HW * 96) // 100
    cx = W // 2
    x0 = cx - HW // 2
    rest = _ART_Y + (_ART_H - HH) // 2 + 4
    arm_y = rest - 14
    top = rest + drop

    def hx(v):
        return x0 + (v * HW) // 100

    def hy(v):
        return top + (v * HH) // 100

    ink_top = hy(30) - top
    ink_bot = hy(82) - top
    iy = top + ink_bot + 8
    reach = (12 + (hit * 24) // HIT_MAX) if hit else 0
    prev = _last.get("fist_top")
    moved = prev != top
    strike = (reach, iy, accent)
    if not (moved or _last.get("strike") != strike):
        return

    _erase(_strike_box)
    _strike_box = None
    if moved:
        lo = min(prev, top) if prev is not None else top
        hi = max(prev, top) if prev is not None else top
        band_y = lo + ink_top - 2
        _lcd.fillRect(x0, band_y, HW, (hi + ink_bot + 4) - band_y, BG)
        _last["fist_top"] = top

    aw = (HW * 32) // 100
    _lcd.fillRect(cx - aw // 2, arm_y, aw, (top + ink_top + 4) - arm_y, DIM)
    _lcd.fillRoundRect(hx(26), hy(30), hx(80) - hx(26), hy(74) - hy(30),
                       (HW * 16) // 100, FG)
    fw_ = hx(11) - hx(0)
    for fx in (28, 41, 54, 67):
        _lcd.fillRoundRect(hx(fx), hy(66), fw_, hy(82) - hy(66), fw_ // 2, FG)
    for gx2 in (41, 54, 67):
        _lcd.fillRect(hx(gx2) - 3, hy(66), 3, hy(82) - hy(66), BG)
    _lcd.fillRoundRect(hx(6), hy(40), hx(34) - hx(6), hy(60) - hy(40),
                       (HW * 9) // 100, FG)

    _last["strike"] = strike
    if reach:
        _lcd.fillRect(cx - reach, iy, reach * 2, 4, accent)
        for sgn in (-1, 1):
            _lcd.drawLine(cx + sgn * reach, iy,
                          cx + sgn * (reach + 12), iy - 10, accent)
        _strike_box = (cx - reach - 13, iy - 11, 2 * (reach + 13) + 2, 17)


def _bars(hit, level, accent, accent_deep):
    """A meter. The columns hold one colour; only the lit tip moves."""
    n = 5
    filled = 1 + (level * n) // (LEVEL_MAX + 1)
    if not _changed("bars", (filled, hit > 0, accent)):
        return
    gap = 6
    bw = (W - 12 - gap * (n - 1)) // n
    base = _ART_Y + _ART_H - 6
    tall = _ART_H - 34
    for i in range(n):
        x = 6 + i * (bw + gap)
        on = i < filled
        h = tall if on else 6
        _lcd.fillRect(x, _ART_Y, bw, base - _ART_Y, BG)   # this column only
        _lcd.drawRect(x, base - h, bw, h, accent_deep if on else FAINT)
        if on and hit:
            _lcd.fillRect(x, base - h, bw, 4, accent)     # the tip lights


def _tap(hit, level, accent, accent_deep):
    """The tap cycle: a robotic hand that plays the beat on a pad.

    Seven sprites, panel-sized, black baked in (`art/README.md` says where
    they came from). This is the one subject that does not erase anything,
    and that is the point: a frame covers the whole art box in a single
    drawPng, so there is never a moment where the box has been cleared and
    not yet painted. That moment IS the flicker on this panel — the reason
    every other subject here goes to such lengths to erase exactly the box it
    is about to fill.

    The cost is that the art cannot follow the palette; drawPng cannot tint,
    and the three inks are baked. That matches the OP-1 idiom the panel
    already follows — each effect screen keeps its own fixed scheme — and the
    palette still drives the numeral, the ruler and the word.

    Timing is measured, never assumed. The beat gives us the strike and
    nothing else, so the interval between the last two strikes is counted in
    ticks and the remaining six frames are spread over it. That makes the
    animation independent of both the tempo and the rate this loop happens to
    run at, and it re-synchronises on every beat: the worst a tempo change
    can do is land one strike late.
    """
    global _tap_prev_hit, _tap_since, _tap_period, _tap_shown
    if not _tap_png:
        _fist(hit, level, accent, accent_deep)          # art did not deploy
        return

    beat = hit > _tap_prev_hit
    _tap_prev_hit = hit
    if beat:
        # A plausible interval only. Two beats a tick apart is a double
        # trigger, and a gap of minutes is the show having stopped; neither
        # should be averaged into the pacing.
        if 4 <= _tap_since <= 600:
            _tap_period = _tap_since if not _tap_period \
                else (_tap_period + _tap_since) // 2
        _tap_since = 0
    else:
        _tap_since += 1

    period = _tap_period or 45
    if _tap_since > period * 2:
        idx = 0                       # two beats missed: back to the hover
    else:
        # Past 100% the hand simply stays poised on the last frame, which is
        # the descent — a beat running late holds the strike, it does not
        # invent one.
        pct = (_tap_since * 100) // period
        idx = _TAP_PHASE[0][1]
        for at, frame in _TAP_PHASE:
            if pct >= at:
                idx = frame
    if idx == _tap_shown:
        return
    _tap_shown = idx
    # Measured on the StickS3: 14 ms for this 135x160 blit, about seven times
    # a beat. That is the SPI bus and not the PNG decode — pre-decoding all
    # seven into canvases and pushing those costs 392 KB and still takes
    # 9.7 ms, so it is not worth the memory. The loop absorbs it: the mic
    # already digests a second of audio in one ~60 ms gulp.
    _lcd.drawPng(_tap_png[idx], (W - _tap_wh[0]) // 2, _ART_Y)


_SUBJECTS = {"face": _face, "tap": _tap, "fist": _fist, "bars": _bars}


# ------------------------------------------------------------------ entry
def draw(style, palette_i, hit, level, step, bpm, fresh, label, name="STAGE"):
    """One frame. Cheap when nothing changed — every region self-gates."""
    if _lcd is None:
        return
    _, accent, accent_deep = PALETTE[palette_i % len(PALETTE)]
    if style == "off":
        if _changed("art", ("off",)):
            _lcd.fillScreen(BG)
            _last.clear()
            _last["art"] = ("off",)
        return
    _place(style)
    _header(name, bpm, fresh, accent)
    _SUBJECTS.get(style, _face)(hit, level, accent, accent_deep)
    _ticks(step, accent, accent_deep, fresh)
    _label(label, accent)
