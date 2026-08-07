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

    def feed(self, codes):
        self.queue = list(codes)

    def get_key(self):
        return self.queue.pop(0) if self.queue else -1


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
                 ("BPM", "OCT", "SCALE", "PATTERN", "VOL", "STEP 16", "NOTE"))
worst_right = 0
for sc, _ in C.SCALES:
    for oc in ("+2", "-2", "--"):
        worst_right = max(worst_right, U.M5.Lcd.textWidth("%s %s" % (sc, oc)))
worst_right = max(worst_right, U.M5.Lcd.textWidth("STRAIGHT"))
U.M5.Lcd.setFont(U.HERO)
hero_w = max(U.spaced_width(v, C.HERO_TRACK) for v in ("240", "MIN", "C#"))
total = 4 + hero_w + 6 + worst_hero + 8 + worst_right + 4
print("  footer worst case: hero %d + label %d + readout %d = %d of %d"
      % (hero_w, worst_hero, worst_right, total, U.W))
check(total <= U.W, "footer worst case fits on one line (%d <= %d)" % (total, U.W))

U.M5.Lcd.setFont(U.TINY)
head_w = 4 + max(U.M5.Lcd.textWidth(n) for n in C.TRACK_NAMES) + 8 + 4 * 8
worst_status = max(U.M5.Lcd.textWidth(x) for x in
                   ("STRAIGHT", "UNMUTE", "ARMED OFF", "P1") + C.VIEW_NAMES)
print("  header worst case: left %d + status %d + pip 12 = %d of %d"
      % (head_w, worst_status, head_w + worst_status + 12, U.W))
check(head_w + worst_status + 12 <= U.W, "header worst case fits")

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
            + " qri'./[]-=`90\\")
for t in range(C.TRACKS):
    S.track = t
    for ch in bindings:
        fake.feed([ord(ch)])
        __import__('opcp_keys').on_key(None)
        app.loop()
    fake.feed([13])              # ENTER: record arm
    __import__('opcp_keys').on_key(None)
    app.loop()
print("  drove %d keys x %d tracks, no exception"
      % (len(bindings) + 1, C.TRACKS))
check(True, "all key bindings dispatch cleanly")

S.kb, S.kb_tick = real_kb, real_tick
S.playing = False
S.recording = False
S.track = 0
S.view = C.V_ROLL

banner("persistence")
Q.save()
print("  save -> %s" % S.status)
check(S.status == "saved", "pattern saved to %s" % C.SAVE_PATH)
Q.load()
print("  load -> %s" % S.status)
check(S.status == "loaded", "pattern loaded back")

banner("memory")
gc.collect()
mem_end = gc.mem_free()
print("  free before import  %d bytes" % mem_start)
print("  free after  test    %d bytes" % mem_end)
print("  consumed            %d bytes" % (mem_start - mem_end))
check(mem_end > 40000, "at least 40 KB headroom left (%d)" % mem_end)

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
