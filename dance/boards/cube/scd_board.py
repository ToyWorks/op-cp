# SCD on the XINGZHI / xiaozhi-cube 1.54.
#
# The other half of the pair — `make BOARD=cube` deploys this file as
# scd_board.py and boards/cores3/ never reaches the device. This machine has
# a face and ears but no body: a 240x240 ST7789, an I2S MEMS microphone,
# three side buttons. It dances entirely on the panel.
#
# Every pin below is from the board's own config.h in xiaozhi-esp32
# (main/boards/xingzhi-cube-1.54tft-wifi), then confirmed on the hardware.
#
# The firmware underneath is UIFlow2 for the M5Stack StampS3 — a bare
# ESP32-S3 build with no panel, no PMIC and no codec of its own to trip over
# on a board M5 never made. What it does bring is M5.UserDisplay, a full
# LovyanGFX device you hand a panel type and a pin list, so the face draws
# through exactly the same calls it uses on the CoreS3.

import math
import time

import M5
from machine import I2S, Pin

import scd_conf as C
from scd_state import S

NAME = "cube"
HAS_BODY = False

# The mic's own scale, after the x8 in _rms32 puts it alongside the CoreS3's.
# Measured in this room: quiet ~56 avg / 300 peak, music ~590 avg / 2500 peak.
MIN_RMS = 140

# --- panel (ST7789, SPI3) -------------------------------------------------
PIN_SCLK, PIN_MOSI, PIN_DC, PIN_CS, PIN_RST, PIN_BL = 9, 10, 8, 14, 18, 13
# --- microphone (I2S in) --------------------------------------------------
PIN_MIC_WS, PIN_MIC_SCK, PIN_MIC_SD = 4, 5, 6
MIC_PORT = 1             # port 0 works too; 1 leaves M5Unified's own alone
RATE = 16000             # FRAME/RATE = one 16 ms energy frame
FRAME = 256
# --- buttons (active low, internal pull-ups; measured 1 at rest) ----------
# GPIO0 is BOOT, and on an ESP32-S3 that is the download-mode strapping pin:
# held low at reset the chip never starts the firmware and the screen simply
# stays black. It is a terrible thing to invite anyone to press, so the app
# does not use it at all — the two side buttons carry everything.
PIN_UP, PIN_LINK = 39, 40
BTN_POLL_MS = 30         # edge-detected, so this only bounds the latency

lcd = None
W = H = 0

_i2s = None
_bufs = None
_cur = 0
_full = False
_mic_ok = False
_pins = None
_prev = (1, 1)


def begin():
    global lcd, W, H
    lcd = M5.UserDisplay(
        panel=M5.UserDisplay.PANEL.ST7789,
        w=240, h=240, ox=0, oy=0,
        # the panel is inverted; its element order is already RGB (checked
        # on hardware with a labelled R/G/B card — the labels read true)
        invert=True, rgb=False,
        spi_host=2, spi_freq=40, spi_mode=0,
        sclk=PIN_SCLK, mosi=PIN_MOSI, miso=-1,
        dc=PIN_DC, cs=PIN_CS, rst=PIN_RST, busy=-1,
        bl=PIN_BL, bl_invert=False, bl_pwm_freq=44100, bl_pwm_chn=7,
    )
    W, H = lcd.width(), lcd.height()
    S.min_rms = MIN_RMS
    lcd.fillScreen(C.BG)
    try:
        lcd.setBrightness(160)
    except Exception:
        pass
    _mic_begin()
    _buttons_begin()


# ---------------------------------------------------------------- microphone
# M5.Mic is no use here. M5Unified drives I2S at 16 bits, and this board's
# MEMS mic puts 24-bit samples MSB-aligned in 32-bit slots, so all that comes
# back is a DC level — measured: mono reads a constant, stereo a slow drift,
# neither moves when you play music at it. machine.I2S at bits=32 does move:
# a tone across the room lifts the frame energy by roughly 10x.
#
# M5Unified claims an I2S port during boot, so hand it back before asking for
# one, or the driver answers ESP_ERR_NOT_FOUND. Registering an irq puts the
# port in non-blocking mode, which buys the same ping-pong the CoreS3 gets
# from its DMA recorder: the next frame fills while this one is measured.

def _irq(_arg):
    global _full
    _full = True                 # ISR context: raise a flag, measure later


def _mic_begin():
    global _i2s, _bufs, _cur, _full, _mic_ok
    try:
        for release in (M5.Speaker.end, M5.Mic.end):
            try:
                release()
            except Exception:
                pass
        _i2s = I2S(MIC_PORT,
                   sck=Pin(PIN_MIC_SCK), ws=Pin(PIN_MIC_WS), sd=Pin(PIN_MIC_SD),
                   mode=I2S.RX, bits=32, format=I2S.MONO,
                   rate=RATE, ibuf=FRAME * 16)
        _bufs = (bytearray(FRAME * 4), bytearray(FRAME * 4))
        _cur = 0
        _full = False
        _i2s.irq(_irq)
        _i2s.readinto(_bufs[0])
        _mic_ok = True
    except Exception:
        _i2s = None
        _mic_ok = False


def mic_poll():
    """The finished frame's RMS, or None while the mic is still filling."""
    global _cur, _full
    if not _mic_ok or not _full:
        return None
    _full = False
    done = _bufs[_cur]
    _cur ^= 1
    try:
        _i2s.readinto(_bufs[_cur])               # keep the stream rolling
    except Exception:
        return None

    # The sample sits MSB-aligned, so bytes 2..3 of each 32-bit slot ARE the
    # sample shifted right by 16 — one uint16 load each, exactly what the
    # CoreS3 path costs. The DC term is large and drifts, so it is removed
    # per frame (variance = E[v^2] - E[v]^2) rather than assumed away.
    s = 0
    ss = 0
    n = 0
    step = 4 * C.RMS_STRIDE
    for i in range(2, len(done) - 1, step):
        v = done[i] | (done[i + 1] << 8)
        if v >= 0x8000:
            v -= 0x10000
        s += v
        ss += v * v
        n += 1
    if not n:
        return 0
    mean = s // n
    var = ss // n - mean * mean
    if var <= 0:
        return 0
    # x8 at the exit, not inside the loop: it puts this microphone on the
    # same numeric scale the CoreS3's readings live on — which is the scale
    # every threshold downstream was tuned against — while the inner loop
    # stays in cheap small integers.
    return int(math.sqrt(var)) * 8


# --------------------------------------------------------------------- input
def _buttons_begin():
    global _pins
    try:
        _pins = (Pin(PIN_UP, Pin.IN, Pin.PULL_UP),
                 Pin(PIN_LINK, Pin.IN, Pin.PULL_UP))
    except Exception:
        _pins = None


def poll_input(now):
    """(toggle_link, palette_step) — one action per falling edge, not per
    poll. The top button walks the colour; the one below it toggles the ear."""
    global _prev
    if _pins is None or time.ticks_diff(now, S.next_btn) < 0:
        return (False, 0)
    S.next_btn = time.ticks_add(now, BTN_POLL_MS)
    try:
        level = (_pins[0].value(), _pins[1].value())
    except Exception:
        return (False, 0)
    edge = tuple(p == 1 and c == 0 for p, c in zip(_prev, level))
    _prev = level
    return (edge[1], 1 if edge[0] else 0)


# ---------------------------------------------------------------------- body
# There isn't one. These exist so app.py has a single spelling for the beat.

def on_beat(now, intensity):
    pass


def tick(now):
    pass


def rest():
    pass


def resting_due(now):
    return False
