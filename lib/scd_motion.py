# SCD — the body: two servos and twelve LEDs, driven by beats.
#
# All motion goes through move(), which clamps into the safe window as the
# last step — the same "limits are applied once, at the exit" rule the C++
# StackChan build settled on. The window is RELATIVE: neutral is wherever
# the head was resting at power-on (see scd_conf for why this unit cannot
# trust the driver's absolute angle convention), and the dance stays within
# a few degrees of it.
#
# The base is optional hardware: with no StackChan base attached (or servo
# power browned out) every call degrades to a no-op and the face dances on.

import scd_conf as C
from scd_state import S

_chan = None


def begin():
    """Bring the base up without moving it: power-cycle the rail (the
    official recovery pattern), torque on, read where the head actually
    is, call that neutral, and command the very pose we just read — so
    nothing lurches, whatever zero this unit was assembled with."""
    global _chan
    try:
        from hardware.stackchan import StackChan
        _chan = StackChan(i2c=1, uart=1)
        _chan.set_servo_power(False, settle_ms=300)
        _chan.set_servo_power(True)
        ok_x = _chan.set_servo_torque(1, True)
        ok_y = _chan.set_servo_torque(2, True)

        x = _chan.get_servo_angle(1)
        y = _chan.get_servo_angle(2)
        S.yaw_neutral = float(x) if x is not None else 0.0
        S.pitch_neutral = float(y) if y is not None else float(C.PITCH_NEUTRAL)
        S.yaw, S.pitch = S.yaw_neutral, S.pitch_neutral
        _chan.set_servo_angle(1, int(S.yaw_neutral), 400, 0)
        _chan.set_servo_angle(2, int(S.pitch_neutral), 400, 0)

        _chan.set_rgb_color(C.LED_OFF)
        S.servo_ok = bool(ok_x and ok_y)
        S.servo_awake = S.servo_ok
    except Exception:
        _chan = None
        S.servo_ok = False
        S.servo_awake = False


def chan():
    return _chan


def wake():
    """Torque back on after a rest, without a jump: command the held pose."""
    if _chan is None or S.servo_awake or not S.servo_ok:
        return
    try:
        _chan.set_servo_power(True)
        _chan.set_servo_torque(1, True)
        _chan.set_servo_torque(2, True)
        _chan.set_servo_angle(1, int(S.yaw), 400, 0)
        _chan.set_servo_angle(2, int(S.pitch), 400, 0)
        S.servo_awake = True
    except Exception:
        pass


def rest():
    """Silence for a long time: settle at neutral and cut torque."""
    if _chan is None or not S.servo_awake:
        return
    try:
        _chan.set_servo_angle(1, int(S.yaw_neutral), 800, 0)
        _chan.set_servo_angle(2, int(S.pitch_neutral), 800, 0)
        import time
        time.sleep_ms(900)
        _chan.set_servo_torque(1, False)
        _chan.set_servo_torque(2, False)
        _chan.set_servo_power(False)
        S.yaw, S.pitch = S.yaw_neutral, S.pitch_neutral
        S.servo_awake = False
    except Exception:
        pass


def move(dyaw, dpitch, t_ms, now):
    """Clamp the RELATIVE offsets, rate-limit, command. The only writer."""
    if dyaw < -C.YAW_LIMIT:
        dyaw = -C.YAW_LIMIT
    elif dyaw > C.YAW_LIMIT:
        dyaw = C.YAW_LIMIT
    if dpitch < -C.PITCH_DOWN:
        dpitch = -C.PITCH_DOWN
    elif dpitch > C.PITCH_UP:
        dpitch = C.PITCH_UP

    S.yaw = S.yaw_neutral + dyaw
    S.pitch = S.pitch_neutral + dpitch
    S.gaze = int(dyaw * 10 // C.YAW_LIMIT)     # pupils lead the head

    if _chan is None or not S.servo_awake:
        return
    if now < S.next_servo:
        return
    S.next_servo = now + C.SERVO_TICK_MS
    if t_ms < C.MOVE_MIN_MS:
        t_ms = C.MOVE_MIN_MS
    elif t_ms > C.MOVE_MAX_MS:
        t_ms = C.MOVE_MAX_MS
    # the whine window: the beat detector goes deaf until the move lands
    S.servo_mask_until = now + t_ms + C.SERVO_MASK_MS
    try:
        ok1 = _chan.set_servo_angle(1, int(S.yaw), t_ms, 0)
        ok2 = _chan.set_servo_angle(2, int(S.pitch), t_ms, 0)
    except Exception:
        ok1 = ok2 = False
    if ok1 and ok2:
        S.servo_fail = 0
    else:
        # each failed write burns 250 ms in the driver's retry loop; after
        # three strikes the head is surrendered so the face never stalls
        S.servo_fail += 1
        if S.servo_fail >= 3:
            S.servo_ok = False
            S.servo_awake = False


def on_beat(now, intensity):
    """One beat: the FACE does the dancing (see scd_face); the head only
    marks the bars. Every SERVO_EVERY-th beat it sways once — quietly,
    because the servo whine reads on the microphone at ~20x the room floor
    and was corrupting the very beat we dance to. Between its turns it
    glides home, one write, also masked."""
    wake()
    S.hit = C.HIT_MAX
    S.hit_intensity = intensity
    S.led_flash = 2

    if S.rand() % 8 != 0:              # 1-in-8: hit the same side again
        S.side = -S.side

    if not S.servo_awake:
        return
    if S.beat_n % C.SERVO_EVERY == 0:
        amp = C.YAW_BASE + intensity * 3
        rise = C.PITCH_UP if S.beat_n % 16 == 0 else 2 + intensity
        S.next_servo = 0               # the bar outranks the rate limiter
        move(S.side * amp, rise, 220, now)
    elif abs(S.yaw - S.yaw_neutral) > 2 and S.beat_n % C.SERVO_EVERY == 2:
        S.next_servo = 0
        move(0, 0, 360, now)           # settle home on the offbar


def tick(now):
    """In silence: breathe and glance."""

    if not S.grooving and S.servo_awake:
        ph = (now - S.breath0) % C.BREATH_MS
        breath = 2.0 if ph > C.BREATH_MS // 2 else 0.0
        if now > S.next_glance:
            S.next_glance = now + C.GLANCE_MIN_MS + S.rand() % (
                C.GLANCE_MAX_MS - C.GLANCE_MIN_MS)
            g = S.rand() % (2 * C.YAW_LIMIT) - C.YAW_LIMIT
            move(g * 0.6, breath, 800, now)
        elif abs((S.pitch - S.pitch_neutral) - breath) > 0.5:
            # only when the breath phase actually flips — re-commanding the
            # same pose 15x a second hammers the bus for nothing, and every
            # servo retry it provokes is 50 ms the face loop doesn't have
            move(S.yaw - S.yaw_neutral, breath, 600, now)


def leds(now):
    """Two 6-LED VU strips; a beat overpaints them white for two frames."""
    if _chan is None or now < S.next_led:
        return
    S.next_led = now + C.LED_TICK_MS

    if S.led_flash:
        S.led_flash -= 1
        lit, color = 6, C.LED_BEAT
    else:
        lit, color = S.level * 7 // (C.LEVEL_MAX + 1), C.ACCENT
    key = lit if color == C.ACCENT else 100 + lit
    if key == S.led_lit:
        return
    S.led_lit = key
    try:
        rgb = _chan.rgb
        for i in range(6):
            c = color if i < lit else C.LED_OFF
            rgb.set_color(i, c, refresh=False)          # strip 0
            rgb.set_color(6 + (5 - i), c, refresh=False)  # strip 1, mirrored
        rgb.refresh()
    except Exception:
        pass
