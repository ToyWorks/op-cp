# Headless self-test for the dance app — what `make check` runs on the board.
#
# Same philosophy as the Cardputer's: bounded, prints what a human would
# otherwise read off the screen, proves geometry and dispatch, and moves any
# servos only a few gentle degrees. Whether the dance is GOOD stays a human
# question — put music on and watch.
#
# One file, both machines. It asks scd_board what this one has rather than
# testing for a board id, so the CoreS3 runs the servo section and the cube
# runs the button section, and neither has to know the other exists.

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


def banner(s):
    print("\n== %s" % s)


gc.collect()
mem_start = gc.mem_free()

banner("import + setup")
import app
import scd_board as BOARD
import scd_conf as C
import scd_face as F
from scd_beat import Beat
from scd_state import S

app.setup()
print("  board         %s (body: %s)" % (BOARD.NAME, BOARD.HAS_BODY))
print("  screen        %dx%d" % (F.W, F.H))
print("  noise gate    %d" % S.min_rms)
check(F.W > 0 and F.H > 0, "display reports a size")
check(S.min_rms == BOARD.MIN_RMS, "the board's own noise gate reached scd_beat")

banner("face geometry stays on the panel")
G = F.G
scale_max = 96 + (255 >> 5) * 2 + C.HIT_MAX * 2
dx_max = 14
half_w_max = (G["mouth_base"] + (255 >> G["m_lvl"])
              + C.HIT_MAX * G["m_hitw"]) * scale_max // 100
half_h_max = 3 + (255 * G["m_hnum"] >> 8) + C.HIT_MAX * G["m_hith"]
mouth_r = F.FACE_CX + dx_max + half_w_max + half_h_max
mouth_l = F.FACE_CX - dx_max - half_w_max - half_h_max
eye_r_max = F.EYE_R * scale_max // 100
eye_ext = F.FACE_CX + dx_max + F.EYE_DX * scale_max // 100 + eye_r_max
mouth_bot = F.EYE_Y + F.MOUTH_DY * scale_max // 100 + 12 + half_h_max
print("  face box      x %d..%d  y %d..%d"
      % (F.FACE_CX - F.FACE_HALF_W, F.FACE_CX + F.FACE_HALF_W,
         F.FACE_TOP, F.FACE_BOT))
print("  worst extents mouth %d..%d, eyes ..%d, bottom %d"
      % (mouth_l, mouth_r, eye_ext, mouth_bot))
check(F.FACE_CX - F.FACE_HALF_W >= 0, "face box inside width")
check(F.FACE_CX + F.FACE_HALF_W <= F.W, "face box inside the right edge")
check(mouth_r <= F.FACE_CX + F.FACE_HALF_W, "widest mouth stays in the box")
check(mouth_l >= F.FACE_CX - F.FACE_HALF_W, "leftmost mouth stays in the box")
check(eye_ext <= F.FACE_CX + F.FACE_HALF_W, "widest eyes stay in the box")
check(F.EYE_Y - eye_r_max >= F.FACE_TOP, "eyes clear the box top")
check(mouth_bot <= F.FACE_BOT, "mouth clears the box bottom (%d <= %d)"
      % (mouth_bot, F.FACE_BOT))
check(F.PAD_X + F.PAD_W <= F.W, "pad inside width")

if G["clap"]:
    reach = C.HIT_MAX * G["clap_travel"] // C.HIT_MAX
    lx = G["clap_rest"] + reach
    rx = F.W - G["clap_rest"] - G["clap_w"] - reach
    print("  clap          rest gap %d, struck gap %d"
          % (F.W - 2 * G["clap_rest"] - 2 * G["clap_w"],
             rx - (lx + G["clap_w"])))
    check(mouth_bot < G["clap_y"], "the mouth never reaches the hands (%d < %d)"
          % (mouth_bot, G["clap_y"]))
    check(rx - (lx + G["clap_w"]) < 8, "the hands actually meet on a full hit")
    check(G["clap_y"] + F.CLAP_H <= F.PAD_Y, "hands clear the bar")
    check(F._clap_l is not None and F._clap_r is not None,
          "both clap sprites loaded")
else:
    check(mouth_r < F.HAND_X, "the face never smears into the hand column")
    check(F.HAND_X + 3 + 100 <= F.W, "hand sprite inside width")
    check(F._hand_up is not None and F._hand_tap is not None,
          "both hand sprites loaded")

banner("beat detector on synthetic music")
bt = Beat()
now = 0
# 2 s of near-silence, then 8 loud hits at 500 ms (= 120 bpm), quiet between
for i in range(60):
    now += 33
    bt.feed(25, now)
hits = 0
for n in range(8 * 15):
    now += 33
    rms = 900 if n % 15 == 0 else 60
    if bt.feed(rms, now):
        hits += 1
print("  beats found   %d of 8, bpm %d" % (hits, S.bpm))
check(hits == 8, "every synthetic hit detected, nothing between (%d)" % hits)
check(115 <= S.bpm <= 125, "tempo lands on 120 bpm (%d)" % S.bpm)
check(bt.quiet(now + C.SILENCE_MS + 1), "silence detector arms after the music")
check(not bt.quiet(now + 100), "and not while it is still playing")

# octave folding: 128 bpm with every third beat missed must still read 128
bt2 = Beat()
now2 = 0
for i in range(60):
    now2 += 33
    bt2.feed(25, now2)
n_hit = 0
for n in range(16):
    step = 938 if n % 3 == 2 else 469         # a miss = a doubled gap
    now2 += step - 33                         # the quiet frame below adds 33
    if bt2.feed(900, now2):
        n_hit += 1
    now2 += 33
    bt2.feed(60, now2)
print("  folded bpm    %d from %d hits with misses" % (S.bpm, n_hit))
check(124 <= S.bpm <= 132, "missed beats fold to the same tempo (%d)" % S.bpm)

# the gate is the board's, so a frame under ITS floor must not be a beat
bt4 = Beat()
now4 = 0
for i in range(40):
    now4 += 33
    bt4.feed(4, now4)
check(bt4.feed(S.min_rms - 1, now4 + 400) == 0,
      "a frame under this board's gate is not a beat")
check(bt4.feed(S.min_rms * 8, now4 + 900) > 0, "a loud one is")

# the servo mask: a loud frame while our own servos whine is not a beat
bt3 = Beat()
now3 = 0
for i in range(40):
    now3 += 33
    bt3.feed(25, now3)
S.servo_mask_until = now3 + 500
masked = bt3.feed(900, now3 + 100)
S.servo_mask_until = 0
open_beat = bt3.feed(900, now3 + 700)
check(masked == 0, "onset suppressed while servos whine")
check(open_beat > 0, "and detected again once the mask lifts")

banner("esp-now link")
import scd_link as L
print("  radio         %s" % ("up" if L.ok else "DOWN"))
check(L.ok, "espnow initialised on channel %d" % C.LINK_CHANNEL)
check(L.poll(time.ticks_ms()) == 0, "no packets pending reads as no beat")


def _step_pkt(step, hits, drum, bpm):
    return bytes((0x6F, 0x63, 1, 1, step, hits, drum, bpm & 0xFF, bpm >> 8))


S.level = 0
check(L.parse(_step_pkt(0, 0x08, 0, 128), 1000) == 3, "BD packet is a strong beat")
check(S.bpm == 128 and S.ibi == 468, "packet bpm lands (%d, ibi %d)"
      % (S.bpm, S.ibi))
check(L.parse(_step_pkt(4, 0x08, 1, 128), 2000) == 2, "SD packet is a mid beat")
check(L.parse(_step_pkt(2, 0x08, 2, 128), 3000) == 0, "a hat only breathes")
lvl_before = S.level
check(lvl_before > 0, "hits pump the level (%d)" % lvl_before)
check(L.parse(_step_pkt(8, 0x03, 255, 128), 4000) == 2,
      "drumless melody still marks the bar")
check(L.parse(_step_pkt(3, 0x03, 255, 128), 5000) == 0,
      "melody off the bar does not")
check(L.parse(b'garbage!!', 6000) == 0, "junk packets are ignored")
check(L.parse(bytes((0x6F, 0x63, 1, 2, 0, 128, 0)), 7000) == 0,
      "transport stop parses")
check(S.link_stop, "and raises the stop flag")
S.link_stop = False
S.level = 0

banner("microphone")
vals = []
t0 = time.ticks_ms()
while len(vals) < 20 and time.ticks_diff(time.ticks_ms(), t0) < 3000:
    r = BOARD.mic_poll()
    if r is not None:
        vals.append(r)
    time.sleep_ms(2)
if vals:
    print("  %d frames in %d ms  rms min/med/max %d/%d/%d"
          % (len(vals), time.ticks_diff(time.ticks_ms(), t0),
             min(vals), sorted(vals)[len(vals) // 2], max(vals)))
check(len(vals) >= 20, "mic streams energy frames (%d in 3 s)" % len(vals))
check(bool(vals) and max(vals) > 0,
      "mic hears something (a silent room still has a floor)")
warn(bool(vals) and sorted(vals)[len(vals) // 2] < S.min_rms,
     "the quiet room already reads above the gate — retune MIN_RMS")

banner("palette")
start = S.palette
app._palette(1, time.ticks_ms())
check(S.palette == (start + 1) % len(C.PALETTE), "a step moves the palette")
check(S.accent == C.PALETTE[S.palette][1], "and the live accent with it")
for i in range(len(C.PALETTE)):
    app._palette(1, time.ticks_ms())
check(S.palette == (start + 1) % len(C.PALETTE), "a full lap comes home")
app._palette(-1, time.ticks_ms())
check(S.palette == start, "and it steps back")

if BOARD.HAS_BODY:
    import scd_motion as MO

    banner("stackchan base")
    if MO.chan() is not None:
        print("  servo power   %s, torque %s" % (S.servo_ok, S.servo_awake))
        check(S.servo_ok, "servo rail up and torque acknowledged")
        print("  boot neutral  x=%.1f y=%.1f  (this unit's own convention)"
              % (S.yaw_neutral, S.pitch_neutral))
        ay = MO.chan().get_servo_angle(2)
        check(ay is not None, "y servo answers position reads")
        # a real nudge: +10 deg relative yaw, judged by how far the head moved
        ax0 = MO.chan().get_servo_angle(1)
        S.next_servo = 0
        MO.move(10, 0, 300, time.ticks_ms())
        time.sleep_ms(800)
        ax1 = MO.chan().get_servo_angle(1)
        print("  yaw nudge     %.1f -> %s (asked %.1f)"
              % (ax0, ax1, S.yaw_neutral + 10))
        check(ax1 is not None and ax1 - ax0 > 4,
              "head follows a +10 deg relative nudge (moved %.1f)"
              % ((ax1 - ax0) if ax1 is not None else -1))
        S.next_servo = 0
        MO.move(0, 0, 400, time.ticks_ms())
        time.sleep_ms(600)
        # pitch: this unit can only rise from rest — verify the rise tracks
        ay0 = MO.chan().get_servo_angle(2)
        S.next_servo = 0
        MO.move(0, 6, 300, time.ticks_ms())
        time.sleep_ms(800)
        ay1 = MO.chan().get_servo_angle(2)
        print("  pitch rise    %.1f -> %s (asked +6)" % (ay0, ay1))
        check(ay1 is not None and ay1 - ay0 > 2.5,
              "head rises +6 deg relative (moved %.1f)"
              % ((ay1 - ay0) if ay1 is not None else -1))
        S.next_servo = 0
        MO.move(0, 0, 400, time.ticks_ms())
        time.sleep_ms(600)
        # LED sweep: all accent, then off
        MO.chan().set_rgb_color(S.accent)
        time.sleep_ms(150)
        MO.chan().set_rgb_color(C.LED_OFF)
        check(True, "led strips accept a fill")
    else:
        warn(False, "no StackChan base found — face-only mode")

    banner("clamps hold at the extremes")
    S.next_servo = 0
    MO.move(999, 999, 100, time.ticks_ms())
    check(S.yaw == S.yaw_neutral + C.YAW_LIMIT
          and S.pitch == S.pitch_neutral + C.PITCH_UP,
          "over-limit request clamps to +(%d, %d)" % (C.YAW_LIMIT, C.PITCH_UP))
    S.next_servo = 0
    MO.move(-999, -999, 100, time.ticks_ms())
    check(S.yaw == S.yaw_neutral - C.YAW_LIMIT
          and S.pitch == S.pitch_neutral - C.PITCH_DOWN,
          "under-limit request clamps to -(%d, %d)"
          % (C.YAW_LIMIT, C.PITCH_DOWN))
    S.next_servo = 0
    MO.move(0, 0, 500, time.ticks_ms())
    time.sleep_ms(600)
else:
    banner("buttons")
    t, step = BOARD.poll_input(time.ticks_ms())
    print("  idle read     toggle=%s step=%d" % (t, step))
    check(not t and step == 0, "nothing is reported while nothing is pressed")
    check(BOARD._pins is not None, "the three side buttons claimed their pins")
    check(all(p.value() == 1 for p in BOARD._pins),
          "and all read high at rest (active-low with pull-ups)")

banner("every face state renders")
for name, groove, lvl, hit in (("idle", False, 0, 0),
                               ("groove-low", True, 60, 0),
                               ("groove-high", True, 230, 0),
                               ("beat-pop", True, 230, C.HIT_MAX),
                               ("blink", False, 0, 0)):
    S.grooving = groove
    S.level = lvl
    S.hit = hit
    S.blink = time.ticks_ms() + 50 if name == "blink" else 0
    F._last.clear()
    t0 = time.ticks_ms()
    F.draw(time.ticks_ms())
    print("  %-11s %3d ms" % (name, time.ticks_diff(time.ticks_ms(), t0)))
S.grooving = False
S.hit = 0
S.level = 0

banner("2 s of the real loop")
S.last_beat = time.ticks_ms()   # steady state, not the go-to-rest transition
frames = 0
t0 = time.ticks_ms()
while time.ticks_diff(time.ticks_ms(), t0) < 2000:
    app.loop()
    frames += 1
print("  %d frames (%d fps)" % (frames, frames * 1000 // 2000))
check(frames > 100, "loop is actually iterating")

banner("memory")
gc.collect()
mem_end = gc.mem_free()
print("  free before import  %d" % mem_start)
print("  free after collect  %d" % mem_end)
check(mem_end > 25000, "at least 25 KB reclaimable headroom (%d)" % mem_end)

BOARD.rest()

banner("result")
if FAIL:
    print("FAILED %d check(s):" % len(FAIL))
    for f in FAIL:
        print("  - %s" % f)
else:
    print("PASS — %d warnings" % len(WARN))

raise SystemExit(1 if FAIL else 0)
