# OP-CP — the mixer and the voices.
#
# Nothing here draws; nothing here reads the keyboard. The only reason this is
# more than a wrapper around M5.Speaker.tone is the channel budget: see
# balance().

import time

import M5

import opcp_conf as C
from opcp_state import S


def set_ch(ch, vol):
    try:
        M5.Speaker.setChannelVolume(ch, int(vol))
    except Exception:
        pass


def apply_mix():
    try:
        M5.Speaker.setAllChannelVolume(C.MAX_CH_VOL)
    except Exception:
        pass


def voices_for(t, val):
    """Which mixer channels track t will occupy for this value."""
    if val is None or S.muted[t]:
        return ()
    if t == 3:
        return tuple(5 + i for i in range(len(C.DRUMS[val % len(C.DRUMS)][1])))
    if t == 2:
        return (2, 4) if C.FIFTHS else (2,)
    return (t,)


def balance(chs):
    """Share the budget across exactly the voices about to sound.

    One note alone gets the whole 255; a dense step gets divided down. This is
    where the loudness comes from — a fixed safety margin would waste most of
    the range on the sparse steps, which is what most steps are.
    """
    if not chs:
        return
    total = 0.0
    for c in chs:
        total += C.CH_TRIM.get(c, 1.0)
    if total <= 0:
        return
    scale = C.MIX_BUDGET / total
    for c in chs:
        set_ch(c, min(C.MAX_CH_VOL, int(C.CH_TRIM.get(c, 1.0) * scale)))


def _tone(freq, ms, ch, delay=0):
    if delay > 0:
        S.pending.append((time.ticks_add(time.ticks_ms(), delay), freq, ms, ch))
        return
    try:
        M5.Speaker.tone(int(freq), int(ms), ch)
    except Exception:
        try:
            M5.Speaker.tone(int(freq), int(ms))
        except Exception:
            pass


def flush_pending():
    """Emit any tones whose stagger delay has come due."""
    if not S.pending:
        return
    now = time.ticks_ms()
    keep = []
    for item in S.pending:
        if time.ticks_diff(now, item[0]) >= 0:
            _tone(item[1], item[2], item[3])
        else:
            keep.append(item)
    S.pending[:] = keep


def midi_to_hz(n):
    return 440.0 * (2.0 ** ((n - 69) / 12.0))


def semi_to_midi(semi, t):
    return S.root + semi + 12 * S.octave[t]


def gate_ms():
    return max(30, int(60000 / (S.bpm * 4) * 0.7))


def voice(t, val, spread=0):
    """Sound one step of one track."""
    if val is None or S.muted[t]:
        return
    g = gate_ms()
    if t == 3:
        for i, (f, ms) in enumerate(C.DRUMS[val % len(C.DRUMS)][1]):
            _tone(f, ms, 5 + i, spread + i * C.SPREAD_MS)
        return
    hz = midi_to_hz(semi_to_midi(val, t))
    if t == 0:
        _tone(hz, g, 0, spread)
    elif t == 1:
        _tone(hz, int(g * 1.4), 1, spread)
    else:
        _tone(hz, g, 2, spread)
        if C.FIFTHS:
            _tone(hz * 1.5, g, 4, spread + C.SPREAD_MS)


def cycle_volume():
    S.vol_i = (S.vol_i + 1) % len(C.VOLS)
    try:
        M5.Speaker.setVolume(C.VOLS[S.vol_i])
    except Exception:
        pass
    S.set_hero("VOL", S.vol_i + 1)


def begin():
    try:
        M5.Speaker.begin()
    except Exception:
        pass
    try:
        M5.Speaker.setVolume(C.VOLUME)
    except Exception:
        pass
    apply_mix()
