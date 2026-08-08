# OP-CP — all mutable state, in one object.
#
# The program used to keep this as ~35 module globals, which meant every
# function that touched any of it needed a `global` line and nothing could be
# split into modules without threading arguments everywhere. One singleton
# fixes both: other modules do `from opcp_state import S` and read S.track,
# S.bpm, S.playing directly. It is the same shared mutable state as before, but
# now it has a name and lives in one file.

import time

import opcp_conf as C


class Seq:
    def __init__(self):
        # pattern data -------------------------------------------------
        self.patterns = [[[None] * C.STEPS for _ in range(C.TRACKS)]
                         for _ in range(C.PATTERNS)]
        self.pat = 0
        self.track = 0
        self.cursor = 0

        # per-track voicing --------------------------------------------
        self.octave = [0, -1, 0, 0]
        self.muted = [False] * C.TRACKS
        self.scale_i = 1
        self.root = 57

        # transport ----------------------------------------------------
        self.bpm = C.BPM
        self.swing = True
        self.playing = False
        self.recording = False
        self.play_step = 0
        self.next_tick = 0
        self.vol_i = len(C.VOLS) - 1

        # presentation -------------------------------------------------
        self.view = C.V_ROLL
        self.dirty_all = True     # full repaint incl. fillScreen — view switch only
        self.dirty_body = False   # just the roll / animation band
        self.flash = [0] * C.STEPS      # per-step trigger decay, for the roll
        self.next_flash = 0
        self.hit = [0] * C.TRACKS       # per-track trigger decay, for the views
        self.next_anim = 0
        self.blink = 0
        self.next_blink = 0
        self.last_semi = 0
        self.ring_pts = []

        # the hero slot: whatever parameter you touched last owns the big
        # number for a moment, then it falls back to the tempo
        self.hero_label = "BPM"
        self.hero_value = ""
        self.hero_until = 0
        self.status = "ready"
        self.status_until = 0

        # audio scheduling ---------------------------------------------
        self.pending = []
        self.kb = None
        self.kb_tick = None

        # link: broadcast each step over ESP-NOW for the dancing StackChan.
        # On by default — a broadcast nobody hears costs nothing; ctrl+N.
        self.link_on = True

        # persistence: storage_init() points save_dir at the SD card when one
        # mounts, so patterns survive a firmware reflash. slot_meta caches
        # (bpm, scale) per slot so the FILES view never reads files to draw —
        # opcp_seq writes it, opcp_screen reads it, and no import cycle forms.
        self.save_dir = "/flash"
        self.slot_meta = [None] * C.SLOTS
        self.files_arm = False        # FILES: next slot digit saves, not loads

    # -- convenience ---------------------------------------------------
    def steps(self):
        """The step list of the track currently being edited."""
        return self.patterns[self.pat][self.track]

    def set_hero(self, label, value):
        self.hero_label = label
        self.hero_value = str(value)
        self.hero_until = time.ticks_add(time.ticks_ms(), C.HERO_MS)

    def hero(self):
        if self.hero_value and fresh(self.hero_until):
            return self.hero_label, self.hero_value
        return "BPM", str(self.bpm)

    def set_status(self, s):
        self.status = s
        self.status_until = time.ticks_add(time.ticks_ms(), C.STATUS_MS)

    def clear_flashes(self):
        for i in range(C.STEPS):
            self.flash[i] = 0


def fresh(until):
    """True while a timestamp set with ticks_add is still in the future."""
    return bool(until) and time.ticks_diff(until, time.ticks_ms()) > 0


S = Seq()
