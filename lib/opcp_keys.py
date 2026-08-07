# OP-CP — the keyboard: one dispatch table's worth of bindings.
#
# Every branch that changes a parameter also claims the hero slot, so the value
# you just changed becomes the big number for a moment. That is the whole
# interaction model; keep it when adding bindings.

import opcp_audio as A
import opcp_conf as C
import opcp_screen as SC
import opcp_seq as Q
import opcp_ui as U
from opcp_state import S


def play_note(semi):
    """Sound a note, and write it to the step the transport says we are on."""
    live = A.voices_for(S.track, semi)
    if S.playing:
        chs = list(live)
        for t in range(C.TRACKS):
            if t != S.track:
                chs.extend(A.voices_for(t, S.patterns[S.pat][t][S.play_step]))
        A.balance(chs)
    else:
        A.balance(live)        # nothing else sounding — give it everything

    S.hit[S.track] = C.HIT_MAX
    if S.track != 3:
        S.last_semi = semi
    if S.view not in (C.V_ROLL, C.V_HELP):
        SC.draw_cartoon()
    A.voice(S.track, semi)

    if S.playing and S.recording:
        i = Q.quantized_step()
        S.steps()[i] = semi
        S.flash[i] = C.FLASH_MAX
        if S.view == C.V_ROLL:
            U.draw_step(i)
    elif not S.playing:
        S.steps()[S.cursor] = semi
        S.flash[S.cursor] = C.FLASH_MAX
        if S.view == C.V_ROLL:
            U.draw_step(S.cursor)

    S.set_hero("NOTE", U.step_label(S.track, semi))
    if S.view == C.V_ROLL:
        U.draw_footer()


def _toggle_step(i):
    old = S.cursor
    S.cursor = i
    st = S.steps()
    st[i] = None if st[i] is not None else 0
    if st[i] is not None:
        A.voice(S.track, st[i])
        S.flash[i] = C.FLASH_MAX
    S.set_hero("STEP %02d" % (i + 1), U.step_label(S.track, st[i]) or "--")
    if S.view == C.V_ROLL:
        U.draw_step(old)
        U.draw_step(i)
        U.draw_footer()


def on_key(_kb):
    try:
        code = S.kb.get_key()
    except Exception:
        return
    if code is None or code < 0:
        return

    if code in (10, 13):                     # ENTER: arm recording
        S.recording = not S.recording
        if S.recording and not S.playing:
            Q.start()
        S.set_status("REC" if S.recording else "ARMED OFF")
        S.dirty_all = True
        return

    ch = chr(code) if 0x20 <= code <= 0x7E else ""
    if not ch:
        return

    if ch == "\\":
        S.view = (S.view + 1) % len(C.VIEW_NAMES)
        S.set_status(C.VIEW_NAMES[S.view])
        S.dirty_all = True
        return

    if S.view == C.V_HELP:                   # help page doubles as save/load
        if ch == "s":
            Q.save()
        elif ch == "l":
            Q.load()
        return

    if ch in C.WHITE_KEYS:
        i = C.WHITE_KEYS.index(ch)
        play_note(i if S.track == 3 else C.WHITE_SEMI[i])
        return
    if ch in C.BLACK_KEYS and S.track != 3:
        play_note(C.BLACK_KEYS[ch])
        return

    if ch in C.STEP_KEYS_A or ch in C.STEP_KEYS_B:
        i = C.STEP_KEYS_A.find(ch)
        _toggle_step(i if i >= 0 else 8 + C.STEP_KEYS_B.find(ch))
        return

    if ch == " ":
        if S.playing:
            Q.stop()
        else:
            Q.start()
        S.set_status("PLAY" if S.playing else "STOP")
    elif ch == "q":
        Q.generate()
        S.set_status("GEN")
    elif ch == "r":
        Q.clear_track()
        S.set_status("CLEAR")
    elif ch == "i":
        S.muted[S.track] = not S.muted[S.track]
        S.set_status("MUTE" if S.muted[S.track] else "UNMUTE")
    elif ch == "'":
        S.pat = (S.pat + 1) % C.PATTERNS
        S.set_hero("PATTERN", S.pat + 1)
    elif ch == ".":
        S.track = (S.track - 1) % C.TRACKS
        S.clear_flashes()
    elif ch == "/":
        S.track = (S.track + 1) % C.TRACKS
        S.clear_flashes()
    elif ch == "[":
        S.bpm = max(40, S.bpm - 4)
        S.set_hero("BPM", S.bpm)
    elif ch == "]":
        S.bpm = min(240, S.bpm + 4)
        S.set_hero("BPM", S.bpm)
    elif ch == "-":
        if S.track != 3:
            S.octave[S.track] = max(-2, S.octave[S.track] - 1)
            S.set_hero("OCT", "%+d" % S.octave[S.track])
    elif ch == "=":
        if S.track != 3:
            S.octave[S.track] = min(2, S.octave[S.track] + 1)
            S.set_hero("OCT", "%+d" % S.octave[S.track])
    elif ch == "`":
        S.scale_i = (S.scale_i + 1) % len(C.SCALES)
        S.set_hero("SCALE", C.SCALES[S.scale_i][0])
    elif ch == "9":
        S.swing = not S.swing
        S.set_status("SWING" if S.swing else "STRAIGHT")
    elif ch == "0":
        A.cycle_volume()
    else:
        return
    S.dirty_all = True
