# OP-CP — pattern generation, the transport clock, and persistence.

import random
import time

import opcp_audio as A
import opcp_conf as C
import opcp_link as L
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
def slot_path(i):
    return "%s/opcp%d.json" % (S.save_dir, i + 1)


def storage_init(path=None):
    """Prefer the SD card when one is inserted; fall back to /flash.

    Patterns on the card survive a firmware reflash, which /flash does not.
    The Cardputer-ADV TF slot is SPI on sck 40 / miso 39 / mosi 14 / cs 12
    (the official pin map). slot=3, because the display owns SPI2 and slot=2
    fails with ESP_ERR_INVALID_STATE — measured on device, with M5 up.
    UIFlow2 v2.5.0 does not mount the card on its own.

    `path` overrides all of that and names the directory outright, skipping
    the card probe. It exists for hosts: /flash and /sd are real on the board
    and nowhere on a laptop, so without a seam here the whole of save_slot,
    load_slot and the FILES view could only ever fail off hardware — which
    means they could only be tested by flashing, which means they were not
    tested. A simulator that cannot save is not simulating this instrument.
    Nothing on the board passes it.
    """
    import os
    if path is not None:
        try:
            os.mkdir(path)
        except OSError:
            pass                             # already there is the normal case
        S.save_dir = path
        scan_slots()
        return
    try:
        os.listdir("/sd")                    # already mounted (soft reset)
        S.save_dir = "/sd"
    except Exception:
        try:
            import machine
            os.mount(machine.SDCard(slot=3, width=1, sck=40, miso=39, mosi=14,
                                    cs=12, freq=20000000), "/sd")
            S.save_dir = "/sd"
        except Exception:
            S.save_dir = "/flash"            # no card is not an error

    # one-time migration: the single-file era's opcp.json becomes slot 1
    try:
        legacy = S.save_dir + "/opcp.json"
        os.stat(legacy)
        try:
            os.stat(slot_path(0))
        except OSError:
            os.rename(legacy, slot_path(0))
    except OSError:
        pass
    scan_slots()


def scan_slots():
    """Refresh the FILES view's cache of what lives in each slot."""
    import json
    for i in range(C.SLOTS):
        try:
            with open(slot_path(i)) as f:
                d = json.load(f)
            S.slot_meta[i] = (d.get("bpm", 0), d.get("scale", 0))
        except Exception:
            S.slot_meta[i] = None


def save_slot(i):
    # set_status, not a bare S.status assignment: without the timestamp the
    # header never shows the word and saving looks like nothing happened
    try:
        import json
        with open(slot_path(i), "w") as f:
            json.dump({"v": 2, "pat": S.patterns, "bpm": S.bpm,
                       "scale": S.scale_i, "root": S.root, "oct": S.octave}, f)
        S.slot_meta[i] = (S.bpm, S.scale_i)
        S.set_status("SAVED %d" % (i + 1))
    except Exception:
        S.set_status("SAVE FAIL")


def load_slot(i):
    import json
    try:
        with open(slot_path(i)) as f:
            d = json.load(f)
    except Exception:
        S.set_status("NO SAVE")
        return
    if d.get("v") != 2:
        S.set_status("OLD SAVE")
        return
    S.patterns = d["pat"]
    S.bpm = d["bpm"]
    S.scale_i = d["scale"]
    S.root = d["root"]
    S.octave = d["oct"]
    S.set_status("LOADED %d" % (i + 1))


def load_preset(n):
    """Drop a factory pattern into the CURRENT bank; storage is untouched."""
    name, bpm, sc, oc, tracks = C.PRESETS[n]
    pat = S.patterns[S.pat]
    for t in range(C.TRACKS):
        pat[t][:] = list(tracks[t])
    S.bpm = bpm
    S.scale_i = sc
    S.octave = list(oc)
    S.set_status(name)


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

    hits = 0
    drum = 255
    for t in range(C.TRACKS):
        v = S.patterns[S.pat][t][S.play_step]
        if v is not None and not S.muted[t]:
            S.hit[t] = C.HIT_MAX
            hits |= 1 << t
            if t != 3:
                S.last_semi = v
            else:
                drum = v % len(C.DRUMS)
        A.voice(t, v, spread=t * C.SPREAD_MS)
    if S.link_on:
        L.send_step(S.play_step, hits, drum)   # sound first, then the word

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
    if S.link_on:
        L.send_transport(True)


def stop():
    S.playing = False
    S.recording = False
    S.clear_flashes()
    if S.link_on:
        L.send_transport(False)
