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


# --- FACE: one flat shape, driven entirely by the music -------------------
def draw_face(full=False):
    top, h = anim_zone()
    M5.Lcd.fillRect(0, top, U.W, h, C.BG)
    energy = max(S.hit)
    c = C.MUTED if S.muted[S.track] else C.TRACK_COLORS[S.track]

    fw = min(96, U.W - 60)
    fh = min(h - 8, 52 + (energy * 8) // C.HIT_MAX)
    fx = (U.W - fw) // 2
    fy = top + (h - fh) // 2

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
        d = 6 + (S.hit[3] * 10) // C.HIT_MAX
        M5.Lcd.fillRect(fx - d, fy + fh // 2, 4, 4, C.TRACK_COLORS[3])
        M5.Lcd.fillRect(fx + fw + d - 4, fy + fh // 2, 4, 4, C.TRACK_COLORS[3])


# --- RING: the sixteen steps as a loop the playhead runs around -----------
def draw_ring(full=False):
    top, h = anim_zone()
    M5.Lcd.fillRect(0, top, U.W, h, C.BG)
    if not S.ring_pts:
        build_ring()
    st = S.steps()
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
            M5.Lcd.fillRect(x, y, 1, 1, C.FAINT)

    energy = max(S.hit)
    if energy:
        M5.Lcd.fillCircle(U.W // 2, top + h // 2,
                          3 + (energy * 9) // C.HIT_MAX,
                          C.TRACK_COLORS[S.track])


# --- BARS: four channel meters --------------------------------------------
def draw_bars(full=False):
    top, h = anim_zone()
    M5.Lcd.fillRect(0, top, U.W, h, C.BG)
    seg = U.W // C.TRACKS
    bw = 10
    base = top + h - U.TINY_H - 2
    maxh = base - top - 2
    M5.Lcd.setFont(U.TINY)
    for t in range(C.TRACKS):
        x = t * seg + (seg - bw) // 2
        lvl = 2 + (S.hit[t] * (maxh - 2)) // C.HIT_MAX
        c = C.MUTED if S.muted[t] else C.TRACK_COLORS[t]
        M5.Lcd.fillRect(x, top, bw, maxh, C.RAIL)
        M5.Lcd.fillRect(x, base - lvl, bw, lvl, c)
        M5.Lcd.setTextColor(c if t == S.track else C.DIM, C.BG)
        s = C.TRACK_NAMES[t]
        M5.Lcd.drawString(s, t * seg + (seg - M5.Lcd.textWidth(s)) // 2, base + 2)


def draw_cartoon(full=False):
    if S.view == C.V_FACE:
        draw_face(full)
    elif S.view == C.V_RING:
        draw_ring(full)
    elif S.view == C.V_BARS:
        draw_bars(full)


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
    if S.view == C.V_ROLL:
        U.draw_roll()
    elif S.view != C.V_HELP:
        build_ring()
        draw_cartoon(True)


def redraw_all():
    M5.Lcd.fillScreen(C.BG)
    if S.view == C.V_HELP:
        U.draw_help()
        return
    U.draw_head()
    if S.view == C.V_ROLL:
        U.draw_roll()
    else:
        build_ring()
        draw_cartoon(True)
    U.draw_footer()
