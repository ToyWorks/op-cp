# OP-CP — the main screen: fonts, layout, the roll, the header, the footer.
#
# Design language, so later edits do not drift from it:
#   * near-black ground; at most one saturated colour lit at a time
#   * flat primitives only — no gradients, no bevels, no outlines-plus-fills
#   * extreme type contrast: a ~3x jump between a label and the value it labels
#   * redraw only what changed; fillScreen per frame flickers visibly here
#
# The pattern is drawn as a piano roll with pitch encoded as height. That fits
# sixteen steps in one row instead of two, makes the shape of a phrase legible
# without reading any text, and takes text out of a 14px column entirely.

import M5

import opcp_conf as C
from opcp_state import S, fresh

# resolved in setup(); never hardcode either of these
W = H = 0
HERO = MID = TINY = None
HERO_H = MID_H = TINY_H = 0
ROLL_X = ROLL_Y = ROLL_W = ROLL_H = SW = 0
FOOT_Y = FOOT_H = 0
MARGIN = 0   # one left/right inset for every band — the roll's own inset, so
             # the header, the footer and the roll share their vertical edges

_last_footer = None
_last_head = None


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
    """Three sizes, deliberately far apart.

    An earlier layout drew everything at 15-16px, which is why it had no
    hierarchy: a label and the value it labelled looked equally important. This
    firmware exposes eight sizes — all the Montserrat/ASCII7 names are aliases
    of one typeface, verified on device — so a ~3x jump is available for free.
    """
    global HERO, MID, TINY, HERO_H, MID_H, TINY_H
    TINY = _font("DejaVu9")
    M5.Lcd.setFont(TINY)
    TINY_H = _fh(15)

    MID = _font("DejaVu12") or TINY
    M5.Lcd.setFont(MID)
    MID_H = _fh(16)

    HERO, HERO_H = TINY, TINY_H
    for name in ("DejaVu40", "DejaVu24", "DejaVu18", "DejaVu12"):
        f = _font(name)
        if f is None:
            continue
        M5.Lcd.setFont(f)
        h = _fh(0)
        if h and h <= H // 3:
            HERO, HERO_H = f, h
            break


def layout():
    global W, H, ROLL_X, ROLL_Y, ROLL_W, ROLL_H, SW, FOOT_Y, FOOT_H, MARGIN
    W = M5.Lcd.width()
    H = M5.Lcd.height()
    pick_fonts()

    SW = (W - 16) // C.STEPS
    ROLL_W = SW * C.STEPS
    ROLL_X = (W - ROLL_W) // 2
    MARGIN = ROLL_X

    FOOT_H = HERO_H
    FOOT_Y = H - FOOT_H
    ROLL_Y = TINY_H + 3
    ROLL_H = FOOT_Y - ROLL_Y - 4


# ------------------------------------------------------------------ the roll
def roll_rows():
    return len(C.DRUMS) if S.track == 3 else C.ROWS_MELODIC


def roll_geom():
    """(rows, row height, top of the lane block).

    The lane block starts right under the mark strip and runs to the bottom of
    the roll, so a column reads as one object: mark on top, lanes below. An
    earlier version sized the block to rows*rh and left a gap, which made the
    mark look like a stray dash floating over the background.
    """
    rows = roll_rows()
    top = ROLL_Y + C.MARK_H + 1
    rh = max(2, (ROLL_Y + ROLL_H - top) // rows)
    return rows, rh, top


def step_label(t, val):
    """Short name for a step's value — drums by abbreviation, notes by name."""
    if val is None:
        return ""
    if t == 3:
        return C.DRUMS[val % len(C.DRUMS)][0]
    import opcp_audio as A
    return C.NOTE_NAMES[A.semi_to_midi(val, t) % 12]


def note_color(i):
    if S.muted[S.track]:
        return C.MUTED
    f = S.flash[i]
    if f >= C.FLASH_MAX:
        return 0xFFFFFF
    if f > 0:
        return C.TRACK_LIGHT[S.track]
    return C.TRACK_COLORS[S.track]


def draw_step(i):
    """One column of the roll: lane background, the note, and the head mark."""
    x = ROLL_X + i * SW
    w = SW - 1
    rows, rh, top = roll_geom()
    lane_h = ROLL_Y + ROLL_H - top

    live = S.playing and i == S.play_step
    here = (not S.playing) and i == S.cursor
    if live or here:
        bg = C.TRACK_DEEP[S.track]
    elif i % 4 == 0:
        bg = C.RAIL_BEAT
    else:
        bg = C.RAIL
    M5.Lcd.fillRect(x, top, w, lane_h, bg)

    val = S.steps()[i]
    if val is not None:
        idx = val if val >= 0 else 0
        if idx > rows - 1:
            idx = rows - 1
        # row edges spread the integer-division remainder over the rows, so the
        # lowest note reaches the bottom of the lane instead of leaving a dead
        # band of rows*rh vs lane_h slack under it
        r = rows - 1 - idx
        y0 = top + (r * lane_h) // rows
        nh = top + ((r + 1) * lane_h) // rows - y0
        M5.Lcd.fillRect(x, y0, w, nh if nh < 3 else nh - 1, note_color(i))

    # the head mark rides above the lanes so a note never hides the playhead
    if live:
        M5.Lcd.fillRect(x, ROLL_Y, w, C.MARK_H,
                        C.ACCENT if S.recording else 0xFFFFFF)
    elif here:
        M5.Lcd.fillRect(x, ROLL_Y, w, C.MARK_H, C.TRACK_COLORS[S.track])


def draw_roll():
    M5.Lcd.fillRect(0, ROLL_Y, W, ROLL_H, C.BG)
    for i in range(C.STEPS):
        draw_step(i)


# ------------------------------------------------------------------ header
def head_state():
    return (S.track, S.pat, S.playing, S.recording, tuple(S.muted),
            S.status if fresh(S.status_until) else "")


def head_changed():
    return _last_head != head_state()


def draw_head():
    """One tiny line: who you are editing, what is happening, where you are."""
    global _last_head
    M5.Lcd.fillRect(0, 0, W, TINY_H + 2, C.BG)
    M5.Lcd.setFont(TINY)

    M5.Lcd.setTextColor(C.MUTED if S.muted[S.track]
                        else C.TRACK_COLORS[S.track], C.BG)
    name = C.TRACK_NAMES[S.track]
    M5.Lcd.drawString(name, MARGIN, 0)
    x = MARGIN + M5.Lcd.textWidth(name) + 8

    # four pips: the current track solid, the rest barely there. A muted track
    # reads as a hollow outline rather than as a second colour.
    for t in range(C.TRACKS):
        c = C.TRACK_COLORS[t] if t == S.track else C.FAINT
        if S.muted[t]:
            M5.Lcd.drawRect(x, 5, 5, 5, c)
        else:
            M5.Lcd.fillRect(x, 5, 5, 5, c)
        x += 8

    right = S.status if fresh(S.status_until) else "P%d" % (S.pat + 1)
    M5.Lcd.setTextColor(C.ACCENT if S.recording else C.DIM, C.BG)
    sq = W - MARGIN - 6          # the state square's right edge sits on the grid
    M5.Lcd.drawString(right, sq - 4 - M5.Lcd.textWidth(right), 0)

    if S.recording:
        M5.Lcd.fillRect(sq, 4, 6, 6, C.ACCENT)
    elif S.playing:
        M5.Lcd.fillRect(sq, 4, 6, 6, C.FG)
    else:
        M5.Lcd.drawRect(sq, 4, 6, 6, C.FAINT)
    _last_head = head_state()


# ------------------------------------------------------------------ footer
def spaced_width(s, extra):
    if not s:
        return 0
    return M5.Lcd.textWidth(s) + extra * (len(s) - 1)


def draw_spaced(s, x, y, extra):
    """Draw a string with extra tracking, advancing per glyph.

    Needed because this typeface gives the numeral 1 a foot serif: set solid,
    "112" merges its three bases into one continuous bar and the number reads
    as underlined. Tracking breaks the bar up — and wide-set numerals are the
    right look here anyway.
    """
    for ch in s:
        M5.Lcd.drawString(ch, x, y)
        x += M5.Lcd.textWidth(ch) + extra
    return x


def _readouts():
    r1 = "%s %s" % (C.SCALES[S.scale_i][0],
                    "--" if S.track == 3 else "%+d" % S.octave[S.track])
    r2 = "SWING" if S.swing else "STRAIGHT"
    return r1, r2


def footer_changed():
    label, value = S.hero()
    r1, r2 = _readouts()
    return _last_footer != (label, value, r1, r2)


def draw_footer():
    """One big number, two tiny readouts, one hairline. Nothing else.

    An earlier footer spent 27% of the panel on four saturated blocks holding
    four values that change once a session. Those values are still here — they
    are just no longer shouting.
    """
    global _last_footer
    M5.Lcd.fillRect(0, FOOT_Y - 2, W, H - FOOT_Y + 2, C.BG)
    M5.Lcd.fillRect(MARGIN, FOOT_Y - 2, W - 2 * MARGIN, 1, C.FAINT)

    label, value = S.hero()
    M5.Lcd.setFont(HERO)
    M5.Lcd.setTextColor(C.FG, C.BG)
    draw_spaced(value, MARGIN, FOOT_Y + (FOOT_H - HERO_H) // 2, C.HERO_TRACK)
    vw = spaced_width(value, C.HERO_TRACK)

    M5.Lcd.setFont(TINY)
    M5.Lcd.setTextColor(C.DIM, C.BG)
    M5.Lcd.drawString(label, MARGIN + vw + 6, FOOT_Y + FOOT_H - TINY_H - 3)

    r1, r2 = _readouts()
    top = FOOT_Y + (FOOT_H - 2 * TINY_H) // 2
    for n, s in ((0, r1), (1, r2)):
        M5.Lcd.setTextColor(C.DIM if n else C.FG, C.BG)
        M5.Lcd.drawString(s, W - M5.Lcd.textWidth(s) - MARGIN, top + n * TINY_H)
    _last_footer = (label, value, r1, r2)


# ------------------------------------------------------------------ help
# Each row is (key, action) segments: keys bright, actions dim, so the eye can
# scan just the keys. No track colour appears here — on every other screen a
# lit colour means "the track you are editing", and help must not dilute that.
# ^X means ctrl+X: the functions that used to squat in the piano rows.
HELP = (
    (("SPACE", C.FG), ("play/stop", C.DIM)),
    (("ENTER", C.FG), ("record", C.DIM)),
    (("\\", C.FG), ("views", C.DIM), ("^F", C.FG), ("files", C.DIM)),
    (("^G", C.FG), ("gen", C.DIM), ("^C", C.FG), ("clear", C.DIM)),
    (("^M", C.FG), ("mute", C.DIM), ("^P", C.FG), ("bank", C.DIM)),
    (("^[ ^]", C.FG), ("bpm", C.DIM), ("^N", C.FG), ("link", C.DIM)),
    (("- =", C.FG), ("octave", C.DIM)),
    (("`", C.FG), ("scale", C.DIM), ("9", C.FG), ("swing", C.DIM)),
    (("0", C.FG), ("volume", C.DIM)),
    ((". /", C.FG), ("track", C.DIM)),
    (("1-8 z-,", C.FG), ("steps", C.DIM)),
)


def keybed_geom():
    """(pitch, cap w, cap h, left x, top y) of the keybed diagram.

    Shared by draw and layout so the command list starts below the real bottom
    of the diagram, whatever the panel size.
    """
    n = len(C.WHITE_KEYS)
    p = (W - 2 * MARGIN + 1) // n
    return p, p - 1, TINY_H + 2, (W - (p * n - 1)) // 2, 2


def _black_gap(semi):
    """Which white-key boundary a black key sits over, from its semitone."""
    for i, s in enumerate(C.WHITE_SEMI):
        if s > semi:
            return i
    return len(C.WHITE_SEMI) - 1


def draw_keybed():
    """The middle two keyboard rows drawn as the piano they are.

    White caps carry the home row; the black caps sit in the gaps above, offset
    by half a key, exactly as on the physical keybed. A picture of the mapping
    beats the two rows of monospaced art this page used to open with.
    """
    p, kw, kh, x0, y0 = keybed_geom()
    M5.Lcd.setFont(TINY)
    wy = y0 + kh + 1
    for i, ch in enumerate(C.WHITE_KEYS):
        x = x0 + i * p
        M5.Lcd.fillRect(x, wy, kw, kh, C.FG)
        M5.Lcd.setTextColor(C.INK, C.FG)
        M5.Lcd.drawString(ch, x + (kw - M5.Lcd.textWidth(ch)) // 2, wy + 1)
    for ch, semi in C.BLACK_KEYS.items():
        x = x0 + _black_gap(semi) * p - p // 2
        M5.Lcd.fillRect(x, y0, kw, kh, C.FAINT)
        M5.Lcd.setTextColor(C.FG, C.FAINT)
        M5.Lcd.drawString(ch, x + (kw - M5.Lcd.textWidth(ch)) // 2, y0 + 1)


def help_layout():
    """Position every (text, colour) segment of the command list.

    The list packs into columns under the keybed: fill a column until it runs
    out of height, then start the next one, sized to the widest row it holds.
    Within a row a key token is followed tightly by its action, with a wider
    gap before the next pair. Draw and self-test share this function so both
    agree on the result.
    """
    M5.Lcd.setFont(TINY)
    _, _, kh, _, y0 = keybed_geom()
    top = y0 + 2 * kh + 6
    lh = TINY_H
    per_col = max(1, (H - top - 2) // lh)
    out = []
    x0, y, col_w = MARGIN, top, 0
    for i, row in enumerate(HELP):
        if i and i % per_col == 0:
            x0 += col_w + 14
            y, col_w = top, 0
        x = x0
        for n, (text, c) in enumerate(row):
            out.append((x, y, text, c))
            x += M5.Lcd.textWidth(text) + (3 if n % 2 == 0 else 8)
        if x - x0 > col_w:
            col_w = x - x0
        y += lh
    return out


def draw_help():
    M5.Lcd.fillScreen(C.BG)
    draw_keybed()
    M5.Lcd.setFont(TINY)
    for x, y, text, c in help_layout():
        M5.Lcd.setTextColor(c, C.BG)
        M5.Lcd.drawString(text, x, y)
