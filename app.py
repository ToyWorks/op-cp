# OP-CP — OP-1 flavoured keyboard sequencer for M5Stack Cardputer-ADV (UIFlow2)
#
# Keybed: the middle two keyboard rows are a real piano — white keys on the
# home row, black keys in the physical gaps above them.
#
#        w e   t y u   o p          black keys
#       a s d f g h j k l ;         white keys  C D E F G A B C D E
#
#   1 2 3 4 5 6 7 8                 steps 1-8   (grid top row)
#   z x c v b n m ,                 steps 9-16  (grid bottom row)
#
#   SPACE play/stop     ENTER record arm (live, quantized to 16ths)
#   q generate   r clear   i mute   ' pattern
#   [ ] tempo    - = octave   ` scale   9 swing   0 volume
#   . / previous / next track        \ help (then s save, l load)
#
# UI follows OP-1's language rather than its artwork: the four encoder colours
# (blue / green / white / orange) code the four tracks AND the four parameter
# slots, steps are bright filled blocks, and every trigger flashes and decays.

import os, sys, io
import time
import random
import M5
from M5 import *

# ------------------------------------------------------------------ config
BPM = 112
VOLUME = 255                 # master out, 0-255
MIX_BUDGET = 255             # total channel volume allowed to sound at once.
                             # Lower it if dense steps still clip.
MAX_CH_VOL = 255
FIFTHS = False
SPREAD_MS = 4
STEPS = 16
TRACKS = 4
PATTERNS = 4
SWING_PCT = 18
SAVE_PATH = "/flash/opcp.json"

BG = 0x000000
CELL_OFF = 0x1A1A1A
CELL_EDGE = 0x333333
INK = 0x000000
DIM = 0x7A7A7A
FG = 0xE0E0E0
ACCENT = 0xFF2A17
MUTED = 0x3A3A3A

# OP-1's four encoder colours, in order. Track n and parameter slot n share one.
BLUE, GREEN, WHITE, ORANGE = 0x2E7BFF, 0x35C75A, 0xEDEDED, 0xFF8A1E
TRACK_COLORS = (BLUE, GREEN, WHITE, ORANGE)
TRACK_LIGHT = (0x9CC4FF, 0x9AE8AE, 0xFFFFFF, 0xFFC98F)

TRACK_NAMES = ("LEAD", "BASS", "KEYS", "PERC")
SCALES = (
    ("MAJ", (0, 2, 4, 5, 7, 9, 11)),
    ("MIN", (0, 2, 3, 5, 7, 8, 10)),
    ("PEN", (0, 3, 5, 7, 10)),
    ("CHR", (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)),
)
# Two-character names on purpose: a step cell is only (CW - GAP) px wide, and
# three glyphs of DejaVu9 overflow it into the neighbouring cell. These are the
# standard drum-machine abbreviations, so nothing is lost by shortening.
DRUMS = (
    ("BD", ((98, 80),)),                      # bass drum
    ("SD", ((200, 45), (2400, 26))),          # snare
    ("HH", ((6200, 18),)),                    # closed hat
    ("OH", ((6200, 80),)),                    # open hat
    ("RM", ((900, 22),)),                     # rimshot
    ("TL", ((140, 70),)),                     # low tom
    ("TH", ((190, 60),)),                     # high tom
    ("CP", ((1200, 24), (1750, 24))),         # clap
    ("CB", ((820, 50),)),                     # cowbell
)
NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

WHITE_KEYS = "asdfghjkl;"
WHITE_SEMI = (0, 2, 4, 5, 7, 9, 11, 12, 14, 16)
BLACK_KEYS = {"w": 1, "e": 3, "t": 6, "y": 8, "u": 10, "o": 13, "p": 15}
STEP_KEYS_A = "12345678"
STEP_KEYS_B = "zxcvbnm,"

FLASH_MAX = 3
FLASH_MS = 45

# ------------------------------------------------------------------ state
W = H = 0
HEAD = CELL_F = TINY = None
HEAD_H = CELL_H = TINY_H = 0
GX = GY = CW = CH = GAP = 0
PROG_Y = PARAM_Y = PARAM_H = STATUS_Y = 0

kb = None
kb_tick = None

patterns = [[[None] * STEPS for _ in range(TRACKS)] for _ in range(PATTERNS)]
pat = 0
track = 0
cursor = 0
octave = [0, -1, 0, 0]
muted = [False] * TRACKS
scale_i = 1
root = 57
bpm = BPM
swing = True
playing = False
recording = False
play_step = 0
next_tick = 0
V_GRID, V_FACE, V_RING, V_BARS, V_HELP = 0, 1, 2, 3, 4
VIEW_NAMES = ("GRID", "FACE", "RING", "BARS", "HELP")
view = V_GRID
hit = [0] * TRACKS           # per-track trigger envelope, for the cartoon views
HIT_MAX = 6
ANIM_MS = 55
next_anim = 0
blink = 0
next_blink = 0
last_semi = 0
ring_pts = []
status = "ready"
dirty_all = True
pending = []
flash = [0] * STEPS
next_flash = 0
vol_i = 4
VOLS = (90, 140, 190, 225, 255)

CH_TRIM = {0: 1.0, 1: 1.0, 2: 0.85, 4: 0.55, 5: 1.0, 6: 0.5}


def steps():
    return patterns[pat][track]


# ------------------------------------------------------------------ audio
def set_ch(ch, vol):
    try:
        M5.Speaker.setChannelVolume(ch, int(vol))
    except Exception:
        pass


def apply_mix():
    try:
        M5.Speaker.setAllChannelVolume(MAX_CH_VOL)
    except Exception:
        pass


def voices_for(t, val):
    """Which mixer channels track t will occupy for this value."""
    if val is None or muted[t]:
        return ()
    if t == 3:
        return tuple(5 + i for i in range(len(DRUMS[val % len(DRUMS)][1])))
    if t == 2:
        return (2, 4) if FIFTHS else (2,)
    return (t,)


def balance(chs):
    """Share the budget across exactly the voices about to sound.

    One note alone gets the whole 255; a dense step gets divided down. This is
    where the loudness comes from — a fixed safety margin would waste most of
    the range on the sparse steps, which is what most steps are."""
    if not chs:
        return
    total = 0.0
    for c in chs:
        total += CH_TRIM.get(c, 1.0)
    if total <= 0:
        return
    scale = MIX_BUDGET / total
    for c in chs:
        set_ch(c, min(MAX_CH_VOL, int(CH_TRIM.get(c, 1.0) * scale)))


def _tone(freq, ms, ch, delay=0):
    if delay > 0:
        pending.append((time.ticks_add(time.ticks_ms(), delay), freq, ms, ch))
        return
    try:
        M5.Speaker.tone(int(freq), int(ms), ch)
    except Exception:
        try:
            M5.Speaker.tone(int(freq), int(ms))
        except Exception:
            pass


def flush_pending():
    if not pending:
        return
    now = time.ticks_ms()
    keep = []
    for item in pending:
        if time.ticks_diff(now, item[0]) >= 0:
            _tone(item[1], item[2], item[3])
        else:
            keep.append(item)
    pending[:] = keep


def midi_to_hz(n):
    return 440.0 * (2.0 ** ((n - 69) / 12.0))


def semi_to_midi(semi, t):
    return root + semi + 12 * octave[t]


def gate_ms():
    return max(30, int(60000 / (bpm * 4) * 0.7))


def voice(t, val, spread=0):
    if val is None or muted[t]:
        return
    g = gate_ms()
    if t == 3:
        for i, (f, ms) in enumerate(DRUMS[val % len(DRUMS)][1]):
            _tone(f, ms, 5 + i, spread + i * SPREAD_MS)
        return
    hz = midi_to_hz(semi_to_midi(val, t))
    if t == 0:
        _tone(hz, g, 0, spread)
    elif t == 1:
        _tone(hz, int(g * 1.4), 1, spread)
    else:
        _tone(hz, g, 2, spread)
        if FIFTHS:
            _tone(hz * 1.5, g, 4, spread + SPREAD_MS)


# ------------------------------------------------------------------ fonts
def _font(name):
    return getattr(M5.Lcd.FONTS, name, None)


def _fh(fallback):
    try:
        h = M5.Lcd.fontHeight()
        if h:
            return h
    except Exception:
        pass
    return fallback


def pick_fonts():
    global HEAD, CELL_F, TINY, HEAD_H, CELL_H, TINY_H
    HEAD = _font("DejaVu12") or _font("DejaVu18")
    M5.Lcd.setFont(HEAD)
    HEAD_H = _fh(12)
    CELL_F = _font("DejaVu12") or HEAD
    M5.Lcd.setFont(CELL_F)
    CELL_H = _fh(12)
    TINY = _font("DejaVu9") or CELL_F
    M5.Lcd.setFont(TINY)
    TINY_H = _fh(9)


def layout():
    global GX, GY, CW, CH, GAP, PROG_Y, PARAM_Y, PARAM_H, STATUS_Y
    GAP = 2
    CW = (W - 12) // 8
    GX = (W - (CW * 8)) // 2
    GY = HEAD_H + 4

    PARAM_H = TINY_H + CELL_H + 6
    STATUS_Y = H - TINY_H - 2
    PARAM_Y = STATUS_Y - PARAM_H - 3
    avail = PARAM_Y - GY - 6
    CH = max(12, min(CW, (avail - GAP) // 2))
    PROG_Y = GY + 2 * (CH + GAP) + 2


# ------------------------------------------------------------------ drawing
def cell_xy(i):
    row, col = i // 8, i % 8
    return GX + col * CW, GY + row * (CH + GAP)


def cell_label(t, val):
    if val is None:
        return ""
    if t == 3:
        return DRUMS[val % len(DRUMS)][0]
    return NOTE_NAMES[semi_to_midi(val, t) % 12]


def step_color(i):
    if muted[track]:
        return MUTED
    f = flash[i]
    if f >= FLASH_MAX:
        return 0xFFFFFF
    if f > 0:
        return TRACK_LIGHT[track]
    return TRACK_COLORS[track]


def draw_cell(i):
    x, y = cell_xy(i)
    w, h = CW - GAP, CH
    val = steps()[i]
    on = val is not None

    if on:
        c = step_color(i)
        M5.Lcd.fillRect(x, y, w, h, c)
        s = cell_label(track, val)
        M5.Lcd.setFont(TINY)
        M5.Lcd.setTextColor(INK, c)
        M5.Lcd.drawString(s, x + (w - M5.Lcd.textWidth(s)) // 2,
                          y + (h - TINY_H) // 2)
    else:
        M5.Lcd.fillRect(x, y, w, h, CELL_OFF)
        M5.Lcd.drawRect(x, y, w, h, CELL_EDGE)
        if i % 4 == 0:                       # beat marker
            M5.Lcd.fillRect(x + w // 2 - 1, y + h // 2 - 1, 3, 3, TRACK_COLORS[track])

    if i == cursor and not playing:
        M5.Lcd.drawRect(x, y, w, h, FG)
    if playing and i == play_step:
        c = ACCENT if recording else 0xFFFFFF
        M5.Lcd.drawRect(x, y, w, h, c)
        M5.Lcd.drawRect(x + 1, y + 1, w - 2, h - 2, c)


def draw_grid():
    for i in range(STEPS):
        draw_cell(i)


def draw_header():
    M5.Lcd.fillRect(0, 0, W, GY - 2, BG)
    M5.Lcd.setFont(HEAD)
    M5.Lcd.setTextColor(TRACK_COLORS[track], BG)
    left = "%s" % TRACK_NAMES[track]
    M5.Lcd.drawString(left, 2, 1)
    M5.Lcd.setTextColor(DIM, BG)
    M5.Lcd.drawString("P%d" % (pat + 1), 2 + M5.Lcd.textWidth(left) + 6, 1)

    # four track chips, OP-1 encoder colours; muted ones go dark
    cx = W - 12
    for t in range(TRACKS - 1, -1, -1):
        c = MUTED if muted[t] else TRACK_COLORS[t]
        sz = 8 if t == track else 5
        M5.Lcd.fillRect(cx, 2 + (8 - sz), sz, sz, c)
        cx -= 11

    if recording:
        M5.Lcd.fillRect(W - 8, 2, 6, 6, ACCENT)


def draw_progress():
    M5.Lcd.fillRect(GX, PROG_Y, CW * 8, 2, CELL_EDGE)
    if playing:
        w = int(CW * 8 * (play_step + 1) / STEPS)
        M5.Lcd.fillRect(GX, PROG_Y, w, 2, ACCENT if recording else TRACK_COLORS[track])


PARAMS = ("TEMPO", "SCALE", "OCT", "SWING")


def param_values():
    return (str(bpm),
            SCALES[scale_i][0],
            "--" if track == 3 else "%+d" % octave[track],
            "ON" if swing else "OFF")


def draw_params():
    M5.Lcd.fillRect(0, PARAM_Y, W, PARAM_H, BG)
    seg = W // 4
    vals = param_values()
    for i in range(4):
        x = i * seg + 1
        w = seg - 3
        c = TRACK_COLORS[i]
        M5.Lcd.fillRect(x, PARAM_Y, w, PARAM_H, c)
        M5.Lcd.setFont(TINY)
        M5.Lcd.setTextColor(INK, c)
        M5.Lcd.drawString(PARAMS[i], x + 3, PARAM_Y + 2)
        M5.Lcd.setFont(CELL_F)
        M5.Lcd.setTextColor(INK, c)
        s = vals[i]
        M5.Lcd.drawString(s, x + w - M5.Lcd.textWidth(s) - 3,
                          PARAM_Y + PARAM_H - CELL_H - 2)


def draw_status():
    M5.Lcd.fillRect(0, STATUS_Y, W, TINY_H + 2, BG)
    M5.Lcd.setFont(TINY)
    val = steps()[cursor]
    M5.Lcd.setTextColor(DIM, BG)
    left = "%02d %s" % (cursor + 1, cell_label(track, val) if val is not None else "--")
    M5.Lcd.drawString(left, 2, STATUS_Y)
    M5.Lcd.setTextColor(ACCENT if recording else CELL_EDGE, BG)
    M5.Lcd.drawString(status, W - M5.Lcd.textWidth(status) - 2, STATUS_Y)


HELP = (
    ("  w e  t y u  o p", WHITE),
    (" a s d f g h j k l ;", WHITE),
    ("1-8 z-,  steps", DIM),
    ("SPACE  play/stop", DIM),
    ("ENTER  record", DIM),
    ("\\  next view", ORANGE),
    ("q gen   r clear", DIM),
    ("i mute  ' pattern", DIM),
    ("[ ] bpm  - = oct", DIM),
    ("` scale  9 swing", DIM),
    ("0 vol   . / track", DIM),
    ("s save  l load", DIM),
)


def help_layout():
    """Pack the help lines into as many columns as the panel needs.

    Single-column help does not fit: twelve lines at this font are taller than
    135 px. Rather than hardcode a split, fill a column until it runs out of
    height and start the next one, sized to the widest string it holds. The one
    layout function is shared with the self-test so both agree on the result.
    """
    M5.Lcd.setFont(TINY)
    lh = TINY_H + 1
    per_col = max(1, (H - 4) // lh)
    out = []
    x, y, col_w = 4, 3, 0
    for i, (text, c) in enumerate(HELP):
        if i and i % per_col == 0:
            x += col_w + 8
            y, col_w = 3, 0
        out.append((x, y, text, c))
        w = M5.Lcd.textWidth(text)
        if w > col_w:
            col_w = w
        y += lh
    return out


def draw_help():
    M5.Lcd.fillScreen(BG)
    M5.Lcd.setFont(TINY)
    for x, y, text, c in help_layout():
        M5.Lcd.setTextColor(c, BG)
        M5.Lcd.drawString(text, x, y)


# ------------------------------------------------------------------ cartoon views
# Original artwork in OP-1's spirit — bright, blocky, always moving — rather
# than copies of Teenage Engineering's engine characters.

TRACK_DARK = (0x0C1B33, 0x0B2814, 0x1E1E1E, 0x33200A)


def anim_zone():
    """The band between the header and the parameter strip."""
    top = GY
    bot = PARAM_Y - 4
    return top, bot - top


def build_ring():
    global ring_pts
    top, h = anim_zone()
    m = 14
    x0, y0 = m, top + 4
    w, hh = W - 2 * m, h - 10
    pts = []
    for i in range(6):
        pts.append((x0 + i * w // 6, y0))
    for i in range(2):
        pts.append((x0 + w, y0 + i * hh // 2))
    for i in range(6):
        pts.append((x0 + w - i * w // 6, y0 + hh))
    for i in range(2):
        pts.append((x0, y0 + hh - i * hh // 2))
    ring_pts = pts


def draw_topbar():
    M5.Lcd.fillRect(0, 0, W, GY - 2, BG)
    M5.Lcd.setFont(TINY)
    M5.Lcd.setTextColor(TRACK_COLORS[track], BG)
    M5.Lcd.drawString(TRACK_NAMES[track], 3, 2)
    M5.Lcd.setTextColor(DIM, BG)
    s = "P%d  %d  %s" % (pat + 1, bpm, SCALES[scale_i][0])
    M5.Lcd.drawString(s, W - M5.Lcd.textWidth(s) - 14, 2)
    c = ACCENT if recording else (TRACK_COLORS[track] if playing else CELL_EDGE)
    M5.Lcd.fillRect(W - 9, 2, 7, 7, c)


# --- FACE: a blocky character that jumps, blinks and sings ----------------
def draw_face(full=False):
    top, h = anim_zone()
    fw, fh = min(120, W - 40), min(74, h - 6)
    fx = (W - fw) // 2
    energy = max(hit)
    fy = top + (h - fh) // 2 - (energy * 3) // HIT_MAX

    if full:
        M5.Lcd.fillRect(0, top, W, h, BG)
    else:
        M5.Lcd.fillRect(0, top, W, h, BG)

    body = TRACK_DARK[track]
    M5.Lcd.fillRect(fx, fy, fw, fh, body)
    M5.Lcd.fillRect(fx + 3, fy + 3, fw - 6, fh - 6, TRACK_COLORS[track] if energy else body)
    if energy:
        M5.Lcd.fillRect(fx + 3, fy + 3, fw - 6, fh - 6, TRACK_COLORS[track])
    else:
        M5.Lcd.drawRect(fx, fy, fw, fh, TRACK_COLORS[track])

    eye_w = 16 if energy else 14
    eye_h = 3 if blink else (18 if energy else 14)
    ey = fy + 16
    look = 0 if track == 3 else max(-3, min(3, (last_semi - 8) // 3))
    for side in (-1, 1):
        ex = fx + fw // 2 + side * 26 - eye_w // 2
        M5.Lcd.fillRect(ex, ey, eye_w, eye_h, 0xFFFFFF)
        if not blink:
            M5.Lcd.fillRect(ex + eye_w // 2 - 3 + look, ey + eye_h // 2 - 3, 6, 6, INK)

    mw = 26 + (energy * 22) // HIT_MAX
    mh = 4 + (energy * 14) // HIT_MAX
    mx = fx + (fw - mw) // 2
    my = fy + fh - 22
    M5.Lcd.fillRect(mx, my, mw, mh, INK)

    if hit[3]:                                  # percussion shakes the frame
        M5.Lcd.fillRect(fx - 6, fy + fh // 2, 4, 4, ORANGE)
        M5.Lcd.fillRect(fx + fw + 2, fy + fh // 2, 4, 4, ORANGE)


# --- RING: the 16 steps as a loop the playhead runs around ----------------
def draw_ring(full=False):
    top, h = anim_zone()
    M5.Lcd.fillRect(0, top, W, h, BG)
    if not ring_pts:
        build_ring()
    st = steps()
    for i, (x, y) in enumerate(ring_pts):
        on = st[i] is not None
        if i == play_step and playing:
            M5.Lcd.fillRect(x - 6, y - 6, 12, 12, ACCENT if recording else 0xFFFFFF)
        elif on:
            c = MUTED if muted[track] else TRACK_COLORS[track]
            M5.Lcd.fillRect(x - 4, y - 4, 8, 8, c)
        elif i % 4 == 0:
            M5.Lcd.fillRect(x - 2, y - 2, 4, 4, CELL_EDGE)
        else:
            M5.Lcd.fillRect(x - 1, y - 1, 2, 2, CELL_EDGE)

    energy = max(hit)
    cx, cy = W // 2, top + h // 2
    r = 4 + (energy * 12) // HIT_MAX
    try:
        M5.Lcd.fillCircle(cx, cy, r, TRACK_COLORS[track] if energy else CELL_EDGE)
    except Exception:
        M5.Lcd.fillRect(cx - r, cy - r, r * 2, r * 2,
                        TRACK_COLORS[track] if energy else CELL_EDGE)


# --- BARS: four channel meters, one per track ----------------------------
def draw_bars(full=False):
    top, h = anim_zone()
    M5.Lcd.fillRect(0, top, W, h, BG)
    seg = W // TRACKS
    bw = seg - 16
    base = top + h - TINY_H - 3
    maxh = h - TINY_H - 8
    for t in range(TRACKS):
        x = t * seg + (seg - bw) // 2
        lvl = 6 + (hit[t] * (maxh - 6)) // HIT_MAX
        c = MUTED if muted[t] else TRACK_COLORS[t]
        M5.Lcd.fillRect(x, base - maxh, bw, maxh, 0x0E0E0E)
        M5.Lcd.fillRect(x, base - lvl, bw, lvl, c)
        if hit[t] >= HIT_MAX - 1:
            M5.Lcd.fillRect(x, base - lvl - 3, bw, 3, 0xFFFFFF)
        M5.Lcd.setFont(TINY)
        M5.Lcd.setTextColor(c if t == track else DIM, BG)
        s = TRACK_NAMES[t]
        M5.Lcd.drawString(s, x + (bw - M5.Lcd.textWidth(s)) // 2, base + 2)


def draw_cartoon(full=False):
    if view == V_FACE:
        draw_face(full)
    elif view == V_RING:
        draw_ring(full)
    elif view == V_BARS:
        draw_bars(full)


def animate():
    """Advance the cartoon envelopes and repaint just the animation band."""
    global next_anim, blink, next_blink
    now = time.ticks_ms()
    if time.ticks_diff(now, next_anim) < 0:
        return
    next_anim = time.ticks_add(now, ANIM_MS)

    changed = False
    for t in range(TRACKS):
        if hit[t] > 0:
            hit[t] -= 1
            changed = True

    if time.ticks_diff(now, next_blink) >= 0:
        blink = 2 if blink == 0 else 0
        next_blink = time.ticks_add(now, 140 if blink else 1800 + (time.ticks_ms() % 1400))
        changed = True
    elif blink:
        changed = True

    if changed:
        draw_cartoon()


def redraw_all():
    M5.Lcd.fillScreen(BG)
    if view == V_HELP:
        draw_help()
        return
    if view == V_GRID:
        draw_header()
        draw_grid()
        draw_progress()
        draw_params()
        draw_status()
        return
    draw_topbar()
    build_ring()
    draw_cartoon(True)
    draw_params()
    draw_status()


# ------------------------------------------------------------------ musical
def generate():
    st = steps()
    for i in range(STEPS):
        st[i] = None
    if track == 3:
        for i in range(STEPS):
            if i % 4 == 0:
                st[i] = 0
            elif i % 8 == 4:
                st[i] = 1
            elif random.getrandbits(3) > 4:
                st[i] = 2 if random.getrandbits(2) else 3
        return
    sc = SCALES[scale_i][1]
    n = len(sc)
    deg = 0
    density = 5 if track == 1 else 6
    for i in range(STEPS):
        if track == 1 and i % 4 != 0 and random.getrandbits(3) < 6:
            continue
        if random.getrandbits(3) < density:
            deg = max(0, min(n + 4, deg + random.getrandbits(2) - 1))
            if track == 1 and i % 8 == 0:
                deg = 0
            st[i] = sc[deg % n] + 12 * (deg // n)


def clear_track():
    st = steps()
    for i in range(STEPS):
        st[i] = None


def save():
    global status
    try:
        import json
        with open(SAVE_PATH, "w") as f:
            json.dump({"v": 2, "pat": patterns, "bpm": bpm, "scale": scale_i,
                       "root": root, "oct": octave}, f)
        status = "saved"
    except Exception:
        status = "save failed"


def load():
    global patterns, bpm, scale_i, root, octave, status
    try:
        import json
        with open(SAVE_PATH) as f:
            d = json.load(f)
        if d.get("v") != 2:
            status = "old save"
            return
        patterns = d["pat"]
        bpm = d["bpm"]
        scale_i = d["scale"]
        root = d["root"]
        octave = d["oct"]
        status = "loaded"
    except Exception:
        status = "no save"


# ------------------------------------------------------------------ transport
def step_interval():
    return 60000.0 / (bpm * 4)


def schedule_next():
    global next_tick
    iv = step_interval()
    if swing:
        iv *= (1.0 - SWING_PCT / 100.0) if (play_step % 2) else (1.0 + SWING_PCT / 100.0)
    next_tick = time.ticks_add(next_tick, int(iv))


def advance():
    global play_step
    prev = play_step
    play_step = (play_step + 1) % STEPS

    chs = []
    for t in range(TRACKS):
        chs.extend(voices_for(t, patterns[pat][t][play_step]))
    balance(chs)

    for t in range(TRACKS):
        v = patterns[pat][t][play_step]
        if v is not None and not muted[t]:
            hit[t] = HIT_MAX
            if t != 3:
                globals()["last_semi"] = v
        voice(t, v, spread=t * SPREAD_MS)
    if view != V_GRID:
        draw_cartoon()
    if steps()[play_step] is not None:
        flash[play_step] = FLASH_MAX
    if view == V_GRID:
        draw_cell(prev)
        draw_cell(play_step)
        draw_progress()
    schedule_next()


def decay_flashes():
    global next_flash
    now = time.ticks_ms()
    if time.ticks_diff(now, next_flash) < 0:
        return
    next_flash = time.ticks_add(now, FLASH_MS)
    if view != V_GRID:
        return
    for i in range(STEPS):
        if flash[i] > 0:
            flash[i] -= 1
            draw_cell(i)


def quantized_step():
    rem = time.ticks_diff(next_tick, time.ticks_ms())
    if rem < step_interval() / 2:
        return (play_step + 1) % STEPS
    return play_step


# ------------------------------------------------------------------ input
def play_note(semi):
    global cursor
    live = voices_for(track, semi)
    if playing:
        chs = list(live)
        for t in range(TRACKS):
            if t != track:
                chs.extend(voices_for(t, patterns[pat][t][play_step]))
        balance(chs)
    else:
        balance(live)          # nothing else sounding — give it everything
    hit[track] = HIT_MAX
    if track != 3:
        globals()["last_semi"] = semi
    if view != V_GRID and view != V_HELP:
        draw_cartoon()
    voice(track, semi)
    if playing and recording:
        i = quantized_step()
        steps()[i] = semi
        flash[i] = FLASH_MAX
        if view == V_GRID:
            draw_cell(i)
    elif not playing:
        steps()[cursor] = semi
        flash[cursor] = FLASH_MAX
        if view == V_GRID:
            draw_cell(cursor)
    if view == V_GRID:
        draw_status()


def on_key(_kb):
    global cursor, track, pat, bpm, scale_i, swing, playing, recording
    global next_tick, view, status, dirty_all, play_step

    try:
        code = kb.get_key()
    except Exception:
        return
    if code is None or code < 0:
        return

    if code in (10, 13):
        recording = not recording
        if recording and not playing:
            playing = True
            play_step = STEPS - 1
            next_tick = time.ticks_ms()
        status = "rec" if recording else "rec off"
        dirty_all = True
        return

    ch = chr(code) if 0x20 <= code <= 0x7E else ""
    if not ch:
        return

    if ch == "\\":
        view = (view + 1) % len(VIEW_NAMES)
        status = VIEW_NAMES[view].lower()
        dirty_all = True
        return

    if view == V_HELP:
        if ch == "s":
            save()
        elif ch == "l":
            load()
        return

    if ch in WHITE_KEYS:
        i = WHITE_KEYS.index(ch)
        play_note(i if track == 3 else WHITE_SEMI[i])
        return
    if ch in BLACK_KEYS and track != 3:
        play_note(BLACK_KEYS[ch])
        return

    if ch in STEP_KEYS_A or ch in STEP_KEYS_B:
        i = STEP_KEYS_A.find(ch)
        i = i if i >= 0 else 8 + STEP_KEYS_B.find(ch)
        old = cursor
        cursor = i
        st = steps()
        st[i] = None if st[i] is not None else 0
        if st[i] is not None:
            voice(track, st[i])
            flash[i] = FLASH_MAX
        if view == V_GRID:
            draw_cell(old)
            draw_cell(i)
            draw_status()
        return

    if ch == " ":
        playing = not playing
        if playing:
            play_step = STEPS - 1
            next_tick = time.ticks_ms()
        else:
            recording = False
            for i in range(STEPS):
                flash[i] = 0
        status = "play" if playing else "stop"
    elif ch == "q":
        generate()
        status = "generated"
    elif ch == "r":
        clear_track()
        status = "cleared"
    elif ch == "i":
        muted[track] = not muted[track]
    elif ch == "'":
        pat = (pat + 1) % PATTERNS
    elif ch == ".":
        track = (track - 1) % TRACKS
        for i in range(STEPS):
            flash[i] = 0
    elif ch == "/":
        track = (track + 1) % TRACKS
        for i in range(STEPS):
            flash[i] = 0
    elif ch == "[":
        bpm = max(40, bpm - 4)
    elif ch == "]":
        bpm = min(240, bpm + 4)
    elif ch == "-":
        if track != 3:
            octave[track] = max(-2, octave[track] - 1)
    elif ch == "=":
        if track != 3:
            octave[track] = min(2, octave[track] + 1)
    elif ch == "`":
        scale_i = (scale_i + 1) % len(SCALES)
    elif ch == "9":
        swing = not swing
        status = "swing on" if swing else "swing off"
    elif ch == "0":
        cycle_volume()
    else:
        return
    dirty_all = True


def cycle_volume():
    global vol_i, status
    vol_i = (vol_i + 1) % len(VOLS)
    try:
        M5.Speaker.setVolume(VOLS[vol_i])
    except Exception:
        pass
    status = "vol %d" % (vol_i + 1)


# ------------------------------------------------------------------ lifecycle
def setup():
    global W, H, kb, kb_tick

    M5.begin()
    W = M5.Lcd.width()
    H = M5.Lcd.height()
    M5.Lcd.fillScreen(BG)
    try:
        M5.Lcd.setBrightness(150)
    except Exception:
        pass

    try:
        M5.Speaker.begin()
    except Exception:
        pass
    try:
        M5.Speaker.setVolume(VOLUME)
    except Exception:
        pass
    apply_mix()

    pick_fonts()
    layout()

    try:
        from hardware import MatrixKeyboard
        kb = MatrixKeyboard()
        kb.set_callback(on_key)
        kb_tick = getattr(kb, "tick", None)
    except Exception:
        kb = None
        kb_tick = None

    generate()
    redraw_all()


def loop():
    global dirty_all

    M5.update()
    if kb_tick:
        try:
            kb_tick()
        except Exception:
            pass

    if dirty_all:
        dirty_all = False
        redraw_all()

    flush_pending()

    if playing and time.ticks_diff(time.ticks_ms(), next_tick) >= 0:
        advance()

    decay_flashes()
    if view in (V_FACE, V_RING, V_BARS):
        animate()
    time.sleep_ms(2)


if __name__ == '__main__':
    try:
        setup()
        while True:
            loop()
    except (Exception, KeyboardInterrupt) as e:
        try:
            from utility import print_error_msg
            print_error_msg(e)
        except ImportError:
            print("please update to latest firmware")
