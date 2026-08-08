# Headless self-test for app.py — this is what `make check` runs on the device.
#
# app.py ends in `while True: loop()`, so `mpremote run app.py` never returns
# and any automation built on it hangs forever. This module imports app instead
# of running it (the `__main__` guard keeps the real loop from starting), drives
# setup() and a bounded number of frames, and prints the numbers a human would
# otherwise have to read off the screen: resolution, every layout coordinate,
# measured string widths, resolved font names, free memory.
#
# It cannot see the screen. What it CAN prove is that every computed rectangle
# lands inside the panel, that no two regions overlap, that every string fits
# the box it is drawn into, and that no code path raises. Whether the result
# looks good is still a human question.

import gc
import time

FAIL = []
WARN = []


def check(cond, msg):
    if cond:
        print("  ok    %s" % msg)
    else:
        print("  FAIL  %s" % msg)
        FAIL.append(msg)


def warn(cond, msg):
    if not cond:
        print("  warn  %s" % msg)
        WARN.append(msg)


class FakeKb:
    """Stands in for MatrixKeyboard so on_key() can be driven from a script."""

    def __init__(self):
        self.queue = []
        self.ctrl = False

    def feed(self, codes):
        self.queue = list(codes)

    def get_key(self):
        return self.queue.pop(0) if self.queue else -1

    def is_key_pressed(self, keycode):
        return self.ctrl and keycode == C.KEY_CTRL


def banner(s):
    print("\n== %s" % s)


gc.collect()
mem_start = gc.mem_free()

banner("import + setup")
import app
import opcp_conf as C
import opcp_screen as SC
import opcp_seq as Q
import opcp_ui as U
from opcp_state import S

C.VOLUME = 60            # audible enough to prove the speaker, quiet enough
                         # not to startle whoever is holding the thing
app.setup()
print("  screen        %dx%d" % (U.W, U.H))
check(U.W > 0 and U.H > 0, "display reports a size")
check(S.kb is not None, "MatrixKeyboard bound")

banner("fonts")
for label, font, height in (("HERO", U.HERO, U.HERO_H),
                            ("MID ", U.MID, U.MID_H),
                            ("TINY", U.TINY, U.TINY_H)):
    print("  %-5s font=%s height=%d" % (label, font, height))
    check(font is not None, "%s font resolved" % label)
    check(height > 0, "%s font height > 0" % label)
check(U.HERO_H >= U.TINY_H * 2,
      "hero/label type contrast is at least 2x (%d vs %d)" % (U.HERO_H, U.TINY_H))

banner("layout")
roll_r = U.ROLL_X + C.STEPS * U.SW
rows, rh, lane_top = U.roll_geom()
print("  header        y 0..%d" % U.TINY_H)
print("  roll          x %d..%d  y %d..%d  step w %d"
      % (U.ROLL_X, roll_r, U.ROLL_Y, U.ROLL_Y + U.ROLL_H, U.SW))
print("  lanes         %d rows x %dpx, top %d" % (rows, rh, lane_top))
print("  footer        y %d..%d  (h %d)" % (U.FOOT_Y, U.FOOT_Y + U.FOOT_H, U.FOOT_H))

check(U.ROLL_X >= 0 and roll_r <= U.W, "roll within width")
check(U.ROLL_Y >= U.TINY_H, "roll clears the header")
check(U.ROLL_Y + U.ROLL_H <= U.FOOT_Y, "roll does not overlap footer")
check(U.FOOT_Y + U.FOOT_H <= U.H, "footer within height")
check(U.SW >= 8, "step column wide enough to see (%dpx)" % U.SW)
for t in range(C.TRACKS):
    S.track = t
    r, h_, top = U.roll_geom()
    check(top >= U.ROLL_Y, "%s lanes start inside the roll (%d >= %d)"
          % (C.TRACK_NAMES[t], top, U.ROLL_Y))
    check(top + r * h_ <= U.ROLL_Y + U.ROLL_H,
          "%s lanes end inside the roll" % C.TRACK_NAMES[t])
    check(h_ >= 2, "%s lane at least 2px tall (%d)" % (C.TRACK_NAMES[t], h_))
S.track = 0

banner("text fits its box")
U.M5.Lcd.setFont(U.HERO)
for v in ("240", "+2", "MIN", "16"):
    w = U.spaced_width(v, C.HERO_TRACK)
    check(w <= U.W // 2, "hero value %-4s %3dpx <= %dpx" % (v, w, U.W // 2))

U.M5.Lcd.setFont(U.TINY)
# the footer draws hero value, its label, and a right-hand readout on one line
worst_hero = max(U.M5.Lcd.textWidth(l) for l in
                 ("BPM", "OCT", "SCALE", "BANK", "VOL", "STEP 16", "NOTE"))
worst_right = 0
for sc, _ in C.SCALES:
    for oc in ("+2", "-2", "--"):
        worst_right = max(worst_right, U.M5.Lcd.textWidth("%s %s" % (sc, oc)))
worst_right = max(worst_right, U.M5.Lcd.textWidth("STRAIGHT"))
U.M5.Lcd.setFont(U.HERO)
hero_w = max(U.spaced_width(v, C.HERO_TRACK) for v in ("240", "MIN", "C#"))
total = U.MARGIN + hero_w + 6 + worst_hero + 8 + worst_right + U.MARGIN
print("  footer worst case: hero %d + label %d + readout %d = %d of %d"
      % (hero_w, worst_hero, worst_right, total, U.W))
check(total <= U.W, "footer worst case fits on one line (%d <= %d)" % (total, U.W))

U.M5.Lcd.setFont(U.TINY)
head_w = U.MARGIN + max(U.M5.Lcd.textWidth(n) for n in C.TRACK_NAMES) + 8 + 4 * 8
worst_status = max(U.M5.Lcd.textWidth(x) for x in
                   ("STRAIGHT", "UNMUTE", "ARMED OFF", "P1", "SAVE 1-8?",
                    "SAVED 8", "SAVE FAIL", "LOADED 8", "NO SAVE", "OLD SAVE",
                    "LINK ON", "LINK OFF", "LINK FAIL")
                   + C.VIEW_NAMES + tuple(p[0] for p in C.PRESETS))
head_total = head_w + 4 + worst_status + 4 + 6 + U.MARGIN
print("  header worst case: left %d + status %d + square = %d of %d"
      % (head_w, worst_status, head_total, U.W))
check(head_total <= U.W, "header worst case fits")

right = bottom = 0
for x, y, text, _ in U.help_layout():
    w = U.M5.Lcd.textWidth(text)
    if x + w > right:
        right = x + w
    if y + U.TINY_H > bottom:
        bottom = y + U.TINY_H
print("  help page occupies %dx%d of %dx%d" % (right, bottom, U.W, U.H))
check(right <= U.W - 2, "help page fits horizontally (%d <= %d)" % (right, U.W - 2))
check(bottom <= U.H, "help page fits vertically (%d <= %d)" % (bottom, U.H))

kp, kkw, kkh, kx0, ky0 = U.keybed_geom()
kb_right = kx0 + kp * len(C.WHITE_KEYS) - 1
kb_bottom = ky0 + 2 * kkh + 1
print("  keybed        x %d..%d  y %d..%d" % (kx0, kb_right, ky0, kb_bottom))
check(kx0 >= 0 and kb_right <= U.W, "keybed fits horizontally")
check(kb_bottom < U.TINY_H * 3, "keybed leaves room for the command list")

U.M5.Lcd.setFont(U.TINY)
colw = (U.W - 2 * U.MARGIN) // 3
worst_slot = 12 + max(U.M5.Lcd.textWidth("240 %s" % sc) for sc, _ in C.SCALES)
worst_pre = 12 + max(U.M5.Lcd.textWidth(p[0]) for p in C.PRESETS)
print("  files cols    %dpx wide; slot row %d, preset row %d"
      % (colw, worst_slot, worst_pre))
check(worst_slot <= colw - 4, "files slot row fits its column")
check(worst_pre <= colw - 4, "files preset row fits its column")

banner("every view renders")
for idx, name in enumerate(C.VIEW_NAMES):
    S.view = idx
    t0 = time.ticks_ms()
    SC.redraw_all()
    print("  %-5s full redraw %4d ms" % (name, time.ticks_diff(time.ticks_ms(), t0)))
S.view = C.V_ROLL

banner("transport: 2 bars of playback")
S.playing = True
S.play_step = C.STEPS - 1
S.next_tick = time.ticks_ms()
frames = 0
t0 = time.ticks_ms()
target = int(2 * C.STEPS * Q.step_interval()) + 200
while time.ticks_diff(time.ticks_ms(), t0) < target:
    app.loop()
    frames += 1
elapsed = time.ticks_diff(time.ticks_ms(), t0)
print("  %d frames in %d ms  (%d fps)" % (frames, elapsed, frames * 1000 // elapsed))
check(frames > 100, "loop is actually iterating")
check(S.play_step != C.STEPS - 1, "playhead advanced")
S.playing = False

banner("key handling: every documented binding")
real_kb, real_tick = S.kb, S.kb_tick
fake = FakeKb()
S.kb, S.kb_tick = fake, None

bindings = (C.WHITE_KEYS + "".join(C.BLACK_KEYS.keys())
            + C.STEP_KEYS_A + C.STEP_KEYS_B
            + " ./-=`90\\")
ctrl_bindings = "gcmp[]fn" + "ax"    # the ctrl layer, plus swallowed letters
                                     # ('n' appears once per track: 4 toggles
                                     # leave the link exactly as it started)
for t in range(C.TRACKS):
    S.track = t
    S.view = C.V_ROLL
    for ch in bindings:
        fake.feed([ord(ch)])
        __import__('opcp_keys').on_key(None)
        app.loop()
    fake.ctrl = True
    for ch in ctrl_bindings:
        fake.feed([ord(ch)])
        __import__('opcp_keys').on_key(None)
        app.loop()
    fake.ctrl = False
    fake.feed([13])              # ENTER: record arm
    __import__('opcp_keys').on_key(None)
    app.loop()
print("  drove %d bare + %d ctrl keys x %d tracks, no exception"
      % (len(bindings) + 1, len(ctrl_bindings), C.TRACKS))
check(True, "all key bindings dispatch cleanly")

# FILES: bare digits load, s arms a save, preset keys drop a pattern in
S.view = C.V_FILES
S.dirty_all = True
app.loop()
for ch, expect in (("s", "SAVE 1-8?"), ("4", "SAVED 4"),
                   ("4", "LOADED 4"), ("w", C.PRESETS[0][0])):
    fake.feed([ord(ch)])
    __import__('opcp_keys').on_key(None)
    app.loop()
    check(S.status == expect, "FILES key %r -> %r" % (ch, S.status))
check(S.slot_meta[3] is not None, "slot meta cache updated by save")
S.view = C.V_ROLL

S.kb, S.kb_tick = real_kb, real_tick
S.playing = False
S.recording = False
S.track = 0
S.view = C.V_ROLL

banner("sound")
import opcp_audio as A
print("  kit loaded:   %s  (%d sounds)" % (A.kit_ok, len(A.KIT)))
check(A.kit_ok, "PCM kit loaded from %s" % A.KIT_PATH)
if A.kit_ok:
    kb = sum(len(b) for b in A.KIT.values())
    print("  kit size:     %d bytes of int16 PCM at %d Hz" % (kb, A.RATE_BASE))
    for nm in ("BD", "SD", "HH", "V0", "V1", "V2"):
        check(nm in A.KIT, "kit has %s" % nm)
    # Every pitch the app can produce must land on a rate the driver handles,
    # and must stay in tune: octave folding is allowed, detuning is not.
    for midi in (33, 45, 57, 69, 81, 93, 100):
        r = A.rate_for(midi)
        ideal = A.RATE_BASE * (2.0 ** ((midi - A.BASE_MIDI) / 12.0))
        ratio = r / ideal
        octaves = 0
        while ratio > 1.5:
            ratio /= 2.0
            octaves += 1
        while ratio < 0.75:
            ratio *= 2.0
            octaves -= 1
        check(A.RATE_MIN <= r <= A.RATE_MAX,
              "midi %3d -> %5d Hz, within %d..%d" % (midi, int(r),
                                                     A.RATE_MIN, A.RATE_MAX))
        check(abs(ratio - 1.0) < 0.001,
              "midi %3d stays in tune (octave shift %+d)" % (midi, octaves))
else:
    warn(False, "no PCM kit — the app is falling back to tone() beeps")

banner("esp-now link")
import opcp_link as L
check(L.begin(), "espnow up on channel %d" % C.LINK_CHANNEL)
L.send_step(0, 0x0B, 0)
L.send_transport(True)
L.send_transport(False)
check(True, "step and transport broadcasts do not raise")

banner("persistence")
print("  save dir      %s   slots [%s]"
      % (S.save_dir, "".join("x" if m else "-" for m in S.slot_meta)))
warn(S.save_dir == "/sd", "no SD card mounted — saves are on /flash only")
Q.save_slot(0)
print("  save -> %s" % S.status)
check(S.status == "SAVED 1", "pattern saved (status %r)" % S.status)
try:
    with open(Q.slot_path(0)) as f:
        f.read(1)
    on_disk = True
except Exception:
    on_disk = False
check(on_disk, "save file readable at %s" % Q.slot_path(0))
Q.load_slot(0)
print("  load -> %s" % S.status)
check(S.status == "LOADED 1", "pattern loaded back")
Q.load_preset(1)
check(S.bpm == C.PRESETS[1][1],
      "preset %s applies its tempo (%d)" % (C.PRESETS[1][0], S.bpm))

banner("memory under load")
# A single free-heap snapshot says very little: MicroPython's heap sawtooths
# between collections, so the number depends on when you looked. What matters
# is whether sustained play allocates faster than GC reclaims. So: run it, and
# watch the floor.
gc.collect()
lo = gc.mem_free()
oom = 0
S.playing = True
S.next_tick = time.ticks_ms()
t0 = time.ticks_ms()
spins = 0
while time.ticks_diff(time.ticks_ms(), t0) < 4000:
    try:
        app.loop()
    except MemoryError:
        oom += 1
    spins += 1
    if spins % 200 == 0:
        f = gc.mem_free()
        if f < lo:
            lo = f
        if spins % 1200 == 0:                 # views allocate differently
            S.view = (S.view + 1) % 4
            S.dirty_all = True
S.playing = False
S.view = C.V_ROLL
gc.collect()
mem_end = gc.mem_free()
print("  free before import  %d bytes" % mem_start)
print("  floor over %d frames of play: %d bytes" % (spins, lo))
print("  free after collect  %d bytes" % mem_end)
print("  MemoryError count   %d" % oom)
check(oom == 0, "no MemoryError during sustained playback")
# 25 KB, not a round guess: the measured floor with the 36 KB PCM kit loaded is
# ~36 KB over 20 s across all four views, so this trips well before real trouble.
check(mem_end > 25000, "at least 25 KB reclaimable headroom (%d)" % mem_end)

S.status = "ready"
S.dirty_all = True
app.loop()

banner("result")
if FAIL:
    print("FAILED %d check(s):" % len(FAIL))
    for f in FAIL:
        print("  - %s" % f)
else:
    print("PASS — %d warnings" % len(WARN))

raise SystemExit(1 if FAIL else 0)
