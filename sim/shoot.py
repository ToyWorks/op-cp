"""Render app.py's real screens to PNGs so the UI can be looked at.

    make shots        # then open sim/shots/

This runs the program's own draw functions -- not a mock of them -- against a
Pillow-backed M5 stub with device-measured font metrics. Every screen state
worth reviewing gets one file, plus a contact sheet with all of them.

Usage: python3 sim/shoot.py [scale]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)
sys.path.insert(0, os.path.join(_root, "lib"))     # device has these flat on /flash

import m5stub                                        # noqa: E402

m5 = m5stub.install()

from PIL import Image                                # noqa: E402

import app                                           # noqa: E402
import opcp_conf as C                                # noqa: E402
import opcp_screen as SC                             # noqa: E402
import opcp_ui as U                                  # noqa: E402
from opcp_state import S                             # noqa: E402

SCALE = int(sys.argv[1]) if len(sys.argv) > 1 else 3
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots")
os.makedirs(OUT, exist_ok=True)

app.setup()

shots = []


def snap(name):
    img = m5.Lcd.img.copy()
    big = img.resize((img.width * SCALE, img.height * SCALE), Image.NEAREST)
    path = os.path.join(OUT, name + ".png")
    big.save(path)
    shots.append((name, img))
    print("  %-22s %dx%d -> %s" % (name, img.width, img.height, path))


def seed(track, pattern):
    """Deterministic content so shots are comparable between runs."""
    S.patterns[S.pat][track] = list(pattern)


N = None
seed(0, [0, N, 3, N, 5, N, 7, N, 0, N, 3, N, 7, N, 5, N])
seed(1, [0, N, N, N, 5, N, N, N, 3, N, N, N, 7, N, N, N])
seed(2, [7, N, N, 5, N, N, 3, N, 0, N, N, 5, N, N, 7, N])
seed(3, [0, 2, 1, 2, 0, 2, 1, 2, 0, 2, 1, 8, 0, 2, 1, 4])

print("rendering %dx%d at %dx" % (U.W, U.H, SCALE))

# --- the grid, per track --------------------------------------------------
S.view = C.V_ROLL
S.playing = False
for t in range(C.TRACKS):
    S.track = t
    S.cursor = 4
    SC.redraw_all()
    snap("roll-%d-%s" % (t, C.TRACK_NAMES[t].lower()))

# --- transport states -----------------------------------------------------
S.track = 0
S.playing = True
S.play_step = 6
S.flash[6] = C.FLASH_MAX
SC.redraw_all()
snap("roll-playing")

S.recording = True
S.status = "rec"
SC.redraw_all()
snap("roll-recording")
S.recording = False

S.muted[0] = True
SC.redraw_all()
snap("roll-muted")
S.muted[0] = False

# --- the cartoon views ----------------------------------------------------
for t, hits in ((0, [C.HIT_MAX, 0, 0, 0]), (3, [0, 0, 0, C.HIT_MAX])):
    S.track = t
    for name, v in (("face", C.V_FACE), ("ring", C.V_RING), ("bars", C.V_BARS)):
        S.view = v
        S.hit[:] = hits
        SC.redraw_all()
        snap("%s-%s-hit" % (name, C.TRACK_NAMES[t].lower()))

S.track = 0
S.hit[:] = [0, 0, 0, 0]
for name, v in (("face", C.V_FACE), ("ring", C.V_RING), ("bars", C.V_BARS)):
    S.view = v
    SC.redraw_all()
    snap("%s-idle" % name)

# --- files ----------------------------------------------------------------
S.view = C.V_FILES
S.slot_meta = [(112, 1), None, (98, 0), None, (140, 2), None, None, (76, 1)]
SC.redraw_all()
snap("files")

S.files_arm = True
S.set_status("SAVE 1-8?")
SC.redraw_all()
snap("files-armed")
S.files_arm = False

# --- help -----------------------------------------------------------------
S.view = C.V_HELP
SC.redraw_all()
snap("help")

# --- ghost check ----------------------------------------------------------
# The animated views erase only what they last painted, rather than clearing
# the whole band, so a wrong erase box leaves a trail that no single snapshot
# would show. Drive each view the way the music drives it, without clearing
# between frames, then compare against the same final state drawn onto a
# clean band: any difference IS a ghost.
GHOSTS = 0


def _ghost_check(view, name):
    global GHOSTS
    S.view = view
    seq = []
    SC.redraw_all()                       # a clean start, caches reset
    for i in range(40):
        S.track = i % C.TRACKS
        S.hit[:] = [max(0, C.HIT_MAX - ((i + t * 3) % 10)) for t in range(C.TRACKS)]
        S.play_step = i % C.STEPS
        S.blink = 2 if i % 11 == 0 else 0
        S.last_semi = (i * 5) % 16
        SC.draw_cartoon()                 # exactly what animate() calls
        seq.append((list(S.hit), S.track, S.play_step, S.blink, S.last_semi))
    band = (0, U.ROLL_Y, U.W, U.ROLL_Y + U.ROLL_H)
    dirty = m5.Lcd.img.crop(band)

    S.hit[:], S.track, S.play_step, S.blink, S.last_semi = seq[-1]
    SC.redraw_all()                       # same state, clean band
    clean = m5.Lcd.img.crop(band)

    # only the animation band: the header and the footer are repainted by the
    # app loop's own changed() checks, not by draw_cartoon, so including them
    # would compare this harness against itself
    dp, cp = dirty.load(), clean.load()
    bad = []
    for yy in range(dirty.height):
        for xx in range(dirty.width):
            if dp[xx, yy] != cp[xx, yy]:
                bad.append((xx, yy + U.ROLL_Y, dp[xx, yy]))
    n = len(bad)
    print("  ghost check %-6s %d pixels differ after 40 live frames" % (name, n))
    if n:
        GHOSTS += n
        print("      at %s%s" % (", ".join("(%d,%d)%s" % b for b in bad[:8]),
                                 " ..." if n > 8 else ""))
        from PIL import ImageChops
        ImageChops.difference(dirty, clean).resize(
            (dirty.width * SCALE, dirty.height * SCALE), Image.NEAREST).save(
                os.path.join(OUT, "_ghosts-%s.png" % name))
        print("      -> sim/shots/_ghosts-%s.png" % name)


print("")
S.playing = True
for _v, _n in ((C.V_FACE, "face"), (C.V_RING, "ring"), (C.V_BARS, "bars")):
    _ghost_check(_v, _n)
S.playing = False
S.hit[:] = [0, 0, 0, 0]
S.track = 0

# --- contact sheet --------------------------------------------------------
COLS = 4
cell_w, cell_h = U.W, U.H
rows = (len(shots) + COLS - 1) // COLS
pad, label_h = 6, 14
sheet = Image.new("RGB", (COLS * (cell_w + pad) + pad,
                          rows * (cell_h + pad + label_h) + pad), (24, 24, 24))
from PIL import ImageDraw                            # noqa: E402
sd = ImageDraw.Draw(sheet)
for i, (name, img) in enumerate(shots):
    c, r = i % COLS, i // COLS
    x = pad + c * (cell_w + pad)
    y = pad + r * (cell_h + pad + label_h)
    sheet.paste(img, (x, y))
    sd.text((x + 1, y + cell_h + 2), name, fill=(170, 170, 170))
s2 = sheet.resize((sheet.width * 2, sheet.height * 2), Image.NEAREST)
s2.save(os.path.join(OUT, "_contact.png"))
print("\n  contact sheet -> %s/_contact.png  (%d shots)" % (OUT, len(shots)))

# A ghost is a correctness bug, not a note: every view must erase exactly what
# it drew last time. Fail loudly rather than leaving it in a PNG.
if GHOSTS:
    raise SystemExit("FAILED: %d ghost pixels — see sim/shots/_ghosts-*.png"
                     % GHOSTS)
