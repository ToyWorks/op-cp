# SCD — the screen: a face that dances and a hand that plays the beat.
#
# The servos got quiet (their whine was corrupting the beat detector), so
# the DANCE moved onto the panel, in the spirit of the OP-1's Finger
# sequencer — a flat hand that plays along — as original art, not a copy:
#
#   * the face itself swings left/right (eased translate), drops on the
#     hit and springs back (bob), and breathes bigger with the loudness
#     (scale) — 左右 / 上下 / 前后, all virtual, all silent
#   * a hand hovers over a drum pad and TAPS it on every beat; the pad
#     lights, strong hits burst
#
# Two PNG sprites (tools/build_art.py renders them; drawPng measured 8 ms
# on device) and flat primitives for everything else. Elements redraw only
# when their parameter tuples change.

import M5

import scd_conf as C
from scd_state import S

W = H = 0
FACE_CX = 0
EYE_Y = 92
EYE_DX = 40
EYE_R = 22
MOUTH_DY = 62
FONT = None
FONT_H = 0

HAND_X = PAD_X = PAD_Y = PAD_W = PAD_H = 0
HAND_UP_Y = 52
HAND_TAP_Y = 96

_hand_up = None
_hand_tap = None
_last = {}


def _changed(key, params):
    if _last.get(key) == params:
        return False
    _last[key] = params
    return True


def _load(name):
    # deployed flat next to main.py on the device; under lib/ on the host
    for p in (name, "lib/" + name):
        try:
            with open(p, "rb") as f:
                return f.read()
        except OSError:
            pass
    return None


def layout():
    global W, H, FACE_CX, FONT, FONT_H
    global HAND_X, PAD_X, PAD_Y, PAD_W, PAD_H, _hand_up, _hand_tap
    W = M5.Lcd.width()
    H = M5.Lcd.height()
    FACE_CX = (W - 108) // 2 + 10        # face zone leaves the hand column
    HAND_X = W - 106
    PAD_X = W - 104
    PAD_W = 96
    PAD_H = 26
    PAD_Y = H - 62
    FONT = getattr(M5.Lcd.FONTS, "DejaVu12", None) or M5.Lcd.FONTS.DejaVu9
    M5.Lcd.setFont(FONT)
    try:
        FONT_H = M5.Lcd.fontHeight() or 16
    except Exception:
        FONT_H = 16
    _hand_up = _load("hand_up.png")
    _hand_tap = _load("hand_tap.png")
    _last.clear()


# face clearing box: sized for the WORST translate+scale+bob, asserted by
# selftest so a popped, swung face can never smear outside it
FACE_HALF_W = 100
FACE_TOP = 46
FACE_BOT = 206


def _mouth(cx, my, half_w, half_h):
    M5.Lcd.fillCircle(cx - half_w, my, half_h, C.FG)
    M5.Lcd.fillCircle(cx + half_w, my, half_h, C.FG)
    M5.Lcd.fillRect(cx - half_w, my - half_h, 2 * half_w, 2 * half_h + 1, C.FG)


def draw_face(dx, dy, scale, lid, gaze):
    """Pose changes repaint the whole face zone; a mouth-only change (the
    loudness breathing between beats) repaints just the mouth's own box —
    a full-zone fill per 1 px of mouth is what dragged the loop to 3 fps."""
    cx = FACE_CX + dx
    my = EYE_Y + MOUTH_DY * scale // 100 + dy
    half_w = (21 + (S.level >> 4) + S.hit * 2) * scale // 100
    half_h = 3 + (S.level * 10 >> 8) + S.hit * 2
    pose = (dx, dy, scale, lid, gaze)
    mouth = (my, half_w, half_h)

    if _changed("pose", pose):
        _last["mouth"] = mouth
        M5.Lcd.fillRect(FACE_CX - FACE_HALF_W, FACE_TOP,
                        2 * FACE_HALF_W, FACE_BOT - FACE_TOP, C.BG)
        edx = EYE_DX * scale // 100
        r = EYE_R * scale // 100
        ey = EYE_Y + dy
        for side in (-1, 1):
            ex = cx + side * edx
            if lid:
                M5.Lcd.fillRect(ex - r, ey - 2, 2 * r, 4, C.FG)
            else:
                M5.Lcd.fillCircle(ex, ey, r, C.FG)
                pr = 8 if scale < 104 else 5   # excited faces stare harder
                M5.Lcd.fillCircle(ex + gaze, ey + 2, pr, C.INK)
        _mouth(cx, my, half_w, half_h)
    elif _changed("mouth", mouth):
        box = 57 + 25 + 3                      # worst capsule half-extent
        M5.Lcd.fillRect(cx - box, EYE_Y + MOUTH_DY * scale // 100 - 30 + dy,
                        2 * box, 62, C.BG)
        _mouth(cx, my, half_w, half_h)


def draw_hand(tap, burst):
    if not _changed("hand", (tap, burst)):
        return
    if _hand_up is None:
        return
    M5.Lcd.fillRect(HAND_X, 40, W - HAND_X, PAD_Y + PAD_H + 6 - 40, C.BG)
    # the pad lights while the hand is down
    M5.Lcd.fillRoundRect(PAD_X, PAD_Y, PAD_W, PAD_H, 8,
                         C.ACCENT if tap else C.ACCENT_DEEP)
    if tap:
        M5.Lcd.drawPng(_hand_tap, HAND_X + 3, HAND_TAP_Y)
        if burst:
            # a strong hit throws sparks off the pad
            for bx, by in ((PAD_X - 8, PAD_Y - 6), (PAD_X + PAD_W + 2, PAD_Y - 6),
                           (PAD_X - 6, PAD_Y + PAD_H), (PAD_X + PAD_W, PAD_Y + PAD_H)):
                M5.Lcd.fillRect(bx, by, 6, 6, C.ACCENT)
    else:
        M5.Lcd.drawPng(_hand_up, HAND_X + 3, HAND_UP_Y)


def draw_info():
    bpm = "%d BPM" % S.bpm if (S.grooving and S.bpm) else ""
    mode = S.mode_word
    if not _changed("info", (bpm, mode)):
        return
    M5.Lcd.setFont(FONT)
    y = H - FONT_H - 8
    M5.Lcd.fillRect(0, y, W, FONT_H, C.BG)
    M5.Lcd.setTextColor(C.DIM, C.BG)
    M5.Lcd.drawString(mode, 10, y)
    if bpm:
        M5.Lcd.setTextColor(C.ACCENT, C.BG)
        M5.Lcd.drawString(bpm, PAD_X + PAD_W - M5.Lcd.textWidth(bpm), y)


def draw(now):
    """One face frame, rate-limited by the caller via S.next_anim."""
    if S.blink and now > S.blink:
        S.blink = 0
    if not S.blink and now > S.next_blink:
        S.blink = now + C.BLINK_MS
        gap = C.BLINK_GAP_MIN + S.rand() % (C.BLINK_GAP_MAX - C.BLINK_GAP_MIN)
        S.next_blink = now + gap + (1200 if S.grooving else 0)

    if S.grooving:
        tgt = S.side * 14
        d = tgt - S.dx
        S.dx = tgt if -3 < d < 3 else S.dx + d // 3     # eased swing
        dy = S.hit * 12 // C.HIT_MAX                    # drop, spring back
        # loudness in 8 coarse buckets: room jitter must not change the pose,
        # because a pose change repaints the whole face zone
        scale = 96 + (S.level >> 5) * 2 + S.hit * 2
        gaze = S.dx * 10 // 14                          # eyes lead the swing
    else:
        d = -S.dx
        S.dx = 0 if -3 < d < 3 else S.dx + d // 3
        ph = ((now - S.breath0) % C.BREATH_MS) * 2 // C.BREATH_MS
        dy = 1 if ph else 0
        scale = 100
        gaze = S.gaze

    draw_face(S.dx, dy, scale, 1 if S.blink else 0, gaze)
    draw_hand(1 if S.hit > C.HIT_MAX // 2 else 0,
              1 if (S.hit and S.hit_intensity >= 3) else 0)
    draw_info()
