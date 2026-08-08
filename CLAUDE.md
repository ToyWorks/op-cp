# StackChan Dance — CoreS3 + StackChan base, UIFlow2

The Cardputer-ADV across the desk runs OP-CP and plays; this board listens
with its own microphone and dances. Sound is the whole protocol — no radio,
no pairing. The workflow, the Makefile and the sim are the ones from
[`../cardputer-adv-uiflow2`](../cardputer-adv-uiflow2/CLAUDE.md); read that
CLAUDE.md first. Only the facts specific to THIS hardware are here.

## The board pair

Two M5Stack boards share the USB hub, so `tools/find-port.sh` matches the
**CoreS3 product string**, not just the manufacturer. `make port` shows both.
The toolchain venv is shared: `../cardputer-adv-uiflow2/.venv`.

## StackChan base facts (all verified against uiflow-micropython 2.5.0 source)

- The frozen driver is `from hardware.stackchan import StackChan`;
  `StackChan(i2c=1, uart=1)` — I2C1 scl 11 / sda 12 (touch, RGB via M5ioe1
  expander at 0x6F, INA226 at 0x41, NFC), UART1 tx 6 / rx 7 at 1 Mbps for two
  SCS0009 bus servos: **id 1 = X (yaw), id 2 = Y (pitch)**.
- `set_servo_angle(id, deg, time_ms, speed)` — degrees around an NVS-stored
  zero. **X neutral 0°; Y rest pose 45°, official example sweeps 20..70.**
  The C++ build in `../stackchan-envpro` established pitch 5..85° as the
  hardware protection window and yaw ±60° as the product limit. This app
  clamps to yaw ±30, pitch 28..62 — inside everything.
- **Power-up without a lurch** (official example pattern, same lesson as the
  C++ build's "stop the head lurching" commit): power the servo rail OFF
  300 ms, ON (1 s settle inside the driver), torque both, then a slow 1 s
  glide to neutral. On wake-from-rest: command the pose you believe you hold
  before anything else.
- The RGB strips are 2×6 through the IO expander: drive per-LED with
  `chan.rgb.set_color(phys, color, refresh=False)` + one `refresh()`;
  strip 1's physical order is mirrored (phys `6 + (5 - i)`).
- Touch is 3 zones: `get_touch()` → list of 3. Unused so far.

## Mic facts

- CoreS3 mic is the ES7210 path: `M5.Mic` (registered in `M5`, **not**
  `hardware`). `Mic.record(buf, rate, stereo)` fills over DMA and returns;
  `Mic.isRecording()` goes False when full. Two buffers ping-pong in
  `scd_mic` for a gapless ~32 ms energy stream (256 samples @ 8 kHz).
- Mic and Speaker are mutually exclusive on this codec — the official mic
  example does `Speaker.end()` before `Mic.begin()`. This app never touches
  the speaker.
- Beat logic (`scd_beat`) is pure integers over frame energies and runs
  identically on host and device; selftest feeds it synthetic music and
  asserts on the beats. Tune `MIN_RMS` against the numbers selftest prints
  from the real room.

## The link

`scd_link.py` listens for OP-CP's ESP-NOW step broadcasts (channel 1; wire
format in both files' headers — change one, change both) and dances from
ground truth: BD = strong beat, SD/CP = mid, hats/melody only breathe the
level, drumless bars still nod on the downbeat. Packets younger than
LINK_FRESH_MS own the dance and the microphone path is skipped entirely;
silence on the radio hands it back to the mic. A pat on the head (base
touchpad, or a tap on the lower screen) toggles the ear; the corner word
reads LINK / DANCE (mic) / LISTEN / MIC ONLY.

## Firmware

UIFlow2 v2.5.0 for CoreS3, installed headless the same way as the Cardputer
(M5Burner catalog API → CDN full-flash image → esptool at 0x0; the memory
note `uiflow2-headless-flashing` has the endpoints). 16 MB image. After
flashing: set NVS `uiflow/boot_option = 0`, then `make metrics` before the
first `make shots`.

## The loop

```bash
make check      # compile + upload + selftest on the CoreS3
make shots      # render the face states to sim/shots/ and look
make run        # dance live; Ctrl-C stops and rests the servos
make deploy     # install as main.py, start on power-up
make probe      # the real API surface
```

`make check` moves the head a few gentle degrees and flashes the LEDs once —
hold the base or let it sit flat. It cannot judge the dance; for that, put a
pattern on the Cardputer, turn its volume up, and watch.
