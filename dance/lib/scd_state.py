# SCD — all mutable state, in one object, so modules share it without
# threading arguments through every call (the opcp_state pattern).

import scd_conf as C


class Dance:
    def __init__(self):
        self.mode_word = "LISTEN"  # what the corner of the screen says

        # palette ------------------------------------------------------
        # The accent is the music; the cube's top button walks this index.
        # Everything that draws in the accent reads S.accent, never C.ACCENT,
        # so one assignment repaints the whole program's idea of "the music".
        self.palette = 0
        self.accent = C.PALETTE[0][1]
        self.accent_deep = C.PALETTE[0][2]
        self.palette_name = C.PALETTE[0][0]
        self.palette_shown = 0     # ms deadline for the colour's name

        # music ---------------------------------------------------------
        # the noise gate lives here, not in scd_conf, so scd_beat stays pure
        # integer logic with no hardware import; each board sets it at boot
        self.min_rms = C.MIN_RMS
        self.level = 0            # 0..LEVEL_MAX, smoothed loudness vs floor
        self.beat_n = 0           # beats seen since boot
        self.bpm = 0              # 0 = no stable tempo yet
        self.ibi = 500            # last credible inter-beat interval, ms
        self.hit = 0              # beat pop, HIT_MAX -> 0
        self.hit_intensity = 1
        self.last_beat = 0
        self.grooving = False     # False = idle: no music heard lately

        # head ----------------------------------------------------------
        self.yaw_neutral = 0.0    # the pose the head held at power-on;
        self.pitch_neutral = float(C.PITCH_NEUTRAL)  # every move is relative
        self.yaw = 0.0            # last commanded angles, deg
        self.pitch = float(C.PITCH_NEUTRAL)
        self.next_servo = 0       # rate limiter deadline
        self.servo_ok = False     # StackChan base answered at boot
        self.servo_awake = False  # torque currently on
        self.side = 1             # which way the next bob goes
        self.servo_fail = 0       # consecutive write failures; 3 = give up
        self.servo_mask_until = 0  # deaf-to-onsets window while servos whine

        # the virtual dance: what the face does INSTEAD of the head
        self.dx = 0               # face translate, eased toward side * swing
        self.dy = 0               # face drop on the hit, springs back up

        # face ----------------------------------------------------------
        self.gaze = 0             # -10..10 px, pupils lead the head
        self.blink = 0            # >0 = lids closed for that many more ms
        self.next_blink = 0
        self.next_anim = 0
        self.breath0 = 0          # phase origin for idle breathing

        # idle life -----------------------------------------------------
        self.next_glance = 0
        self.rng = 0x5EED

        # link ----------------------------------------------------------
        self.link_enabled = True  # head-pat toggles; mic remains the fallback
        self.link_last = -99999   # when the last OP-CP packet landed
        self.link_stop = False    # a transport-stop packet arrived
        self.next_touch = 0
        self.touch_prev = False
        self.touch_hold = 0       # debounce deadline
        self.next_btn = 0         # cube button poll deadline
        self.screen_down = 0      # when the screen contact started, 0 = up
        self.strip_down = 0       # ...and the base strip's
        self.strip_fired = False  # its hold already fired; ignore the release

        # A held strip means "be still": the body stops marking the beat and
        # settles, while the face keeps dancing. It is the servos that are
        # loud and distracting, not the screen.
        self.still = False

        # plumbing ------------------------------------------------------
        self.next_led = 0
        self.led_lit = -1         # last pushed VU count, -1 forces first push
        self.led_flash = 0

    def rand(self):
        """Deterministic LCG — same idea as the C++ build's motion_rand."""
        self.rng = (self.rng * 1103515245 + 12345) & 0x7FFFFFFF
        return self.rng >> 16


S = Dance()
