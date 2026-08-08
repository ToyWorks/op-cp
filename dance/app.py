# SCD — StackChan Dance: the OP-CP sequencer's dance partner.
#
# The Cardputer across the desk plays; this board listens with its own
# microphone, finds the beat in what it hears, and dances. Sound is the whole
# protocol: no radio, no pairing, no clock to share. Anything rhythmic works,
# the OP-CP kit just happens to live on the same desk.
#
#   mic -> scd_board (energy frames)
#       -> scd_beat  (pure onset/tempo logic, host-testable)
#       -> scd_face  (the face), scd_board (whatever body there is)
#
# This file is only the lifecycle, and it is the same on both machines.
# Which machine it is, is decided at deploy time, not here: `make BOARD=...`
# copies one of boards/*/scd_board.py to the device as scd_board.py, and
# that module answers for the screen, the microphone, the buttons and the
# body. Nothing in this file tests which board it is running on.
#
# Import direction, strictly one way:
#   scd_conf <- scd_state <- scd_board / scd_beat / scd_face <- here

import time

import M5

import scd_board as BOARD
import scd_conf as C
import scd_face as F
import scd_link as L
from scd_beat import B
from scd_state import S


def setup():
    M5.begin()
    BOARD.begin()           # screen, microphone, buttons, body
    F.layout()
    F.repaint()

    now = time.ticks_ms()
    S.breath0 = now
    S.next_blink = now + 1200
    L.begin()               # optional radio: the mic remains the fallback
    F.draw(now)


def _palette(step, now):
    """Walk the accent colour. The accent means 'the music' and nothing
    else, so moving it moves every lit thing at once — hence the full
    repaint rather than a patch."""
    n = len(C.PALETTE)
    S.palette = (S.palette + step) % n
    name, lit, deep = C.PALETTE[S.palette]
    S.accent, S.accent_deep = lit, deep
    S.palette_name = name
    S.palette_shown = time.ticks_add(now, C.PALETTE_NAME_MS)
    F.repaint()


def _beat(now, intensity):
    """One beat, however it was heard: the face pops, the body marks it."""
    S.beat_n += 1
    S.last_beat = now
    S.grooving = True
    S.hit = C.HIT_MAX
    S.hit_intensity = intensity
    if S.rand() % 8 != 0:              # 1-in-8: hit the same side again
        S.side = -S.side
    BOARD.on_beat(now, intensity)


def loop():
    M5.update()
    now = time.ticks_ms()

    toggle, step, still = BOARD.poll_input(now)
    if toggle:
        S.link_enabled = not S.link_enabled
    if step:
        _palette(step, now)
    if still:
        S.still = not S.still
        if S.still:
            BOARD.rest()      # settle where it is and drop torque — quiet

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
        _beat(now, intensity)

    if not linked:
        rms = BOARD.mic_poll()
        if rms is not None:
            intensity = B.feed(rms, now)
            if intensity:
                _beat(now, intensity)

    if S.grooving and time.ticks_diff(now, S.last_beat) > C.SILENCE_MS:
        S.grooving = False
        S.breath0 = now
        S.hit = 0
        S.level = 0
    if not S.grooving and BOARD.resting_due(now):
        BOARD.rest()

    BOARD.tick(now)

    if time.ticks_diff(now, S.next_anim) >= 0:
        S.next_anim = time.ticks_add(now, C.ANIM_MS)
        S.mode_word = "STILL" if S.still else \
            (("LINK" if linked else "DANCE") if S.grooving else
             ("LISTEN" if S.link_enabled else "MIC ONLY"))
        F.draw(now)
        # Decay AFTER drawing. Decaying first meant the peak of every hit was
        # computed and then thrown away unseen: the largest S.hit ever rendered
        # was HIT_MAX - 1, so the clapping hands stopped 16 px short of each
        # other and never once touched on the device — while the simulator,
        # which sets S.hit directly, showed them meeting.
        if S.hit:
            S.hit -= 1        # one step per frame: a ~200 ms pop, every time
        if linked and S.level:
            S.level -= (S.level >> 3) + 1   # packet mode decays its own level

    time.sleep_ms(2)


if __name__ == '__main__':
    try:
        setup()
        while True:
            loop()
    except (Exception, KeyboardInterrupt) as e:
        try:
            BOARD.rest()
        except Exception:
            pass
        try:
            from utility import print_error_msg
            print_error_msg(e)
        except ImportError:
            print("please update to latest firmware")
