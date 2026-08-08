# SCD — StackChan Dance: the OP-CP sequencer's dance partner.
#
# The Cardputer across the desk plays; this CoreS3 on a StackChan base
# listens with its own microphone, finds the beat in what it hears, and
# dances — face, two servos, twelve LEDs. Sound is the whole protocol:
# no radio, no pairing, no clock to share. Anything rhythmic works, the
# OP-CP kit just happens to live on the same desk.
#
#   mic -> scd_mic (32 ms energy frames)
#       -> scd_beat (pure onset/tempo logic, host-testable)
#       -> scd_face (the face), scd_motion (servos + LEDs)
#
# This file is only the lifecycle, same contract as the Cardputer app:
# everything else lives in lib/, deployed flat next to main.py.
#
# Import direction, strictly one way:
#   scd_conf <- scd_state <- scd_beat / scd_mic / scd_face / scd_motion <- here

import time

import M5

import scd_conf as C
import scd_face as F
import scd_link as L
import scd_mic as MIC
import scd_motion as MO
from scd_beat import B
from scd_state import S


def setup():
    M5.begin()
    F.layout()
    M5.Lcd.fillScreen(C.BG)
    try:
        M5.Lcd.setBrightness(160)
    except Exception:
        pass

    MIC.begin()
    MO.begin()          # optional hardware: face still dances without a base
    L.begin()           # optional radio: mic remains the fallback

    now = time.ticks_ms()
    S.breath0 = now
    S.next_blink = now + 1200
    F.draw(now)


def _touch(now):
    """A pat on the head (base touchpad or a screen tap) toggles the ear."""
    if time.ticks_diff(now, S.next_touch) < 0:
        return
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
        S.link_enabled = not S.link_enabled


def loop():
    M5.update()
    now = time.ticks_ms()
    _touch(now)

    # packets first; the microphone only works when the radio is silent
    intensity = L.poll(now)
    linked = L.fresh(now)
    if S.link_stop:
        S.link_stop = False
        S.grooving = False
        S.breath0 = now
        S.hit = 0
        S.level = 0
    if intensity:
        S.beat_n += 1
        S.last_beat = now
        S.grooving = True
        MO.on_beat(now, intensity)

    if not linked:
        rms = MIC.poll()
        if rms is not None:
            intensity = B.feed(rms, now)
            if intensity:
                S.beat_n += 1
                S.last_beat = now
                S.grooving = True
                MO.on_beat(now, intensity)

    if S.grooving and time.ticks_diff(now, S.last_beat) > C.SILENCE_MS:
        S.grooving = False
        S.breath0 = now
        S.hit = 0
        S.level = 0
    if not S.grooving and S.servo_awake and \
            time.ticks_diff(now, S.last_beat) > C.SERVO_REST_MS:
        MO.rest()

    MO.tick(now)
    MO.leds(now)

    if time.ticks_diff(now, S.next_anim) >= 0:
        S.next_anim = time.ticks_add(now, C.ANIM_MS)
        if S.hit:
            S.hit -= 1        # one step per frame: a ~200 ms pop, every time
        if linked and S.level:
            S.level -= (S.level >> 3) + 1   # packet mode decays its own level
        S.mode_word = ("LINK" if linked else "DANCE") if S.grooving else \
            ("LISTEN" if S.link_enabled else "MIC ONLY")
        F.draw(now)

    time.sleep_ms(2)


if __name__ == '__main__':
    try:
        setup()
        while True:
            loop()
    except (Exception, KeyboardInterrupt) as e:
        try:
            MO.rest()
        except Exception:
            pass
        try:
            from utility import print_error_msg
            print_error_msg(e)
        except ImportError:
            print("please update to latest firmware")
