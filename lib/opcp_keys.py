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
        S.dirty_body = True
        return

    ch = chr(code) if 0x20 <= code <= 0x7E else ""
    if not ch:
        return

    # The control layer: held ctrl turns the letters back into functions.
    # is_key_pressed reads the driver's cached pressed-key table, so this is
    # a dict lookup, not an I2C transaction; a keyboard without the API (the
    # plain Cardputer's) just never reports ctrl.
    try:
        ctrl = S.kb.is_key_pressed(C.KEY_CTRL)
    except Exception:
        ctrl = False

    if ctrl:
        if ch == "g":
            Q.generate()
            S.set_status("GEN")
        elif ch == "c":
            Q.clear_track()
            S.set_status("CLEAR")
        elif ch == "m":
            S.muted[S.track] = not S.muted[S.track]
            S.set_status("MUTE" if S.muted[S.track] else "UNMUTE")
        elif ch == "p":
            S.pat = (S.pat + 1) % C.PATTERNS
            S.set_hero("BANK", S.pat + 1)
        elif ch == "[":
            S.bpm = max(40, S.bpm - 4)
            S.set_hero("BPM", S.bpm)
        elif ch == "]":
            S.bpm = min(240, S.bpm + 4)
            S.set_hero("BPM", S.bpm)
        elif ch == "f":
            S.view = C.V_FILES
            S.files_arm = False
            S.set_status("FILES")
            S.dirty_all = True
        elif ch == "n":
            S.link_on = not S.link_on
            if S.link_on:
                import opcp_link as L
                S.set_status("LINK ON" if L.begin() else "LINK FAIL")
            else:
                S.set_status("LINK OFF")
        else:
            return                           # ctrl+anything else is swallowed
        if ch in "gcmp":
            S.dirty_body = True
        return

    if ch == "\\":
        S.view = (S.view + 1) % len(C.VIEW_NAMES)
        S.files_arm = False
        S.set_status(C.VIEW_NAMES[S.view])
        S.dirty_all = True
        return

    if S.view == C.V_HELP:                   # help is a poster, not a mode
        return

    if S.view == C.V_FILES:
        i = C.STEP_KEYS_A.find(ch)           # the slot digits are the step row
        if i >= 0:
            if S.files_arm:
                S.files_arm = False
                Q.save_slot(i)
            else:
                Q.load_slot(i)
            S.dirty_body = True
            return
        if ch in C.PRESET_KEYS:
            if not S.files_arm:
                Q.load_preset(C.PRESET_KEYS.index(ch))
                S.dirty_body = True
            return
        if ch == "s":
            S.files_arm = not S.files_arm
            S.set_status("SAVE 1-8?" if S.files_arm else "FILES")
            S.dirty_body = True
            return
        if ch != " ":
            return
        # SPACE falls through to the transport: audition presets in place

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
    elif ch == ".":
        S.track = (S.track - 1) % C.TRACKS
        S.clear_flashes()
    elif ch == "/":
        S.track = (S.track + 1) % C.TRACKS
        S.clear_flashes()
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
    # tempo / octave / scale / swing / volume touch nothing but the footer, and
    # the loop repaints that on its own when footer_changed() notices.
    if ch in " ./":
        S.dirty_body = True
