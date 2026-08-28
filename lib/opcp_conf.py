# OP-CP — everything that never changes at runtime.
#
# Constants only: no state, no imports from the rest of the program. That makes
# this the one module every other one may import without thinking about cycles.

# ------------------------------------------------------------------ transport
BPM = 112
STEPS = 16
TRACKS = 4
PATTERNS = 4
SWING_PCT = 18
SLOTS = 8                    # save slots — one per step key on the top row
LINK_CHANNEL = 1             # ESP-NOW broadcast to the StackChan; both ends
                             # pin channel 1 (see lib/opcp_link.py)

# ------------------------------------------------------------------ audio
VOLUME = 255                 # master out, 0-255
MIX_BUDGET = 255             # total channel volume allowed to sound at once.
                             # Lower it if dense steps still clip.
MAX_CH_VOL = 255
FIFTHS = False
SPREAD_MS = 4
# Six positions, and the first is silence. The 0 key cycles them, so the
# instrument can be muted from its own keyboard without unplugging it or
# reaching for a host — which is what you want on a desk beside someone
# else's meeting. S.vol_i IS the number shown, so it reads 0..5.
VOLS = (0, 90, 140, 190, 225, 255)
CH_TRIM = {0: 1.0, 1: 1.0, 2: 0.85, 4: 0.55, 5: 1.0, 6: 0.5}

# ------------------------------------------------------------------ palette
# Every grey is a multiple of 0x10. That is not tidiness — the panel is RGB565,
# where green keeps 6 bits and red/blue only 5, so an arbitrary grey like
# 0x0E0E0E quantises to rgb(8,12,8) and the whole background picks up a green
# cast. Multiples of 0x10 land on the same value in all three channels.
#
# The rule the UI follows: at most ONE saturated colour is lit at a time, and it
# always means "the track you are editing". Colour is information, never
# decoration.
BG = 0x000000
RAIL = 0x101010          # the roll's background lanes
RAIL_BEAT = 0x202020     # every fourth column, so the bar is countable
INK = 0x000000
FAINT = 0x303030         # hairlines, inactive marks
DIM = 0x707070           # labels — present, never competing
FG = 0xF0F0F0            # values
ACCENT = 0xFF2A17        # record only. Nothing else may use it.
MUTED = 0x404040

# Four encoder colours, one per track — and *only* per track. An earlier version
# reused them for parameter slots too; a colour that means two things means
# nothing.
BLUE, GREEN, WHITE, ORANGE = 0x2E7BFF, 0x35C75A, 0xEDEDED, 0xFF8A1E
TRACK_COLORS = (BLUE, GREEN, WHITE, ORANGE)
TRACK_LIGHT = (0x9CC4FF, 0x9AE8AE, 0xFFFFFF, 0xFFC98F)
TRACK_DEEP = (0x081428, 0x081C0C, 0x202020, 0x201400)

# ------------------------------------------------------------------ layout
ROWS_MELODIC = 17        # pitch lanes; generate() can exceed this, so the lane
                         # index is clamped rather than trusted
MARK_H = 3               # the playhead/cursor strip above the lanes
HERO_TRACK = 3           # letterspacing for the hero value, in px
HERO_MS = 1400           # how long a touched parameter owns the big number
STATUS_MS = 1200
FLASH_MAX = 3
FLASH_MS = 45
HIT_MAX = 6
ANIM_MS = 55

V_ROLL, V_FACE, V_RING, V_BARS, V_FILES, V_HELP = 0, 1, 2, 3, 4, 5
VIEW_NAMES = ("ROLL", "FACE", "RING", "BARS", "FILES", "HELP")

# ------------------------------------------------------------------ musical
TRACK_NAMES = ("LEAD", "BASS", "KEYS", "PERC")
SCALES = (
    ("MAJ", (0, 2, 4, 5, 7, 9, 11)),
    ("MIN", (0, 2, 3, 5, 7, 8, 10)),
    ("PEN", (0, 3, 5, 7, 10)),
    ("CHR", (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)),
)
# Two-character names: the roll shows drums as lane height, but these still have
# to fit the hero slot and the help page. They are the standard drum-machine
# abbreviations, so nothing is lost by keeping them short.
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

# ------------------------------------------------------------------ keybed
# The middle two keyboard rows are a piano: white keys on the home row, black
# keys in the physical gaps above them. Those two rows hold NOTHING but piano:
# every function that used to squat between the keys (q r i ' [ ]) lives on
# the ctrl layer now, so a missed black key can no longer wipe a track.
WHITE_KEYS = "asdfghjkl;"
WHITE_SEMI = (0, 2, 4, 5, 7, 9, 11, 12, 14, 16)
BLACK_KEYS = {"w": 1, "e": 3, "t": 6, "y": 8, "u": 10, "o": 13, "p": 15}
STEP_KEYS_A = "12345678"
STEP_KEYS_B = "zxcvbnm,"

# The ctrl key's own keycode in the ADV keyboard driver's pressed-key table;
# MatrixKeyboard.is_key_pressed(KEY_CTRL) is True while it is physically held
# (verified in uiflow-micropython 2.5.0 source). Mnemonic ctrl-layer bindings:
# G generate, C clear, M mute, P pattern, [ ] tempo, F files.
KEY_CTRL = 0x80

# ------------------------------------------------------------------ presets
# Four factory patterns, one per key on the black-key row's first four keys.
# A preset lands in the CURRENT pattern slot, so ctrl+P then a preset key
# stacks different grooves into different banks. Values are the same semitone
# offsets (melodic) and drum indices (PERC) the generator writes.
_N = None
PRESET_KEYS = "wety"
PRESETS = (
    # (name, bpm, scale index, per-track octave, 4 tracks x 16 steps)
    ("ACID", 128, 1, (0, -1, 0, 0), (
        (_N, _N, 12, _N, _N, 15, _N, _N, _N, _N, 12, _N, 10, _N, _N, _N),
        (0, _N, 0, 12, 0, _N, 3, _N, 0, _N, 0, 12, 5, _N, 3, _N),
        (_N,) * 16,
        (0, 2, 2, 2, 0, 2, 3, 2, 0, 2, 2, 2, 0, 7, 3, 2))),
    ("DISCO", 118, 0, (0, -1, 0, 0), (
        (_N, _N, _N, _N, _N, _N, _N, _N, _N, _N, 9, _N, 7, _N, 4, _N),
        (0, _N, 12, _N, 0, _N, 12, _N, 5, _N, 17, _N, 7, _N, 19, _N),
        (_N, _N, 4, _N, _N, _N, 4, _N, _N, _N, 5, _N, _N, _N, 7, _N),
        (0, _N, 3, _N, 0, _N, 3, _N, 0, _N, 3, _N, 0, _N, 3, 7))),
    ("DUB", 76, 1, (0, -1, 0, 0), (
        (_N,) * 16,
        (0, _N, _N, _N, _N, _N, _N, 10, _N, _N, _N, _N, 7, _N, _N, _N),
        (_N, _N, _N, _N, 3, _N, _N, _N, _N, _N, _N, _N, 7, _N, _N, _N),
        (0, _N, _N, _N, 1, _N, _N, 2, _N, _N, 0, _N, 1, _N, 4, _N))),
    ("CHIP", 140, 0, (0, -1, 0, 0), (
        (0, 4, 7, 12, 7, 4, 0, 4, 2, 5, 9, 14, 9, 5, 2, 5),
        (0, _N, 0, _N, 0, _N, 0, _N, 2, _N, 2, _N, 2, _N, 2, _N),
        (_N, _N, 12, _N, _N, _N, 11, _N, _N, _N, 14, _N, _N, _N, 12, _N),
        (0, 2, 1, 2, 0, 2, 1, 2, 0, 2, 1, 2, 0, 2, 1, 7))),
)
