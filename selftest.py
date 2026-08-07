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

app.VOLUME = 60          # audible enough to prove the speaker, quiet enough
                         # not to startle whoever is holding the thing
app.setup()
print("  screen        %dx%d" % (app.W, app.H))
check(app.W > 0 and app.H > 0, "display reports a size")
check(app.kb is not None, "MatrixKeyboard bound")

banner("fonts")
for label, font, height in (("HEAD", app.HEAD, app.HEAD_H),
                            ("CELL", app.CELL_F, app.CELL_H),
                            ("TINY", app.TINY, app.TINY_H)):
    print("  %-5s font=%s height=%d" % (label, font, height))
    check(font is not None, "%s font resolved" % label)
    check(height > 0, "%s font height > 0" % label)

banner("layout")
grid_r = app.GX + 8 * app.CW
grid_b = app.GY + 2 * (app.CH + app.GAP) - app.GAP
prog_b = app.PROG_Y + 2
param_b = app.PARAM_Y + app.PARAM_H
status_b = app.STATUS_Y + app.TINY_H
anim_top, anim_h = app.anim_zone()

print("  grid          x %d..%d  y %d..%d  cell %dx%d gap %d"
      % (app.GX, grid_r, app.GY, grid_b, app.CW, app.CH, app.GAP))
print("  progress      y %d..%d" % (app.PROG_Y, prog_b))
print("  params        y %d..%d  (h %d)" % (app.PARAM_Y, param_b, app.PARAM_H))
print("  status        y %d..%d" % (app.STATUS_Y, status_b))
print("  anim band     y %d..%d  (h %d)" % (anim_top, anim_top + anim_h, anim_h))

check(app.GX >= 0 and grid_r <= app.W, "grid within width")
check(app.GY >= 0 and grid_b <= app.H, "grid within height")
check(grid_b <= app.PROG_Y, "grid does not overlap progress bar")
check(prog_b <= app.PARAM_Y, "progress bar does not overlap params")
check(param_b <= app.STATUS_Y, "params do not overlap status row")
check(status_b <= app.H, "status row within height")
check(anim_h > 20, "animation band tall enough to draw into")

banner("text fits its box")
app.M5.Lcd.setFont(app.TINY)
seg = app.W // 4
box = seg - 3
for name in app.PARAMS:
    w = app.M5.Lcd.textWidth(name)
    check(w <= box - 6, "param label %-6s %3dpx <= %dpx" % (name, w, box - 6))

app.M5.Lcd.setFont(app.CELL_F)
for v in ("240", "MAJ", "CHR", "+2", "-2", "--", "OFF"):
    w = app.M5.Lcd.textWidth(v)
    check(w <= box - 6, "param value %-4s %3dpx <= %dpx" % (v, w, box - 6))

app.M5.Lcd.setFont(app.TINY)
cell_box = app.CW - app.GAP
for name, _ in app.DRUMS:
    w = app.M5.Lcd.textWidth(name)
    check(w <= cell_box, "drum label %-4s %3dpx <= %dpx" % (name, w, cell_box))
for name in app.NOTE_NAMES:
    w = app.M5.Lcd.textWidth(name)
    check(w <= cell_box, "note label %-3s %3dpx <= %dpx" % (name, w, cell_box))

app.M5.Lcd.setFont(app.TINY)
right = bottom = 0
for x, y, text, _ in app.help_layout():
    w = app.M5.Lcd.textWidth(text)
    if x + w > right:
        right = x + w
    if y + app.TINY_H > bottom:
        bottom = y + app.TINY_H
print("  help page occupies %dx%d of %dx%d" % (right, bottom, app.W, app.H))
check(right <= app.W - 2, "help page fits horizontally (%d <= %d)" % (right, app.W - 2))
check(bottom <= app.H, "help page fits vertically (%d <= %d)" % (bottom, app.H))

banner("every view renders")
for idx, name in enumerate(app.VIEW_NAMES):
    app.view = idx
    t0 = time.ticks_ms()
    app.redraw_all()
    print("  %-5s full redraw %4d ms" % (name, time.ticks_diff(time.ticks_ms(), t0)))
app.view = app.V_GRID

banner("transport: 2 bars of playback")
app.playing = True
app.play_step = app.STEPS - 1
app.next_tick = time.ticks_ms()
frames = 0
t0 = time.ticks_ms()
target = int(2 * app.STEPS * app.step_interval()) + 200
while time.ticks_diff(time.ticks_ms(), t0) < target:
    app.loop()
    frames += 1
elapsed = time.ticks_diff(time.ticks_ms(), t0)
print("  %d frames in %d ms  (%d fps)" % (frames, elapsed, frames * 1000 // elapsed))
check(frames > 100, "loop is actually iterating")
check(app.play_step != app.STEPS - 1, "playhead advanced")
app.playing = False

banner("key handling: every documented binding")
real_kb, real_tick = app.kb, app.kb_tick
fake = FakeKb()
app.kb, app.kb_tick = fake, None

bindings = (app.WHITE_KEYS + "".join(app.BLACK_KEYS.keys())
            + app.STEP_KEYS_A + app.STEP_KEYS_B
            + " qri'./[]-=`90\\")
for t in range(app.TRACKS):
    app.track = t
    for ch in bindings:
        fake.feed([ord(ch)])
        app.on_key(None)
        app.loop()
    fake.feed([13])              # ENTER: record arm
    app.on_key(None)
    app.loop()
print("  drove %d keys x %d tracks, no exception"
      % (len(bindings) + 1, app.TRACKS))
check(True, "all key bindings dispatch cleanly")

app.kb, app.kb_tick = real_kb, real_tick
app.playing = False
app.recording = False
app.track = 0
app.view = app.V_GRID

banner("persistence")
app.save()
print("  save -> %s" % app.status)
check(app.status == "saved", "pattern saved to %s" % app.SAVE_PATH)
app.load()
print("  load -> %s" % app.status)
check(app.status == "loaded", "pattern loaded back")

banner("memory")
gc.collect()
mem_end = gc.mem_free()
print("  free before import  %d bytes" % mem_start)
print("  free after  test    %d bytes" % mem_end)
print("  consumed            %d bytes" % (mem_start - mem_end))
check(mem_end > 40000, "at least 40 KB headroom left (%d)" % mem_end)

app.status = "ready"
app.dirty_all = True
app.loop()

banner("result")
if FAIL:
    print("FAILED %d check(s):" % len(FAIL))
    for f in FAIL:
        print("  - %s" % f)
else:
    print("PASS — %d warnings" % len(WARN))

raise SystemExit(1 if FAIL else 0)
