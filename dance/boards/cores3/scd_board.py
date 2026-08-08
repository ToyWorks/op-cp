# SCD on the M5Stack CoreS3, sitting on a StackChan base.
#
# One of two files with this name — `make BOARD=cores3` deploys this one,
# `make BOARD=cube` deploys boards/cube/scd_board.py instead. app.py, the
# beat detector and the face are identical on both machines; everything
# that is true only of THIS machine is here, written straight, with no
# runtime test for which board it is.
#
# What this machine has: a 320x240 panel, an ES7210 microphone reached
# through M5.Mic, two SCS0009 servos and twelve RGB LEDs on the StackChan
# base, and the base's three-zone touchpad.

import math
import time

import M5

import scd_conf as C
import scd_motion as MO
from scd_state import S

NAME = "cores3"
HAS_BODY = True

# gate: below this the room is just being a room. Tuned on this hardware —
# ambient idles ~40-60, the Cardputer at arm's length peaks in the hundreds.
MIN_RMS = 90

lcd = None
W = H = 0

_bufs = None
_cur = 0
_mic_ok = False


def begin():
    """Screen, microphone, body — in that order, so a base that fails to
    answer still leaves a face on the panel."""
    global lcd, W, H
    lcd = M5.Lcd
    W, H = lcd.width(), lcd.height()
    S.min_rms = MIN_RMS
    lcd.fillScreen(C.BG)
    try:
        lcd.setBrightness(160)
    except Exception:
        pass
    _mic_begin()
    MO.begin()          # optional hardware: the face dances without a base


# ---------------------------------------------------------------- microphone
# M5.Mic.record() fills a buffer over DMA and returns immediately;
# isRecording() goes False when it is full. Two buffers ping-pong so the next
# frame records while this one is measured — at FRAME/RATE that is a fresh
# energy number every ~32 ms, which is all a dancer needs.

def _mic_begin():
    global _bufs, _cur, _mic_ok
    try:
        M5.Mic.begin()
        _bufs = (bytearray(C.FRAME * 2), bytearray(C.FRAME * 2))
        _cur = 0
        M5.Mic.record(_bufs[0], C.RATE, False)
        _mic_ok = True
    except Exception:
        _mic_ok = False


def mic_poll():
    """The finished frame's RMS, or None while the mic is still filling."""
    global _cur
    if not _mic_ok:
        return None
    try:
        if M5.Mic.isRecording():
            return None
    except Exception:
        return None
    done = _bufs[_cur]
    _cur ^= 1
    M5.Mic.record(_bufs[_cur], C.RATE, False)     # keep the stream rolling

    acc = 0
    n = 0
    step = 2 * C.RMS_STRIDE
    for i in range(0, len(done), step):
        v = done[i] | (done[i + 1] << 8)
        if v >= 0x8000:
            v -= 0x10000
        acc += v * v
        n += 1
    return int(math.sqrt(acc // n)) if n else 0


# --------------------------------------------------------------------- input
def _screen_touched():
    """Is a finger on the panel right now?

    M5.update() refreshes the touch controller every loop, so this is a cached
    read, not an I2C transaction — which is why the screen can be polled every
    frame while the base strip below cannot. Guarded because M5.Touch is not on
    every board this firmware family runs on."""
    try:
        return M5.Touch.getCount() > 0
    except Exception:
        try:
            return bool(M5.BtnA.isPressed() or M5.BtnB.isPressed()
                        or M5.BtnC.isPressed())
        except Exception:
            return False


def _strip_touched():
    """Any of the base's three touch zones. A real I2C read — rate-limited."""
    try:
        ch = MO.chan()
        if ch is None:
            return False
        tp = ch.get_touch()
        return bool(tp[0] or tp[1] or tp[2])
    except Exception:
        return False


def poll_input(now):
    """(toggle_link, palette_step, toggle_still) — the shape both boards
    answer in.

    Two surfaces, two gestures:

      screen tap            -> next colour
      base strip, tapped    -> toggle the ear (LISTEN / MIC ONLY)
      base strip, HELD      -> be still: the body stops marking the beat

    A hold fires the moment it crosses HOLD_MS rather than on release, so it
    lands under your finger instead of after it; the release is then swallowed
    so one gesture is never also read as a tap."""
    step = 0
    toggle = False
    still = False

    # -- the screen: cached, so poll it every frame and time the contact
    down = _screen_touched()
    if down and not S.screen_down:
        S.screen_down = now or 1
    elif not down and S.screen_down:
        if time.ticks_diff(now, S.screen_down) <= C.TAP_MAX_MS \
                and now > S.touch_hold:
            S.touch_hold = now + C.TOUCH_DEBOUNCE_MS
            step = 1
        S.screen_down = 0

    # -- the base strip: an I2C read, so keep it to TOUCH_POLL_MS
    if time.ticks_diff(now, S.next_touch) >= 0:
        S.next_touch = time.ticks_add(now, C.TOUCH_POLL_MS)
        held = _strip_touched()
        if held and not S.strip_down:
            S.strip_down = now or 1
            S.strip_fired = False
        elif held and S.strip_down and not S.strip_fired:
            if time.ticks_diff(now, S.strip_down) >= C.HOLD_MS:
                S.strip_fired = True          # fire under the finger, not after
                still = True
        elif not held and S.strip_down:
            if not S.strip_fired and now > S.touch_hold:
                S.touch_hold = now + C.TOUCH_DEBOUNCE_MS
                toggle = True                 # a tap, not a hold
            S.strip_down = 0

    return (toggle, step, still)


# ---------------------------------------------------------------------- body
def on_beat(now, intensity):
    MO.on_beat(now, intensity)


def tick(now):
    MO.tick(now)
    MO.leds(now)


def rest():
    MO.rest()


def resting_due(now):
    """True once the body has been idle long enough to drop its torque."""
    return (S.servo_awake
            and time.ticks_diff(now, S.last_beat) > C.SERVO_REST_MS)
