# OP-CP — the surface an outside program is allowed to drive.
#
# Everything here is something op-cp already did; nothing here is new
# behaviour. What is new is that it has a NAME. Before this module the only
# statement of "what can be driven from outside" was 95 references to
# S.pat, Q.stop, C.VOLS and friends, spread through a caller's source — so
# op-cp could not tell which of its internals were load-bearing for somebody
# else, and a caller could not tell which were safe to touch. Two of them
# were not: the tiny-MHS layer was assigning A.TRIM and C.CH_TRIM, module
# constants in a file whose own docs say "no state". set_track_trim() is
# where that belongs.
#
# This module does NOT import anything above op-cp and knows nothing about
# who is calling. It is a lens on op-cp's own state in op-cp's own words —
# "the volume moved", not "mix.master_gain changed". Whoever is driving is
# responsible for translating that into their own vocabulary.
#
# Layering: sits beside opcp_keys, one above the sequencer. The human's
# keyboard and an outside program are siblings, and this is the sibling's
# door.

import opcp_audio as A
import opcp_conf as C
import opcp_seq as Q
from opcp_state import S


# ------------------------------------------------------------------ reading

def transport():
    return {"playing": S.playing, "step": S.play_step,
            "bpm": S.bpm, "swing": S.swing}


def pattern():
    return {"bank": S.pat, "banks": C.PATTERNS, "steps": C.STEPS,
            "chain": S.chain}


def steps(bank=None, track=None):
    """One track of one bank, as a list. Defaults to what is selected."""
    b = S.pat if bank is None else bank
    t = S.track if track is None else track
    return S.patterns[b][t]


def music():
    return {"root": S.root, "scale": C.SCALES[S.scale_i][0],
            "octaves": list(S.octave)}


def mix():
    """Per-track mutes, and where the volume key currently stands.

    `volume` is the index into the ladder, `gain` the fraction of full scale
    it means. Index 0 is silence — the instrument can be muted from its own
    keyboard, and a caller that reports otherwise is lying about a room.
    """
    return {"muted": list(S.muted), "volume": S.vol_i,
            "steps": len(C.VOLS),
            "gain": C.VOLS[S.vol_i] / float(C.VOLS[-1])}


def storage():
    """Where saves land, and which slots hold one.

    `where` is decided once at startup and does not change if a card is
    inserted later — worth reporting, because /flash does not survive a
    firmware reflash and the card does.
    """
    return {"where": S.save_dir, "slots": C.SLOTS,
            "used": [i + 1 for i, m in enumerate(S.slot_meta) if m]}


def slot(n):
    """What save slot `n` holds, or None if it is empty. 1-based, matching
    the keys on the device.

    The tempo comes back with it because "this slot is taken" is not enough
    to decide with: a caller about to overwrite somebody's work can say
    which work, and there is no undo.
    """
    i = n - 1
    m = S.slot_meta[i] if 0 <= i < len(S.slot_meta) else None
    if m is None:
        return None
    return {"bpm": m[0], "scale": m[1]}


def audio():
    """Whether this instrument currently sounds like itself.

    kit false means the PCM kit did not fit and op-cp fell back to square
    waves: same pitches, same timing, every other reading still correct.
    Nothing else reports it.
    """
    return {"kit": A.kit_ok, "note": getattr(A, "kit_note", ""),
            "link": bool(S.link_on)}


def styles():
    return [p[0] for p in C.PRESETS]


# ------------------------------------------------------------------ writing
# Nothing here validates a range: op-cp's own keys do not either, and a
# caller that needs bounds has a table of its own to enforce them in. What
# these DO own is the mechanism — which fields move together, and what has
# to be marked dirty so the screen agrees with the sound.

def set_bpm(bpm):
    S.bpm = bpm
    S.set_hero("BPM", bpm)


def set_swing(on):
    S.swing = bool(on)


def set_bank(bank):
    """Select a bank by hand. Ends chaining, because asking for a bank
    means that bank — the same rule ctrl+P follows."""
    S.pat = bank
    S.chain = False


def set_chain(on):
    S.chain = bool(on)


def set_mute(track, muted):
    S.muted[track] = bool(muted)


def set_track_trim(track, gain):
    """Per-track gain in the mixer.

    balance() consults trim_for(channel) on every step and channel N is
    track N, so replacing the trim is the whole mechanism. Two tables move
    together: A.TRIM is what the PCM path reads, C.CH_TRIM what the tone()
    fallback reads. They were being assigned from outside op-cp, which meant
    the caller had to know both — including that one of them is a dict in
    the constants module. It is this module's job to know that instead.
    """
    A.set_trim(track, gain)


def set_steps(bank, track, values):
    """Write sixteen steps. `values` is a list of ints and Nones."""
    S.patterns[bank][track][:] = values
    S.dirty_body = True


def redraw():
    """Ask for the roll to be repainted on the next frame."""
    S.dirty_body = True


# ------------------------------------------------------------------ doing

def start():
    Q.start()


def stop():
    Q.stop()


def generate(track=None):
    """Re-roll one track with op-cp's own generator, leaving the selected
    track where it was."""
    if track is None:
        Q.generate()
        return
    prev, S.track = S.track, track
    try:
        Q.generate()
    finally:
        S.track = prev


def load_style(name, bank=None):
    """Drop a factory pattern into a bank. Returns False for a name op-cp
    does not have — it cannot invent one."""
    names = styles()
    if name not in names:
        return False
    prev = S.pat
    if bank is not None:
        S.pat = bank
    try:
        Q.load_preset(names.index(name))
    finally:
        S.pat = prev if bank is not None else S.pat
    S.dirty_body = True
    return True


def save(slot):
    """Write a slot, 1-based. Returns True only if the file is there
    afterwards — Q.save_slot reports failure by painting the screen, which
    serves the person holding the device and tells a program nothing."""
    i = slot - 1
    Q.save_slot(i)
    return S.slot_meta[i] is not None


def load(slot):
    """Read a slot, 1-based. False when it is empty; Q.load_slot's own
    answer to that is a status line, for the same reason."""
    i = slot - 1
    if S.slot_meta[i] is None:
        return False
    Q.load_slot(i)
    S.dirty_body = True
    S.set_hero("BPM", S.bpm)
    return True


# ------------------------------------------------------------------ changes
# The keyboard and an outside program are siblings, and only one of them
# reports what it did. Without this, anything watching op-cp has to
# hand-write a comparison per field, and the failure is silent and
# characteristic: somebody adds a key, forgets the mirror, and a reading
# quietly disagrees with the instrument. That happened twice here — a muted
# device that still read as audible, and ctrl+S moving the banks with
# nothing in the log.
#
# WATCHED is the list, so adding a field is one entry rather than one more
# method somebody has to remember to write.

WATCHED = ("volume", "bank", "chain", "bpm", "swing", "playing", "muted")


def snapshot():
    return (S.vol_i, S.pat, S.chain, S.bpm, S.swing, S.playing,
            tuple(S.muted))


def changes(prev):
    """What moved since `prev`, and a fresh snapshot to keep.

    Returns (names, snapshot). The caller holds the snapshot rather than
    this module, so two watchers cannot steal each other's changes — and
    the first call, with prev None, reports nothing rather than everything.
    """
    now = snapshot()
    if prev is None:
        return (), now
    moved = []
    for i in range(len(WATCHED)):
        if prev[i] != now[i]:
            moved.append(WATCHED[i])
    return tuple(moved), now
