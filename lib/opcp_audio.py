# OP-CP — the mixer and the voices.
#
# Nothing here draws; nothing here reads the keyboard. The only reason this is
# more than a wrapper around M5.Speaker.tone is the channel budget: see
# balance().

import time

import M5

import opcp_conf as C
from opcp_state import S

# ------------------------------------------------------------------ the kit
# lib/opcp_kit.bin holds every sound as signed 16-bit PCM at 11025 Hz, built on
# the host by tools/build_kit.py (rendering it on the board costs ~5.4 s, which
# is not an acceptable boot cost).
#
# Each sound gets its OWN allocation, read straight out of the file with seek.
# The obvious design — one 36 KB blob with memoryview slices into it — does not
# work: with the app running there is ~72 KB free but no single contiguous 36 KB
# block, so it dies with `MemoryError: memory allocation failed, allocating
# 36096 bytes`. Free heap is not the same as largest free block. Twelve
# allocations of 1-4 KB fit a fragmented heap easily.
#
# playRaw interprets ANY buffer as int16 regardless of its type — verified on
# device: 8000 bytes played for 459 ms at rate 8000, i.e. 4000 samples.
KIT_PATH = "opcp_kit.bin"
KIT = {}                     # name -> bytearray of int16 PCM
kit_ok = False

# One channel per track now. The old engine needed up to seven, because each
# drum layer was a separate tone() call; a drum is one buffer today.
CH = (0, 1, 2, 3)
TRIM = (1.0, 1.0, 0.80, 1.0)

RATE_BASE = 11025        # what lib/opcp_kit.bin was rendered at
BASE_MIDI = 69           # the pitch the melodic buffers were rendered at
# Measured on device: playRaw reproduces 700 Hz to 48 kHz with the duration it
# promises. Outside that we fold by octaves rather than clamp — clamping puts
# the note out of tune, and a note in the wrong octave is far less offensive
# than a note that is simply wrong.
RATE_MIN = 700
RATE_MAX = 48000


def rate_for(midi):
    r = RATE_BASE * (2.0 ** ((midi - BASE_MIDI) / 12.0))
    while r < RATE_MIN:
        r *= 2.0
    while r > RATE_MAX:
        r *= 0.5
    return r


def load_kit(path=KIT_PATH):
    """Read the PCM kit, one allocation per sound.

    Returns False if anything is missing or will not fit, and the caller falls
    back to tone() — a board without the .bin should still make noise.
    """
    global kit_ok
    kit_ok = False
    KIT.clear()
    try:
        import gc
        import struct
        gc.collect()
        with open(path, "rb") as f:
            head = f.read(5)
            if len(head) < 5 or head[:4] != b"OPK1":
                return False
            count = head[4]
            index = f.read(12 * count)
            for k in range(count):
                nm, off, ln = struct.unpack_from("<4sII", index, k * 12)
                f.seek(off)
                buf = f.read(ln)
                if len(buf) != ln:
                    return False
                KIT[nm.rstrip(b"\0").decode()] = buf
        kit_ok = len(KIT) == count
    except Exception:
        KIT.clear()
        kit_ok = False
    return kit_ok


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
    if kit_ok:
        return (CH[t],)                 # one buffer, one channel
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
        total += trim_for(c)
    if total <= 0:
        return
    scale = C.MIX_BUDGET / total
    for c in chs:
        set_ch(c, min(C.MAX_CH_VOL, int(trim_for(c) * scale)))


def trim_for(c):
    return TRIM[c] if kit_ok and c < len(TRIM) else C.CH_TRIM.get(c, 1.0)


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


def _play(buf, rate, ch):
    try:
        M5.Speaker.playRaw(buf, int(rate), False, 1, ch, True)
        return True
    except Exception:
        return False


def voice(t, val, spread=0):
    """Sound one step of one track."""
    if val is None or S.muted[t]:
        return

    if kit_ok:
        if t == 3:
            name = C.DRUMS[val % len(C.DRUMS)][0]
            buf = KIT.get(name)
            if buf is not None and _play(buf, RATE_BASE, CH[3]):
                return
        else:
            buf = KIT.get("V%d" % t)
            if buf is not None:
                # repitch by playback rate — the sampler trick
                if _play(buf, rate_for(semi_to_midi(val, t)), CH[t]):
                    return
        # falling through means the blob was missing a sound; use tone()

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
    S.set_hero("VOL", S.vol_i)     # 0 is mute, so the index IS the reading


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
    load_kit()
