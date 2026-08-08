"""A host stand-in for the M5 module, backed by Pillow.

The point is fidelity, not convenience: `app.py`'s own draw functions run
unchanged against this, so the sim cannot drift from the device the way a
hand-written HTML mock would. The hardware boundary is drawn exactly at the
M5.Lcd primitives -- everything above it is the real program.

Two things make it faithful rather than approximate:

* **Text is positioned from device-measured metrics.** sim/metrics.json holds
  the real per-character advance for every font, dumped off the board by
  sim/dump_metrics.py. Glyphs are drawn one at a time and advanced by the
  device's width, so a centred string lands on the same pixel it does on the
  panel. Composition is additive on this firmware (verified: 'TEMPO', '108'
  and 'ABCDEFGH' all measured exact); a couple of lowercase pairs kern by 1px.

* **Colour is quantised through RGB565**, as the panel does, so banding and
  the loss of low-order bits show up here instead of surprising you later.

What is still NOT faithful, and must be judged on hardware: panel gamma and
colour cast, backlight, viewing angle, and refresh/tearing behaviour. Treat
the sim for geometry and typography, the panel for colour.
"""

import json
import os

from PIL import Image, ImageDraw, ImageFont

_HERE = os.path.dirname(os.path.abspath(__file__))
_METRICS = json.load(open(os.path.join(_HERE, "metrics.json")))

# Any DejaVu Sans on the box; the firmware ships one typeface at eight sizes
# (all the Montserrat/ASCII7 names are aliases of it -- verified on device with
# `FONTS.Montserrat12 is FONTS.DejaVu9` -> True).
_TTF_CANDIDATES = [
    "/opt/miniconda3/envs/11-thermal3d/lib/python3.10/site-packages/matplotlib/"
    "mpl-data/fonts/ttf/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/DejaVuSans.ttf",
]
_TTF_BOLD = [p.replace("DejaVuSans.ttf", "DejaVuSans-Bold.ttf")
             for p in _TTF_CANDIDATES]


def _find(paths):
    for p in paths:
        if os.path.exists(p):
            return p
    raise RuntimeError("no DejaVuSans.ttf found; looked in:\n  " + "\n  ".join(paths))


_TTF = _find(_TTF_CANDIDATES)
try:
    _TTF_B = _find(_TTF_BOLD)
except RuntimeError:
    _TTF_B = _TTF


def rgb565(c):
    """Quantise a 0xRRGGBB int the way the panel does."""
    r, g, b = (c >> 16) & 0xFF, (c >> 8) & 0xFF, c & 0xFF
    r, g, b = r >> 3, g >> 2, b >> 3
    return (r * 255 // 31, g * 255 // 63, b * 255 // 31)


class _Font:
    """One device font: its measured advances plus a TTF calibrated to match."""

    _cache = {}

    def __init__(self, name, spec, bold=False):
        self.name = name
        self.height = spec["h"]
        self.adv = spec["w"]                    # advance for chr(32+i)
        self.bold = bold
        self.ttf = self._calibrate(spec, bold)

    def _calibrate(self, spec, bold):
        """Pick the TTF pixel size whose advances best match the device's.

        Guessing a point size would put the glyphs at the wrong weight for the
        box they sit in; fitting against the real table keeps the sim honest.
        """
        path = _TTF_B if bold else _TTF
        target = spec["w"]
        best, best_err = None, None
        for size in range(6, 60):
            key = (path, size)
            if key not in _Font._cache:
                _Font._cache[key] = ImageFont.truetype(path, size)
            f = _Font._cache[key]
            err = 0
            for i in range(95):
                ch = chr(32 + i)
                err += abs(f.getlength(ch) - target[i])
            if best_err is None or err < best_err:
                best, best_err = f, err
        return best

    def advance(self, ch):
        o = ord(ch)
        return self.adv[o - 32] if 32 <= o <= 126 else 0

    def width(self, s):
        return sum(self.advance(c) for c in s)


class _Fonts:
    pass


class _Lcd:
    def __init__(self, w, h):
        self.img = Image.new("RGB", (w, h), (0, 0, 0))
        self.d = ImageDraw.Draw(self.img)
        self._w, self._h = w, h
        self._font = None
        self._fg = (255, 255, 255)
        self._bg = None
        self.brightness = 255

        self.FONTS = _Fonts()
        for name, spec in _METRICS["fonts"].items():
            setattr(self.FONTS, name, _Font(name, spec))

    # -- geometry -------------------------------------------------------
    def width(self):
        return self._w

    def height(self):
        return self._h

    def setBrightness(self, v):
        self.brightness = v

    # LovyanGFX batches a frame between these; on the host they are no-ops,
    # but the app calls them so the stub has to answer.
    def startWrite(self):
        pass

    def endWrite(self):
        pass

    # -- fills ----------------------------------------------------------
    def fillScreen(self, c):
        self.d.rectangle([0, 0, self._w, self._h], fill=rgb565(c))

    def fillRect(self, x, y, w, h, c):
        if w <= 0 or h <= 0:
            return
        self.d.rectangle([x, y, x + w - 1, y + h - 1], fill=rgb565(c))

    def drawRect(self, x, y, w, h, c):
        if w <= 0 or h <= 0:
            return
        self.d.rectangle([x, y, x + w - 1, y + h - 1], outline=rgb565(c))

    def fillCircle(self, x, y, r, c):
        self.d.ellipse([x - r, y - r, x + r, y + r], fill=rgb565(c))

    def fillRoundRect(self, x, y, w, h, r, c):
        if w <= 0 or h <= 0:
            return
        self.d.rounded_rectangle([x, y, x + w - 1, y + h - 1], radius=r,
                                 fill=rgb565(c))

    def drawPng(self, buf, x, y):
        """Blit a PNG from a bytes buffer, as the device's drawPng does
        (verified: 8 ms per ~100x96 sprite on the CoreS3)."""
        from io import BytesIO
        spr = Image.open(BytesIO(buf)).convert("RGB")
        self.img.paste(spr, (int(x), int(y)))

    def drawCircle(self, x, y, r, c):
        self.d.ellipse([x - r, y - r, x + r, y + r], outline=rgb565(c))

    def fillTriangle(self, x0, y0, x1, y1, x2, y2, c):
        self.d.polygon([(x0, y0), (x1, y1), (x2, y2)], fill=rgb565(c))

    def drawLine(self, x0, y0, x1, y1, c):
        self.d.line([x0, y0, x1, y1], fill=rgb565(c))

    def drawFastHLine(self, x, y, w, c):
        self.fillRect(x, y, w, 1, c)

    def drawFastVLine(self, x, y, h, c):
        self.fillRect(x, y, 1, h, c)

    # -- text -----------------------------------------------------------
    def setFont(self, f):
        self._font = f

    def fontHeight(self):
        return self._font.height if self._font else 0

    def setTextColor(self, fg, bg=None):
        self._fg = rgb565(fg)
        self._bg = rgb565(bg) if bg is not None else None

    def textWidth(self, s):
        return self._font.width(s) if self._font else 0

    def drawString(self, s, x, y):
        f = self._font
        if f is None:
            return
        if self._bg is not None:
            self.fillRect(x, y, f.width(s), f.height,
                          (self._bg[0] << 16) | (self._bg[1] << 8) | self._bg[2])
        cx = x
        for ch in s:
            a = f.advance(ch)
            if ch != " ":
                # centre the glyph in the advance box the device would use
                gw = f.ttf.getlength(ch)
                self.d.text((cx + (a - gw) / 2, y + f.height / 2), ch,
                            font=f.ttf, fill=self._fg, anchor="lm")
            cx += a


class _Speaker:
    """Silent, but records what was asked for so the sim can show triggers."""

    def __init__(self):
        self.events = []
        self.volume = 0
        self.ch_vol = {}

    def begin(self):
        pass

    def end(self):
        pass

    def setVolume(self, v):
        self.volume = v

    def getVolume(self):
        return self.volume

    def setChannelVolume(self, ch, v):
        self.ch_vol[ch] = v

    def setAllChannelVolume(self, v):
        for c in range(8):
            self.ch_vol[c] = v

    def tone(self, freq, ms, ch=0):
        self.events.append((freq, ms, ch))

    def stop(self, *a):
        pass

    def isPlaying(self, *a):
        return False


class _M5:
    def __init__(self, size=None):
        w, h = size or _METRICS["screen"]
        self.Lcd = _Lcd(w, h)
        self.Display = self.Lcd
        self.Speaker = _Speaker()
        self.Power = None

    def begin(self):
        pass

    def update(self):
        pass

    def getBoard(self):
        return 24


class MatrixKeyboard:
    """Scriptable keyboard: feed() key codes, the app pulls them via get_key()."""

    def __init__(self):
        self.queue = []
        self.cb = None

    def feed(self, codes):
        self.queue.extend(codes)

    def set_callback(self, cb):
        self.cb = cb

    def tick(self):
        while self.queue and self.cb:
            self.cb(self)

    def get_key(self):
        return self.queue.pop(0) if self.queue else -1

    def is_pressed(self):
        return bool(self.queue)

    def deinit(self):
        pass


BOARDS = {"cores3": (320, 240), "cube": (240, 240)}


def install(board="cores3"):
    """Put the fakes into sys.modules, then hand back the M5 instance.

    `board` picks the panel size, because the two machines differ in shape
    and the face lays itself out from what the board reports. A stand-in
    scd_board carries just enough of that module's surface for the drawing
    code — the real ones are hardware and cannot run here.

    Also grafts MicroPython's ticks_* onto the host `time` module, since the
    app's transport is written against them.
    """
    import sys
    import time as _time
    import types

    m5 = _M5(BOARDS[board])
    sys.modules["M5"] = m5

    hw = types.ModuleType("hardware")
    hw.MatrixKeyboard = MatrixKeyboard
    sys.modules["hardware"] = hw

    b = types.ModuleType("scd_board")
    b.NAME = board
    b.HAS_BODY = board == "cores3"
    b.MIN_RMS = 90 if board == "cores3" else 140
    b.lcd = m5.Lcd
    b.W, b.H = m5.Lcd.width(), m5.Lcd.height()
    b.begin = lambda: None
    b.mic_poll = lambda: None
    b.poll_input = lambda now: (False, 0, False)
    b.on_beat = lambda now, intensity: None
    b.tick = lambda now: None
    b.rest = lambda: None
    b.resting_due = lambda now: False
    sys.modules["scd_board"] = b

    if not hasattr(_time, "ticks_ms"):
        _time.ticks_ms = lambda: int(_time.monotonic() * 1000)
        _time.ticks_us = lambda: int(_time.monotonic() * 1000000)
        _time.ticks_add = lambda t, d: t + d
        _time.ticks_diff = lambda a, b: a - b
        _time.sleep_ms = lambda ms: None          # never actually sleep in the sim
    return m5
