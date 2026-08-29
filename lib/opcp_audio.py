# OP-CP — the mixer and the voices.
#
# Nothing here draws; nothing here reads the keyboard. The only reason this is
# more than a wrapper around M5.Speaker.tone is the channel budget: see
# balance().

import time

import M5

import opcp_conf as C
from opcp_state import S

MAGIC = b"OPK2"              # keep in sync with opcp_synth.MAGIC

# ------------------------------------------------------------------ the kit
# lib/opcp_kit.bin holds every sound as a complete 8-bit mono WAV at 11025 Hz,
# built on the host by tools/build_kit.py (rendering it on the board costs
# ~5.4 s, which is not an acceptable boot cost).
#
# Each sound gets its OWN allocation, read straight out of the file with seek.
# The obvious design — one blob with memoryview slices into it — does not
# work: with the app running there is ~72 KB free but no single contiguous
# block that size, so it dies with `MemoryError: memory allocation failed`.
# Free heap is not the same as largest free block. Twelve allocations of
# 1-2 KB fit a fragmented heap far more easily than one of 18 KB.
#
# 8-bit, not 16, and that is a memory decision rather than a taste one: the
# kit is resident for the life of the program, and the difference between
# 36 KB and 18 KB is the difference between having the ESP-NOW radio and
# having real drums. See opcp_synth.to_u8().
#
# playWav rather than playRaw, because playRaw reads ANY buffer as int16
# whatever its type — that is what made 8-bit impossible the first time. The
# price is that the sample rate is in the header rather than an argument,
# which _play() rewrites per note; the sampler trick is unchanged.
KIT_PATH = "opcp_kit.bin"
KIT = {}                     # name -> bytearray holding one 8-bit mono WAV
kit_ok = False
kit_note = ""                # why the kit is not loaded, when it is not

# One channel per track now. The old engine needed up to seven, because each
# drum layer was a separate tone() call; a drum is one buffer today.
CH = (0, 1, 2, 3)
TRIM = (1.0, 1.0, 0.80, 1.0)

RATE_BASE = 11025        # what lib/opcp_kit.bin was rendered at
BASE_MIDI = 69           # the pitch the melodic buffers were rendered at
# Measured on device: playback reproduces 700 Hz to 48 kHz with the duration
# it promises. Outside that we fold by octaves rather than clamp — clamping
# puts the note out of tune, and a note in the wrong octave is far less
# offensive than a note that is simply wrong.
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

    Keeps whatever fits. voice() already falls through to tone() for a sound
    the dict does not have, so eleven real drums and one beep is strictly
    better than twelve beeps — and the old all-or-nothing behaviour threw
    away ten loaded sounds to answer False. It did it silently, too: nothing
    said so anywhere, so an instrument that had quietly dropped to tone()
    just sounded wrong, with no way to tell that from a bad kit or a bad ear.
    kit_note now says what went wrong, and any layer above can read it.
    """
    global kit_ok, kit_note
    kit_ok = False
    kit_note = ""
    KIT.clear()
    count = 0
    try:
        import gc
        import struct
        gc.collect()
        with open(path, "rb") as f:
            head = f.read(5)
            if len(head) < 5 or head[:4] != MAGIC:
                kit_note = "%s is not %s — rebuild it with `make kit`" % (
                    path, MAGIC.decode())
                return False
            count = head[4]
            index = f.read(12 * count)
            for k in range(count):
                nm, off, ln = struct.unpack_from("<4sII", index, k * 12)
                f.seek(off)
                buf = f.read(ln)
                if len(buf) != ln:
                    kit_note = "%s is truncated" % path
                    break
                KIT[nm.rstrip(b"\0").decode()] = bytearray(buf)
    except MemoryError:
        # Not fatal, and not silent. The sounds already read stay read.
        kit_note = "out of memory after %d of %d sounds" % (len(KIT), count)
    except Exception as e:
        kit_note = "%s: %s" % (path, e)
    kit_ok = len(KIT) > 0
    if kit_ok and len(KIT) < count:
        kit_note = kit_note or "only %d of %d sounds loaded" % (len(KIT), count)
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
        # One buffer, one channel. A PARTIALLY loaded kit can be wrong here —
        # a sound the dict is missing falls back to tone() on channels 5+, so
        # the budget was shared for a channel that stays silent. That makes a
        # degraded kit a little quieter than it could be, which is the right
        # direction for a mode that should be noticed and fixed.
        return (CH[t],)
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


def set_trim(track, gain):
    """Per-track gain, which balance() picks up on the next step.

    Two tables, because there are two paths: TRIM is what the PCM mixer
    reads, C.CH_TRIM what the tone() fallback reads, and a caller changing
    one and not the other gets a mix that changes when the kit fails to
    load. Callers used to assign both from outside — including CH_TRIM,
    a dict in the constants module, which the layering says holds no state.
    Knowing that is this module's job.
    """
    global TRIM
    if 0 <= track < len(TRIM):
        t = list(TRIM)
        t[track] = gain
        TRIM = tuple(t)
    C.CH_TRIM[track] = gain


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


# Offsets into the canonical 44-byte header opcp_synth.wav8 writes: the
# sample rate at 24, and the byte rate at 28 which for 8-bit mono is the same
# number. Both have to move together or the duration comes out wrong.
_RATE_OFF = 24
_BYTERATE_OFF = 28


def _play(buf, rate, ch):
    """Play one WAV buffer at `rate`, by rewriting its header first.

    playWav takes no rate argument — the header carries it. Since the buffer
    is ours, repitching is four bytes, and the sampler trick survives the move
    off playRaw. Measured on device: one buffer at 11025, 22050 and 5512 Hz
    played for 301, 156 and 593 ms.
    """
    try:
        r = int(rate)
        for off in (_RATE_OFF, _BYTERATE_OFF):
            buf[off] = r & 0xFF
            buf[off + 1] = (r >> 8) & 0xFF
            buf[off + 2] = (r >> 16) & 0xFF
            buf[off + 3] = (r >> 24) & 0xFF
        M5.Speaker.playWav(buf, 1, ch, True)
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
