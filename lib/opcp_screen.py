# OP-CP — the three alternate views, and the full-screen compositor.
#
# Original work in the same visual language as the roll — flat, one accent,
# primitive geometry — not a copy of anyone's artwork.
#
# This module imports opcp_ui and never the other way round; redraw_all lives
# here because it is the only function that needs both the roll and the views.

import time

import M5

import opcp_conf as C
import opcp_ui as U
from opcp_state import S

# worst-case extents, so the erase boxes above are computed once and cannot
# drift from what the drawing code actually paints
MARK_D_MIN = 6           # percussion marks start this far out of the face
MARK_D_RANGE = 10        # ...and travel this much further at full hit
MARK_D = MARK_D_MIN + MARK_D_RANGE
DOT_R = 6                # biggest ring dot is the 5 px playhead
PULSE_R = 13             # biggest centre pulse is 3 + 9

_TRIG = None


def _trig():
    """A 64-entry sin/cos table, built once, on first use.

    Cheaper than importing math into every frame's path, and it keeps the ring
    layout to integer work after setup.
    """
    global _TRIG
    if _TRIG is None:
        import math
        _TRIG = [(math.cos(i / 64.0 * 6.283185),
                  math.sin(i / 64.0 * 6.283185)) for i in range(64)]
    return _TRIG


def _cos(a):
    return _trig()[int((a % 6.283185) / 6.283185 * 64) % 64][0]


def _sin(a):
    return _trig()[int((a % 6.283185) / 6.283185 * 64) % 64][1]


def anim_zone():
    """The band between the header and the footer."""
    return U.ROLL_Y, U.ROLL_H


def build_ring():
    """Sixteen points on an ellipse: the pattern as a loop you can see at once."""
    top, h = anim_zone()
    cx, cy = U.W // 2, top + h // 2
    rx, ry = min(U.W // 2 - 14, 98), max(8, h // 2 - 8)
    pts = []
    for i in range(C.STEPS):
        # start at 12 o'clock and run clockwise, so step 1 is where you expect
        a = (i / C.STEPS) * 6.283185 - 1.570796
        pts.append((int(cx + rx * _cos(a)), int(cy + ry * _sin(a))))
    S.ring_pts = pts


# The bounds each view last painted, so the next frame can erase exactly that
# instead of the whole band. Clearing 240x69 and redrawing into it 18 times a
# second is what the face flicker was: the panel spends part of every frame
# showing the cleared state. redraw with full=True resets these.
_face_box = None
_ring_drawn = False
_bars_labels = None


def _erase(box):
    if box:
        M5.Lcd.fillRect(box[0], box[1], box[2], box[3], C.BG)


def _band(full):
    """A full repaint owns the band; an animation frame does not."""
    if full:
        top, h = anim_zone()
        M5.Lcd.fillRect(0, top, U.W, h, C.BG)
        return True
    return False


# --- FACE: one flat shape, driven entirely by the music -------------------
def draw_face(full=False):
    global _face_box
    top, h = anim_zone()
    if _band(full):
        _face_box = None
    energy = max(S.hit)
    c = C.MUTED if S.muted[S.track] else C.TRACK_COLORS[S.track]

    fw = min(96, U.W - 60)
    fh = min(h - 8, 52 + (energy * 8) // C.HIT_MAX)
    fx = (U.W - fw) // 2
    fy = top + (h - fh) // 2

    # the marks below reach MARK_D px out of each side at full percussion, so
    # one box covers everything this function can paint
    _erase(_face_box)
    ex0 = fx - MARK_D
    if ex0 < 0:
        ex0 = 0
    ex1 = fx + fw + MARK_D
    if ex1 > U.W:
        ex1 = U.W
    _face_box = (ex0, fy, ex1 - ex0, fh)

    M5.Lcd.fillRect(fx, fy, fw, fh, C.TRACK_DEEP[S.track])
    M5.Lcd.fillRect(fx, fy, fw, 3, c)
    M5.Lcd.fillRect(fx, fy + fh - 3, fw, 3, c)

    eye_h = 2 if S.blink else 10 + (energy * 4) // C.HIT_MAX
    ey = fy + fh // 2 - eye_h // 2 - 4
    look = 0 if S.track == 3 else max(-4, min(4, (S.last_semi - 8) // 2))
    for side in (-1, 1):
        ex = fx + fw // 2 + side * 20 - 5
        M5.Lcd.fillRect(ex + look, ey, 10, eye_h, C.FG)

    mw = 8 + (energy * 30) // C.HIT_MAX
    M5.Lcd.fillRect(fx + (fw - mw) // 2, fy + fh - 16, mw, 3, c)

    # percussion pushes marks out of the sides rather than shaking the frame
    if S.hit[3]:
        d = MARK_D_MIN + (S.hit[3] * MARK_D_RANGE) // C.HIT_MAX
        M5.Lcd.fillRect(fx - d, fy + fh // 2, 4, 4, C.TRACK_COLORS[3])
        M5.Lcd.fillRect(fx + fw + d - 4, fy + fh // 2, 4, 4, C.TRACK_COLORS[3])


# --- RING: the sixteen steps as a loop the playhead runs around -----------
def draw_ring(full=False):
    global _ring_drawn
    top, h = anim_zone()
    if _band(full):
        _ring_drawn = False
    if not S.ring_pts:
        build_ring()
    st = S.steps()
    # The dots sit at fixed points and only change size, so a smaller one drawn
    # over a bigger one leaves a halo — each needs its own worst case erased,
    # which is still a fifth of the band that contains all sixteen.
    #
    # ALL of the erasing first, though: neighbouring dots are 9 px apart and
    # these boxes are 13 px wide, so erasing dot B after drawing dot A takes a
    # bite out of A. (Caught by the ghost check, which reported missing pixels
    # rather than left-over ones — the giveaway.)
    if _ring_drawn:
        for x, y in S.ring_pts:
            M5.Lcd.fillRect(x - DOT_R, y - DOT_R, 2 * DOT_R + 1,
                            2 * DOT_R + 1, C.BG)
        M5.Lcd.fillRect(U.W // 2 - PULSE_R, top + h // 2 - PULSE_R,
                        2 * PULSE_R + 1, 2 * PULSE_R + 1, C.BG)
    for i, (x, y) in enumerate(S.ring_pts):
        on = st[i] is not None
        if S.playing and i == S.play_step:
            M5.Lcd.fillCircle(x, y, 5, C.ACCENT if S.recording else C.FG)
        elif on:
            M5.Lcd.fillCircle(x, y, 4, C.MUTED if S.muted[S.track]
                              else C.TRACK_COLORS[S.track])
        elif i % 4 == 0:
            M5.Lcd.fillRect(x - 1, y - 1, 3, 3, C.FAINT)
        else:
            # 2px, not 1 — a single pixel vanishes on the panel, and the loop
            # then reads as four beat marks floating in space, not as a ring
            M5.Lcd.fillRect(x, y, 2, 2, C.FAINT)

    energy = max(S.hit)
    if energy:
        M5.Lcd.fillCircle(U.W // 2, top + h // 2,
                          3 + (energy * 9) // C.HIT_MAX,
                          C.TRACK_COLORS[S.track])
    _ring_drawn = True


# --- BARS: four channel meters --------------------------------------------
def draw_bars(full=False):
    # no per-frame band clear: every column repaints its own full height as
    # rail-then-level, and the labels draw with a background, so there is
    # nothing between them that could go stale
    global _bars_labels
    if _band(full):
        _bars_labels = None
    top, h = anim_zone()
    seg = U.W // C.TRACKS
    bw = max(10, U.SW)           # same width as a roll column — one vocabulary
    base = top + h - U.TINY_H - 2
    maxh = base - top - 2
    M5.Lcd.fillRect(U.ROLL_X, base, U.ROLL_W, 1, C.FAINT)
    # The four names cost 7.6 ms of a 9.8 ms frame — measured; text is by far
    # the most expensive thing on this screen, four drawStrings costing more
    # than clearing the entire band. They only change when the selection or a
    # mute does, so they are drawn then and not eighteen times a second.
    labels = (S.track, tuple(S.muted))
    names = labels != _bars_labels
    _bars_labels = labels
    if names:
        M5.Lcd.setFont(U.TINY)
    for t in range(C.TRACKS):
        x = t * seg + (seg - bw) // 2
        lvl = 2 + (S.hit[t] * (maxh - 2)) // C.HIT_MAX
        c = C.MUTED if S.muted[t] else C.TRACK_COLORS[t]
        # rail only ABOVE the level, not the full column with the level
        # painted back over it: the two used to overlap by the level's whole
        # height, which is the tallest thing on screen at full hit
        M5.Lcd.fillRect(x, top, bw, maxh + 2 - lvl, C.RAIL)
        M5.Lcd.fillRect(x, base - lvl, bw, lvl, c)
        if names:
            M5.Lcd.setTextColor(c if t == S.track else C.DIM, C.BG)
            s = C.TRACK_NAMES[t]
            M5.Lcd.drawString(s, t * seg + (seg - M5.Lcd.textWidth(s)) // 2,
                              base + 2)


# --- FILES: eight save slots and the factory presets ----------------------
def draw_files(full=False):
    """Three direct-access columns: presets, slots 1-4, slots 5-8.

    No cursor — every entry is labelled with the key that fires it, the same
    contract as the step keys. While save is armed the preset column drops to
    FAINT (presets are read-only targets) and every slot digit lights up.
    """
    top, h = anim_zone()
    M5.Lcd.fillRect(0, top, U.W, h, C.BG)   # not animated; one clear is fine
    M5.Lcd.setFont(U.TINY)
    colw = (U.W - 2 * U.MARGIN) // 3
    lh = (h - 4) // 4
    y0 = top + 2

    for n, p in enumerate(C.PRESETS):
        y = y0 + n * lh
        kc = C.FAINT if S.files_arm else C.FG
        nc = C.FAINT if S.files_arm else C.DIM
        M5.Lcd.setTextColor(kc, C.BG)
        M5.Lcd.drawString(C.PRESET_KEYS[n], U.MARGIN, y)
        M5.Lcd.setTextColor(nc, C.BG)
        M5.Lcd.drawString(p[0], U.MARGIN + 12, y)

    for i in range(C.SLOTS):
        x = U.MARGIN + (1 + i // 4) * colw
        y = y0 + (i % 4) * lh
        m = S.slot_meta[i]
        M5.Lcd.setTextColor(C.FG if (m or S.files_arm) else C.DIM, C.BG)
        M5.Lcd.drawString(str(i + 1), x, y)
        if m:
            M5.Lcd.setTextColor(C.DIM, C.BG)
            M5.Lcd.drawString("%d %s" % (m[0], C.SCALES[m[1]][0]), x + 12, y)
        else:
            M5.Lcd.setTextColor(C.FAINT, C.BG)
            M5.Lcd.drawString("--", x + 12, y)


def draw_cartoon(full=False):
    U.hold()
    try:
        if S.view == C.V_FACE:
            draw_face(full)
        elif S.view == C.V_RING:
            draw_ring(full)
        elif S.view == C.V_BARS:
            draw_bars(full)
    finally:
        U.release()


def animate():
    """Advance the trigger envelopes and repaint just the animation band."""
    now = time.ticks_ms()
    if time.ticks_diff(now, S.next_anim) < 0:
        return
    S.next_anim = time.ticks_add(now, C.ANIM_MS)

    changed = False
    for t in range(C.TRACKS):
        if S.hit[t] > 0:
            S.hit[t] -= 1
            changed = True

    if time.ticks_diff(now, S.next_blink) >= 0:
        S.blink = 2 if S.blink == 0 else 0
        S.next_blink = time.ticks_add(
            now, 140 if S.blink else 1800 + (time.ticks_ms() % 1400))
        changed = True
    elif S.blink:
        changed = True

    if changed:
        draw_cartoon()


def redraw_body():
    """Repaint only the roll (or the animation band) — no fillScreen.

    Almost every key used to set dirty_all, which meant a 62 ms full-screen
    redraw. At a 133 ms sixteenth that is half a step, and it showed up as the
    step clock firing up to 60 ms late whenever you touched a control mid-play.
    The header and footer already repaint themselves from head_changed() /
    footer_changed(), so a control change rarely needs more than this.
    """
    U.hold()
    try:
        if S.view == C.V_ROLL:
            U.draw_roll()
        elif S.view == C.V_FILES:
            draw_files(True)
        elif S.view != C.V_HELP:
            build_ring()
            draw_cartoon(True)
    finally:
        U.release()


def redraw_all():
    U.hold()
    try:
        M5.Lcd.fillScreen(C.BG)
        if S.view == C.V_HELP:
            U.draw_help()
            return
        U.draw_head()
        if S.view == C.V_ROLL:
            U.draw_roll()
        elif S.view == C.V_FILES:
            draw_files(True)
        else:
            build_ring()
            draw_cartoon(True)
        U.draw_footer()
    finally:
        U.release()
