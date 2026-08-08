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
def poll_input(now):
    """(toggle_link, palette_step) — the shape both boards answer in.

    A pat on the head (the base touchpad, or a tap on the lower screen)
    toggles the ear. This board has no spare control for the palette, so
    the second field is always 0 here."""
    if time.ticks_diff(now, S.next_touch) < 0:
        return (False, 0)
    S.next_touch = time.ticks_add(now, C.TOUCH_POLL_MS)
    t = False
    try:
        ch = MO.chan()
        if ch is not None:
            tp = ch.get_touch()
            t = bool(tp[0] or tp[1] or tp[2])
    except Exception:
        pass
    if not t:
        try:
            t = M5.BtnA.wasClicked() or M5.BtnB.wasClicked() \
                or M5.BtnC.wasClicked()
        except Exception:
            pass
    if t and now > S.touch_hold:
        S.touch_hold = now + C.TOUCH_DEBOUNCE_MS
        return (True, 0)
    return (False, 0)


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
