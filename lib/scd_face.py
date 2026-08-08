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
#
# One face, two panels. Every coordinate comes from the layout table below,
# picked by the width the board reports, so neither machine has its numbers
# scattered through the drawing code.
#
# The two are not the same drawing scaled. On 320x240 the face sits left and
# one hand plays a pad in the right-hand column. The cube's 240x240 square
# has no room for such a column, so it does the other obvious thing with a
# pair of hands: it CLAPS. Two palms face each other under a face that is
# drawn flatter to leave them room, and every beat drives them together and
# lets them spring apart. The pad's job — somewhere for the accent to live
# between beats — passes to a slim bar along the bottom, which is also the
# VU meter the twelve LEDs provide on the CoreS3 and this board has not got.

import scd_board as BOARD
import scd_conf as C
from scd_state import S

# m_* are how hard the mouth reacts: (level shift, hit width, level height
# numerator, hit height). The square runs them softer — its mouth has hands
# below it to stay clear of, and a mouth that swings 160 px wide on a 240 px
# panel stops reading as a mouth.
_WIDE = {
    "face_cx": 116, "half_w": 100, "top": 46, "bot": 206,
    "eye_y": 92, "eye_dx": 40, "eye_r": 22, "pupil_r": 8, "pupil_r_hot": 5,
    "mouth_dy": 62, "mouth_base": 21, "mouth_box": 85,
    "m_lvl": 4, "m_hitw": 2, "m_hnum": 10, "m_hith": 2,
    "clap": False, "info_top": False,
    "hand_x": 214, "hand_top": 40, "hand_up_y": 52, "hand_tap_y": 96,
    "pad_x": 216, "pad_w": 96, "pad_h": 26, "pad_dy": 62,
}
_SQUARE = {
    # flatter than the wide face: the eyes and the mouth pull together so the
    # whole head reads as one wide shape with the hands under it, instead of
    # a tall one that crowds them
    "face_cx": 120, "half_w": 112, "top": 26, "bot": 138,
    "eye_y": 62, "eye_dx": 42, "eye_r": 22, "pupil_r": 8, "pupil_r_hot": 5,
    "mouth_dy": 38, "mouth_base": 21, "mouth_box": 60,
    "m_lvl": 5, "m_hitw": 1, "m_hnum": 6, "m_hith": 1,
    "clap": True, "info_top": True,
    # the clap: hands `travel` px in from `rest` as the hit decays to nothing
    "clap_y": 140, "clap_w": 60, "clap_rest": 22, "clap_travel": 36,
    "pad_x": 12, "pad_w": 216, "pad_h": 12, "pad_dy": 32,
}

lcd = None
W = H = 0
FONT = None
FONT_H = 0
G = _WIDE                        # the live geometry

FACE_CX = FACE_HALF_W = FACE_TOP = FACE_BOT = 0
EYE_Y = EYE_DX = EYE_R = MOUTH_DY = 0
HAND_X = PAD_X = PAD_Y = PAD_W = PAD_H = 0
HAND_UP_Y = HAND_TAP_Y = 0

_hand_up = None
_hand_tap = None
_clap_l = None
_clap_r = None
CLAP_H = 62
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
    global lcd, W, H, FONT, FONT_H, G
    global FACE_CX, FACE_HALF_W, FACE_TOP, FACE_BOT
    global EYE_Y, EYE_DX, EYE_R, MOUTH_DY
    global HAND_X, PAD_X, PAD_Y, PAD_W, PAD_H, HAND_UP_Y, HAND_TAP_Y
    global _hand_up, _hand_tap, _clap_l, _clap_r, CLAP_H

    lcd = BOARD.lcd
    W = lcd.width()
    H = lcd.height()
    G = _WIDE if W >= 300 else _SQUARE

    FACE_CX = G["face_cx"]
    FACE_HALF_W = G["half_w"]
    FACE_TOP = G["top"]
    FACE_BOT = G["bot"]
    EYE_Y = G["eye_y"]
    EYE_DX = G["eye_dx"]
    EYE_R = G["eye_r"]
    MOUTH_DY = G["mouth_dy"]
    HAND_X = G.get("hand_x", 0)
    HAND_UP_Y = G.get("hand_up_y", 0)
    HAND_TAP_Y = G.get("hand_tap_y", 0)
    PAD_X = G["pad_x"]
    PAD_W = G["pad_w"]
    PAD_H = G["pad_h"]
    PAD_Y = H - G["pad_dy"]

    FONT = getattr(lcd.FONTS, "DejaVu12", None) or lcd.FONTS.DejaVu9
    lcd.setFont(FONT)
    try:
        FONT_H = lcd.fontHeight() or 16
    except Exception:
        FONT_H = 16
    if G["clap"]:
        _clap_l = _load("clap_l.png")
        _clap_r = _load("clap_r.png")
    else:
        _hand_up = _load("hand_up.png")
        _hand_tap = _load("hand_tap.png")
    _last.clear()


def repaint():
    """Wipe and forget: the next draw() rebuilds every element. Used after
    a palette change, where the accent moves under everything at once."""
    _last.clear()
    lcd.fillScreen(C.BG)


def _mouth(cx, my, half_w, half_h):
    lcd.fillCircle(cx - half_w, my, half_h, C.FG)
    lcd.fillCircle(cx + half_w, my, half_h, C.FG)
    lcd.fillRect(cx - half_w, my - half_h, 2 * half_w, 2 * half_h + 1, C.FG)


def draw_face(dx, dy, scale, lid, gaze):
    """Pose changes repaint the whole face zone; a mouth-only change (the
    loudness breathing between beats) repaints just the mouth's own box —
    a full-zone fill per 1 px of mouth is what dragged the loop to 3 fps."""
    cx = FACE_CX + dx
    my = EYE_Y + MOUTH_DY * scale // 100 + dy
    half_w = (G["mouth_base"] + (S.level >> G["m_lvl"])
              + S.hit * G["m_hitw"]) * scale // 100
    half_h = 3 + (S.level * G["m_hnum"] >> 8) + S.hit * G["m_hith"]
    pose = (dx, dy, scale, lid, gaze)
    mouth = (my, half_w, half_h)

    if _changed("pose", pose):
        _last["mouth"] = mouth
        lcd.fillRect(FACE_CX - FACE_HALF_W, FACE_TOP,
                     2 * FACE_HALF_W, FACE_BOT - FACE_TOP, C.BG)
        edx = EYE_DX * scale // 100
        r = EYE_R * scale // 100
        ey = EYE_Y + dy
        for side in (-1, 1):
            ex = cx + side * edx
            if lid:
                lcd.fillRect(ex - r, ey - 2, 2 * r, 4, C.FG)
            else:
                lcd.fillCircle(ex, ey, r, C.FG)
                # excited faces stare harder
                pr = G["pupil_r"] if scale < 104 else G["pupil_r_hot"]
                lcd.fillCircle(ex + gaze, ey + 2, pr, C.INK)
        _mouth(cx, my, half_w, half_h)
    elif _changed("mouth", mouth):
        box = G["mouth_box"]                   # worst capsule half-extent
        top = EYE_Y + MOUTH_DY * scale // 100 - 30 + dy
        # never past the face zone's own floor: below it is the pad, which
        # this path does not redraw, so a taller box would eat a hole in it
        bot = top + 62
        if bot > FACE_BOT:
            bot = FACE_BOT
        lcd.fillRect(cx - box, top, 2 * box, bot - top, C.BG)
        _mouth(cx, my, half_w, half_h)


def _sparks(corners):
    """A strong hit throws sparks off the pad."""
    for bx, by in corners:
        lcd.fillRect(bx, by, 6, 6, S.accent)


def draw_clap(burst):
    """Two palms, driven together by the hit and springing apart after it.

    The travel is the hit's own decay, so the clap lands on the beat and
    opens over the same ~200 ms the face's pop takes — one motion, read two
    ways. The strike itself is the only accent up here: a flash between the
    palms, and sparks when the hit was a strong one."""
    reach = S.hit * G["clap_travel"] // C.HIT_MAX
    # 3 px buckets: the hands must not repaint for sub-pixel jitter
    reach = (reach // 3) * 3
    if not _changed("clap", (reach, burst)):
        return
    y = G["clap_y"]
    cw = G["clap_w"]
    lx = G["clap_rest"] + reach
    rx = W - G["clap_rest"] - cw - reach
    lcd.fillRect(0, y - 6, W, CLAP_H + 12, C.BG)
    if _clap_l is not None:
        lcd.drawPng(_clap_l, lx, y)
        lcd.drawPng(_clap_r, rx, y)
    if rx - (lx + cw) < 8:             # contact: the strike itself
        # a clap is a sound, and the only way a screen has to say so is to
        # throw something off the point of impact — short accent strokes
        # radiating from between the palms, longer when the hit was strong
        cx = (lx + cw + rx) // 2
        my = y + CLAP_H // 2
        near, far = (10, 26) if burst else (8, 18)
        for ex, ey in ((0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)):
            lcd.drawLine(cx + ex * near, my + ey * near,
                         cx + ex * far, my + ey * far, S.accent)
        if burst:
            _sparks(((cx - 3, my - far - 10), (cx - 3, my + far + 4),
                     (cx - far - 10, my - 3), (cx + far + 4, my - 3)))


def draw_bar(tap):
    """The accent's home between beats: the drum pad's job and the LED VU's,
    on a board that has neither. 8 px buckets, so room jitter cannot make it
    repaint."""
    lit = PAD_W if tap else (S.level * PAD_W // (C.LEVEL_MAX + 1) // 8) * 8
    if not _changed("bar", lit):
        return
    lcd.fillRoundRect(PAD_X, PAD_Y, PAD_W, PAD_H, 5, S.accent_deep)
    if lit:
        lcd.fillRoundRect(PAD_X, PAD_Y, lit, PAD_H, 5, S.accent)


def draw_hand(tap, burst):
    """The wide panel's single hand over its pad."""
    if not _changed("hand", (tap, burst)):
        return
    if _hand_up is None:
        return
    top = G["hand_top"]
    lcd.fillRect(HAND_X, top, W - HAND_X, PAD_Y + PAD_H + 6 - top, C.BG)
    # the pad lights while the hand is down
    lcd.fillRoundRect(PAD_X, PAD_Y, PAD_W, PAD_H, 8,
                      S.accent if tap else S.accent_deep)
    if tap:
        lcd.drawPng(_hand_tap, HAND_X + 3, HAND_TAP_Y)
        if burst:
            _sparks(((PAD_X - 8, PAD_Y - 6), (PAD_X + PAD_W + 2, PAD_Y - 6),
                     (PAD_X - 6, PAD_Y + PAD_H), (PAD_X + PAD_W, PAD_Y + PAD_H)))
    else:
        lcd.drawPng(_hand_up, HAND_X + 3, HAND_UP_Y)


def draw_info(now):
    """The bottom line: what the ears are doing, and the tempo they found.

    A palette change borrows the left slot for a moment — the name is the
    only way to know which colour you just landed on without waiting for a
    beat to light the pad."""
    naming = S.palette_shown and now < S.palette_shown
    left = S.palette_name if naming else S.mode_word
    bpm = "%d BPM" % S.bpm if (S.grooving and S.bpm) else ""
    if not _changed("info", (left, bpm, naming)):
        return
    lcd.setFont(FONT)
    y = 6 if G["info_top"] else H - FONT_H - 8
    lcd.fillRect(0, y, W, FONT_H, C.BG)
    lcd.setTextColor(S.accent if naming else C.DIM, C.BG)
    lcd.drawString(left, 10, y)
    if bpm:
        lcd.setTextColor(S.accent, C.BG)
        lcd.drawString(bpm, PAD_X + PAD_W - lcd.textWidth(bpm), y)


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
    tap = 1 if S.hit > C.HIT_MAX // 2 else 0
    burst = 1 if (S.hit and S.hit_intensity >= 3) else 0
    if G["clap"]:
        draw_clap(burst)
        draw_bar(tap)
    else:
        draw_hand(tap, burst)
    draw_info(now)
