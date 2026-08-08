# SCD — the microphone, streamed.
#
# M5.Mic.record() fills a buffer over DMA and returns immediately;
# isRecording() goes False when the buffer is full. Two buffers ping-pong so
# the next frame records while this one is measured. At FRAME/RATE that is a
# fresh energy number every ~32 ms, which is all a dancer needs.

import math

import M5

import scd_conf as C

_bufs = None
_cur = 0
ok = False


def begin():
    global _bufs, _cur, ok
    try:
        M5.Mic.begin()
        _bufs = (bytearray(C.FRAME * 2), bytearray(C.FRAME * 2))
        _cur = 0
        M5.Mic.record(_bufs[0], C.RATE, False)
        ok = True
    except Exception:
        ok = False


def _rms(buf):
    """Integer RMS over every RMS_STRIDE-th int16 sample."""
    acc = 0
    n = 0
    step = 2 * C.RMS_STRIDE
    for i in range(0, len(buf), step):
        v = buf[i] | (buf[i + 1] << 8)
        if v >= 0x8000:
            v -= 0x10000
        acc += v * v
        n += 1
    return int(math.sqrt(acc // n)) if n else 0


def poll():
    """The finished frame's RMS, or None while the mic is still filling."""
    global _cur
    if not ok:
        return None
    try:
        if M5.Mic.isRecording():
            return None
    except Exception:
        return None
    done = _bufs[_cur]
    _cur ^= 1
    M5.Mic.record(_bufs[_cur], C.RATE, False)    # keep the stream rolling
    return _rms(done)
