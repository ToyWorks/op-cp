# SCD — StackChan Dance. Everything that never changes at runtime.
#
# Constants only: no state, no imports from the rest of the program, same
# contract as opcp_conf in the Cardputer project this dances with.

# ------------------------------------------------------------------ palette
# Greys are multiples of 0x10 (RGB565: green keeps 6 bits, red/blue 5 — an
# arbitrary grey picks up a green cast; same lesson as the Cardputer panel).
# ONE saturated colour, and it always means "the music": beat, level, LEDs.
BG = 0x000000
FG = 0xF0F0F0            # the face itself — classic white-on-black stackchan
INK = 0x000000
DIM = 0x707070
FAINT = 0x303030
LED_OFF = 0x000000
LED_BEAT = 0xF0F0F0      # beat flash on the strips, one frame of white

# The accent is the music, and it is the ONE saturated colour on screen —
# that rule is what makes a flash legible at a glance, so cycling the accent
# must never turn into a second colour appearing. Each entry is therefore an
# (name, lit, unlit) triple: one hue, two brightnesses. The cube's top button
# steps through them; index 0 is the cyan the CoreS3 was designed around.
PALETTE = (
    ("CYAN",   0x20C8F8, 0x082830),
    ("AMBER",  0xF8A020, 0x302008),
    ("LIME",   0x60E020, 0x142808),
    ("MAGENTA", 0xF040C0, 0x300828),
    ("VIOLET", 0x8060F8, 0x181030),
    ("RED",    0xF83820, 0x300808),
)
ACCENT = PALETTE[0][1]       # the sim and selftest's fallback; the running
ACCENT_DEEP = PALETTE[0][2]  # program reads S.accent, which the button moves
PALETTE_NAME_MS = 1200       # how long the colour's name sits in the corner

# ------------------------------------------------------------------ mic / beat
RATE = 8000              # mic sample rate; FRAME/RATE = one 32 ms energy frame
FRAME = 256              # samples per capture
RMS_STRIDE = 4           # every 4th sample is plenty for an energy envelope
MIN_RMS = 90             # the default noise gate. Each board overrides it
                         # into S.min_rms at begin(), because the number is a
                         # property of that microphone, not of the music.
REFRACT_MS = 130         # two beats can't be closer than this (≈460 bpm)
IBI_MIN = 240            # inter-beat intervals outside this window are noise,
IBI_MAX = 1500           # not tempo (40..250 bpm)
IBI_KEEP = 6
# The tempo readout folds every interval into one octave, 80..160 bpm, so a
# missed beat (a 2x gap) or a double-triggered one (a /2 gap) still votes for
# the same tempo instead of dragging the median to half or double time.
FOLD_MIN_MS = 375        # 160 bpm
FOLD_MAX_MS = 750        # 80 bpm
SILENCE_MS = 2600        # no beat for this long -> back to idle
LEVEL_MAX = 255
SERVO_MASK_MS = 150      # extra deafness after a servo move ends — the whine
                         # measured louder than the room (rms ~683 vs 34)

# ------------------------------------------------------------------ servos
# All choreography is RELATIVE to the pose read at power-on, never absolute.
# Measured on this unit: the Y servo rests at 150.9 deg in the driver's
# convention where the official rest pose is 45 — this base was assembled
# and zeroed under the old C++ firmware, and the UIFlow2 NVS zero does not
# describe it. Commanding the conventional 45 does nothing: the servo's own
# EEPROM limits reject the excursion (a useful hardware backstop, but not
# one to lean on). So: boot, read where the head actually is, call that
# neutral, and dance in a small window around it. Amplitudes stay inside
# what the C++ build (pitch window 5..85, yaw +-60) proved safe.
# Measured on this unit (2026-08-08): from rest, pitch -8 is REJECTED by the
# servo's EEPROM limit (the head rests at the bottom of its window) while
# +10 and +16 track fine. So the head can only look UP from rest, and the
# dance is built that way round: ride a few degrees above neutral, DROP to
# neutral on the beat, bounce back up on the offbeat.
YAW_LIMIT = 30           # max relative yaw, deg — the front arc
YAW_BASE = 8             # smallest sway amplitude, deg
PITCH_NEUTRAL = 45       # fallback only, when the boot read fails
PITCH_UP = 12            # max relative pitch above neutral, deg (16 tracked)
PITCH_DOWN = 0           # the rest pose IS the bottom of this unit's window
SERVO_EVERY = 4          # head moves on every Nth beat only. The SCS0009
                         # whine reads on the mic at ~20x the room floor, so
                         # the SCREEN dances every beat and the head marks
                         # the bars — quieter, and honest to the detector.
SERVO_TICK_MS = 66       # min gap between position writes — don't spam the bus
SERVO_REST_MS = 120000   # torque off after this much continuous silence
MOVE_MIN_MS = 90         # fastest commanded move
MOVE_MAX_MS = 420

# ------------------------------------------------------------------ idle life
BREATH_MS = 4200         # idle breathing period (pitch +-1.5 deg)
GLANCE_MIN_MS = 6000     # idle glances, uniformly random in this window
GLANCE_MAX_MS = 14000
BLINK_GAP_MIN = 1800
BLINK_GAP_MAX = 4600
BLINK_MS = 110

# ------------------------------------------------------------------ face
ANIM_MS = 33             # face frame budget (~30 fps)
HIT_MAX = 6              # beat pop decay steps, same feel as OP-CP's flashes
LED_TICK_MS = 66

# ------------------------------------------------------------------ link
# ESP-NOW from the Cardputer: OP-CP broadcasts each step it plays, so no
# audio analysis is needed while packets flow. Both sides pin channel 1.
LINK_CHANNEL = 1
LINK_FRESH_MS = 1500     # packets younger than this own the dance
TOUCH_POLL_MS = 150      # base touchpad is an I2C read — don't hammer it
TOUCH_DEBOUNCE_MS = 700  # one head-pat, one toggle
