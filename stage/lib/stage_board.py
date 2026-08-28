# The stage node's hardware, and the only file that knows about it.
#
# Same split dance/ uses: everything above this file is pure logic that can be
# tested on a host, and every M5 call lives here behind a try/except so a
# missing subsystem degrades instead of killing the program at line 1
# (op-cp's CLAUDE.md rule 1).
#
# On the host there is no M5 at all, so `present` stays False, draw() records
# the last frame, and the button never fires. The conformance suite drives the
# same table either way.

import stage_anim

BTN_LONG_MS = 800        # a release must be deliberate, not a bounce

BG = 0x000000
FG = 0xF0F0F0
DIM = 0x707070
ALERT = 0xFF2A17         # e-stop only; nothing else may use it

present = False
mic_present = False
last_frame = ()          # what draw() was last asked to show

MIC_RATE = 8000
MIC_SUB_SAMPLES = 256            # one 32 ms energy sub-frame
MIC_SUB_MS = 32
MIC_SUBFRAMES = 32               # per DMA buffer
MIC_BUF_SAMPLES = MIC_SUB_SAMPLES * MIC_SUBFRAMES   # 1.024 s
MIC_BUF_MS = MIC_SUB_MS * MIC_SUBFRAMES
MIC_STRIDE = 4                   # every 4th sample is plenty for an envelope

_bufs = None
_queue = []
_t0 = None

_lcd = None
_btn = None
_w = 135
_h = 240
_shown = None


def begin():
    global present, _lcd, _btn, _w, _h
    try:
        import M5
        M5.begin()
        _lcd = M5.Lcd
        _w, _h = _lcd.width(), _lcd.height()
        _lcd.fillScreen(BG)
        try:
            _lcd.setBrightness(120)
        except Exception:
            pass
        _btn = getattr(M5, "BtnA", None)
        stage_anim.layout(_lcd, _w, _h)
        present = True
    except Exception:
        present = False
    return present


def mic_begin():
    """Bring up the microphone. Two tricks, both measured on this board:

    * M5Unified holds the I2S port for the speaker from boot, and with it
      held the mic 'works' — begin() True, frames all exactly zero.
      Speaker.end() first. (The lesson dance's cube board paid for.)
    * M5.Mic.record() QUEUES: isRecording() is the queue depth, and a
      second buffer armed behind the first starts the instant it ends —
      measured 1014 ms and 2038 ms for two queued seconds. Keeping one
      buffer always queued makes the stream gapless, which is what killed
      the last design: its ~70 ms re-arm hole inflated every gap that
      crossed a buffer boundary and read 100 bpm as 90.
    """
    global mic_present, _bufs, _queue, _t0
    if not present:
        return False
    try:
        import M5
        try:
            M5.Speaker.end()
        except Exception:
            pass
        try:
            M5.Mic.end()
        except Exception:
            pass
        mic_present = bool(M5.Mic.begin())
        _bufs = (bytearray(MIC_BUF_SAMPLES * 2),
                 bytearray(MIC_BUF_SAMPLES * 2))
        _queue = []
        _t0 = None
        if mic_present:
            M5.Mic.record(_bufs[0], MIC_RATE, False)
            M5.Mic.record(_bufs[1], MIC_RATE, False)
            _queue = [0, 1]
    except Exception:
        mic_present = False
    return mic_present


def mic_poll():
    """Energy sub-frames of every second that has finished, or [].

    Timestamps ride the audio chain: the first completed buffer anchors to
    the wall clock once, and every buffer after it is exactly +1024 ms —
    the DMA never pauses, so sample arithmetic IS the clock. Digesting one
    second costs ~54 ms; each finished buffer is re-queued before the
    other runs out, so a tick stall shorter than a second loses nothing.
    """
    global _t0
    if not mic_present or not _queue:
        return []
    import M5
    import time
    out = []
    try:
        while True:
            depth = int(M5.Mic.isRecording())
            if depth >= len(_queue):
                break
            idx = _queue.pop(0)
            if _t0 is None:
                _t0 = time.ticks_add(time.ticks_ms(), -MIC_BUF_MS)
            done = memoryview(_bufs[idx])
            for k in range(MIC_SUBFRAMES):
                base = k * MIC_SUB_SAMPLES * 2
                acc = 0
                sq = 0
                n = 0
                for i in range(base, base + MIC_SUB_SAMPLES * 2,
                               2 * MIC_STRIDE):
                    v = done[i] | (done[i + 1] << 8)
                    if v >= 0x8000:
                        v -= 0x10000
                    acc += v
                    sq += v * v
                    n += 1
                mean = acc // n
                var = sq // n - mean * mean
                out.append((time.ticks_add(_t0, k * MIC_SUB_MS),
                            int(var ** 0.5) if var > 0 else 0))
            _t0 = time.ticks_add(_t0, MIC_BUF_MS)
            M5.Mic.record(_bufs[idx], MIC_RATE, False)
            _queue.append(idx)
    except Exception:
        pass
    return out


def button_held_ms():
    """How long BtnA has been held, or 0. Returns 0 where there is no button.

    Deliberately a duration rather than an event: the e-stop trips on press
    and only releases on a deliberate hold, and both live in the table where
    they can be read.
    """
    if _btn is None:
        return 0
    try:
        if not _btn.isPressed():
            return 0
        held = getattr(_btn, "pressedFor", None)
        if held is not None and held(BTN_LONG_MS):
            return BTN_LONG_MS
        return 1
    except Exception:
        return 0


def draw(frame):
    """Route one frame to the screen.

    An emergency stop takes the whole panel — it is the one state that must
    be readable across a room without interpreting an animation. Everything
    else is stage_anim's business; this file stays the only one that knows
    there is an M5 involved.
    """
    global _shown, last_frame
    last_frame = frame
    if not present or _lcd is None:
        return
    if frame["estop"]:
        if _shown != "estop":
            _shown = "estop"
            stage_anim.clear()
            try:
                _lcd.fillScreen(ALERT)
                _lcd.setTextColor(FG, ALERT)
                _lcd.drawString("STOP", 8, 90)
                _lcd.setTextColor(0x400800, ALERT)
                _lcd.drawString(frame["estop_source"][:12], 8, 120)
            except Exception:
                pass
        return
    if _shown == "estop":                 # coming back: repaint from scratch
        _shown = None
        stage_anim.clear()
    try:
        stage_anim.draw(frame["style"], frame["palette"], frame["hit"],
                        frame["level"], frame["step"], frame["bpm"],
                        frame["fresh"], frame["label"], frame["name"])
    except Exception:
        pass                 # a screen that will not draw must not stop a show
