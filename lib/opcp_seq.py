# OP-CP — pattern generation, the transport clock, and persistence.

import random
import time

import opcp_audio as A
import opcp_conf as C
import opcp_screen as SC
import opcp_ui as U
from opcp_state import S


# ------------------------------------------------------------------ musical
def generate():
    """Fill the current track with something playable rather than random.

    PERC gets a real backbeat; BASS lands on beats and resets to the root each
    half bar; the melodic tracks walk the scale by small steps. Pure randomness
    sounds like pure randomness.
    """
    st = S.steps()
    for i in range(C.STEPS):
        st[i] = None
    if S.track == 3:
        for i in range(C.STEPS):
            if i % 4 == 0:
                st[i] = 0
            elif i % 8 == 4:
                st[i] = 1
            elif random.getrandbits(3) > 4:
                st[i] = 2 if random.getrandbits(2) else 3
        return
    sc = C.SCALES[S.scale_i][1]
    n = len(sc)
    deg = 0
    density = 5 if S.track == 1 else 6
    for i in range(C.STEPS):
        if S.track == 1 and i % 4 != 0 and random.getrandbits(3) < 6:
            continue
        if random.getrandbits(3) < density:
            deg = max(0, min(n + 4, deg + random.getrandbits(2) - 1))
            if S.track == 1 and i % 8 == 0:
                deg = 0
            st[i] = sc[deg % n] + 12 * (deg // n)


def clear_track():
    st = S.steps()
    for i in range(C.STEPS):
        st[i] = None


# ------------------------------------------------------------------ storage
def save():
    try:
        import json
        with open(C.SAVE_PATH, "w") as f:
            json.dump({"v": 2, "pat": S.patterns, "bpm": S.bpm,
                       "scale": S.scale_i, "root": S.root, "oct": S.octave}, f)
        S.status = "saved"
    except Exception:
        S.status = "save failed"


def load():
    try:
        import json
        with open(C.SAVE_PATH) as f:
            d = json.load(f)
        if d.get("v") != 2:
            S.status = "old save"
            return
        S.patterns = d["pat"]
        S.bpm = d["bpm"]
        S.scale_i = d["scale"]
        S.root = d["root"]
        S.octave = d["oct"]
        S.status = "loaded"
    except Exception:
        S.status = "no save"


# ------------------------------------------------------------------ transport
def step_interval():
    return 60000.0 / (S.bpm * 4)


def schedule_next():
    iv = step_interval()
    if S.swing:
        iv *= ((1.0 - C.SWING_PCT / 100.0) if (S.play_step % 2)
               else (1.0 + C.SWING_PCT / 100.0))
    S.next_tick = time.ticks_add(S.next_tick, int(iv))


def advance():
    """One sixteenth: sound every track's step, then repaint what moved."""
    prev = S.play_step
    S.play_step = (S.play_step + 1) % C.STEPS

    # decide the whole step's channel budget before any of it sounds
    chs = []
    for t in range(C.TRACKS):
        chs.extend(A.voices_for(t, S.patterns[S.pat][t][S.play_step]))
    A.balance(chs)

    for t in range(C.TRACKS):
        v = S.patterns[S.pat][t][S.play_step]
        if v is not None and not S.muted[t]:
            S.hit[t] = C.HIT_MAX
            if t != 3:
                S.last_semi = v
        A.voice(t, v, spread=t * C.SPREAD_MS)

    if S.steps()[S.play_step] is not None:
        S.flash[S.play_step] = C.FLASH_MAX
    if S.view == C.V_ROLL:
        U.draw_step(prev)
        U.draw_step(S.play_step)
    else:
        SC.draw_cartoon()
    schedule_next()


def decay_flashes():
    now = time.ticks_ms()
    if time.ticks_diff(now, S.next_flash) < 0:
        return
    S.next_flash = time.ticks_add(now, C.FLASH_MS)
    if S.view != C.V_ROLL:
        return
    for i in range(C.STEPS):
        if S.flash[i] > 0:
            S.flash[i] -= 1
            U.draw_step(i)


def quantized_step():
    """Which step a live-recorded note belongs to — nearest, not floor."""
    rem = time.ticks_diff(S.next_tick, time.ticks_ms())
    if rem < step_interval() / 2:
        return (S.play_step + 1) % C.STEPS
    return S.play_step


def start(from_step=None):
    S.playing = True
    S.play_step = C.STEPS - 1 if from_step is None else from_step
    S.next_tick = time.ticks_ms()


def stop():
    S.playing = False
    S.recording = False
    S.clear_flashes()
