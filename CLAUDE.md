# StackChan Dance — one program, two dancers, UIFlow2

The Cardputer-ADV across the desk runs OP-CP and plays; a board over here
listens with its own microphone and dances. Sound is the whole protocol — no
radio, no pairing. The workflow, the Makefile and the sim are the ones from
[`../cardputer-adv-uiflow2`](../cardputer-adv-uiflow2/CLAUDE.md); read that
CLAUDE.md first. Only the facts specific to THIS hardware are here.

## Two boards, one program, split at deploy time

`app.py` and `lib/` are shared and identical on both machines. Everything
that differs is in `boards/<board>/scd_board.py`, and `make BOARD=...` copies
exactly one of them to the device **under the same name**. So no file in this
project ever asks which board it is running on — the answer was decided by
the Makefile before anything was uploaded.

```bash
make boards               # what is attached, and the BOARD= name for each
make check                # BOARD=cores3 is the default
make check BOARD=cube
make compile-all          # syntax-check BOTH halves, no board needed
```

`scd_board` answers for: the screen (`lcd`, `W`, `H`), the microphone
(`mic_poll()` → one integer energy frame or None), the controls
(`poll_input()` → `(toggle_link, palette_step)`), the noise gate (`MIN_RMS`,
which it publishes into `S.min_rms` so `scd_beat` stays pure integer logic
with no hardware import), and the body (`on_beat` / `tick` / `rest` /
`resting_due`, which on the cube do nothing at all).

## BOARD=cores3 — CoreS3 on a StackChan base

- Frozen driver `from hardware.stackchan import StackChan`;
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
- RGB strips are 2×6 through the IO expander: drive per-LED with
  `chan.rgb.set_color(phys, color, refresh=False)` + one `refresh()`;
  strip 1's physical order is mirrored (phys `6 + (5 - i)`).
- Mic is the ES7210 path: `M5.Mic` (registered in `M5`, **not** `hardware`).
  `Mic.record(buf, rate, stereo)` fills over DMA and returns;
  `Mic.isRecording()` goes False when full. Two buffers ping-pong for a
  gapless ~32 ms energy stream (256 samples @ 8 kHz). Mic and Speaker are
  mutually exclusive on this codec; this app never touches the speaker.
- Firmware: UIFlow2 v2.5.0 for CoreS3, 16 MB image.

## BOARD=cube — XINGZHI / xiaozhi-cube 1.54

An ESP32-S3 (rev v0.2, 16 MB flash, 8 MB embedded PSRAM) that M5 never made.
Pins come from `xiaozhi-esp32`'s own board config,
`main/boards/xingzhi-cube-1.54tft-wifi/config.h`, and every one below was
then confirmed on the hardware.

- **Firmware is UIFlow2 v2.5.0 for the M5Stack StampS3** — flashed at 0x0 the
  headless way (`uiflow2-headless-flashing`), file
  `e4436acc87fec305fe85a04394bdf300.bin`, then `make bootopt`.
  StampS3 because it is the only UIFlow2 build that is a *bare* ESP32-S3:
  no panel, no PMIC, no codec for `M5.begin()` to hunt for and hang on. The
  stock xiaozhi firmware was dumped to `exp/_backup/` first and can be put
  back with `esptool write_flash 0x0`.
- **Screen: `M5.UserDisplay`**, which is the thing that makes this possible —
  a full LovyanGFX device you hand a panel type and a pin list, with the same
  drawing surface `M5.Lcd` has, so `scd_face` never learns which one it got.
  ST7789, 240×240, SPI3 (`spi_host=2`) at 40 MHz, sclk 9 / mosi 10 / dc 8 /
  cs 14 / rst 18, backlight PWM on 13. **`invert=True`**; the panel's element
  order is already RGB (checked with a labelled R/G/B card — the labels read
  true). Note `M5.addDisplay` is NOT this: it only knows M5's own units.
- **Microphone: `machine.I2S`, not `M5.Mic`.** M5Unified drives I2S at 16
  bits and this board's MEMS mic puts 24-bit samples MSB-aligned in 32-bit
  slots, so `M5.Mic` returns a DC level and nothing else — mono a constant,
  stereo a slow drift, neither moving when you play music at it. At
  `bits=32, format=MONO` on ws 4 / sck 5 / sd 6 it works. Two gotchas:
  M5Unified holds an I2S port from boot, so call `M5.Speaker.end()` and
  `M5.Mic.end()` first or the driver answers `ESP_ERR_NOT_FOUND`; and
  registering an `irq` puts the port in non-blocking mode, which buys the
  same ping-pong the CoreS3 gets from its DMA recorder.
  Bytes 2..3 of each slot ARE the sample >> 16, so reading energy costs one
  uint16 load per sample, same as the CoreS3 path. The DC term is large and
  drifts, so it is removed per frame (`E[v²] − E[v]²`), and the result is
  ×8 at the exit to land on the scale every threshold downstream was tuned
  against. Measured in this room: quiet 24–80, music 590 avg / 2500 peak,
  gate at 140.
- **Buttons** on 0 (BOOT) / 39 / 40, active-low with internal pull-ups.
  BOOT toggles the ear; **39 is the top one and steps the palette forward**,
  40 steps back. Edge-detected, so one press is one step.
- **No body**: no servos, no LEDs. `on_beat`/`tick`/`rest` are empty and the
  dance is entirely on the panel.
- Speaker (I2S out, bclk 15 / ws 16 / dout 7) exists but is unused — and
  **cannot** be used to test the mic, because M5Unified's Speaker and Mic are
  mutually exclusive. Test with sound from the host instead.

## boot_option is a u8, and getting that wrong is silent

UIFlow2's `boot.py` reads `uiflow/boot_option` with **`get_u8`**, and
`esp32.NVS` types its keys. Write it with `set_i32` and `get_i32` reads 0
back perfectly happily — while `boot.py`'s `get_u8` raises NOT_FOUND, falls
back to 1, and spends 60 s on a network connect instead of starting the app.
Nothing reports an error anywhere. And an ST7789 holds its last image without
being refreshed, so the symptom is not a blank screen but the **previous
frame, frozen** — which reads as a hung app rather than one that never ran.
`tools/bootopt.py` (erase the key, then `set_u8`) is wired into `make deploy`
so this cannot be got wrong by hand again.

Related: `boot.py` also names a per-board startup override (hold Cardputer-ADV's
ESC, StickS3's BtnA, or touch the StackChan screen during a 100 ms window) to
get back to the menu without deleting main.py. **The StampS3 build has no such
override**, so on the cube the way back is `make undeploy`.

## The face, on two panels

`scd_face` holds one layout table per panel shape and picks by width. They
are not the same drawing scaled:

- **320×240** — face left, one hand over a drum pad in the right column.
- **240×240** — no room for that column, so the square **claps**: two palms
  under a face drawn flatter, driven together by the hit's own decay and
  springing apart after it, with accent strokes thrown off the point of
  impact. The pad's job (somewhere for the accent to live between beats)
  passes to a slim bar along the bottom, which is also the VU meter the
  twelve LEDs give the CoreS3 and this board has not got. The mode word and
  the tempo move to the top, because the bottom is now spoken for.

`make shots BOARD=cube` renders to `sim/shots/cube/` — **look at the PNGs,
do not reason about the coordinates.** The one thing the sim cannot judge is
colour on the real panel.

## The palette

The accent is the music, and it is the only saturated colour on screen —
that rule is what makes a flash legible, so cycling it must never introduce
a *second* colour. `C.PALETTE` is therefore a list of (name, lit, unlit)
triples: one hue, two brightnesses. Everything that draws in the accent
reads `S.accent`, never `C.ACCENT`, so one assignment moves the whole
program's idea of the music; the change forces a full repaint because the
accent sits under several elements at once.

## The link

`scd_link.py` listens for OP-CP's ESP-NOW step broadcasts (channel 1; wire
format in both files' headers — change one, change both) and dances from
ground truth: BD = strong beat, SD/CP = mid, hats/melody only breathe the
level, drumless bars still nod on the downbeat. Packets younger than
LINK_FRESH_MS own the dance and the microphone path is skipped entirely;
silence on the radio hands it back to the mic. The corner word reads
LINK / DANCE (mic) / LISTEN / MIC ONLY.

## The loop

```bash
make check BOARD=cube    # compile + upload + selftest on hardware
make shots BOARD=cube    # render the face states and look
make run BOARD=cube      # dance live; Ctrl-C stops it
make deploy BOARD=cube   # install as main.py, start on power-up
make probe BOARD=cube    # the real API surface
```

`make check` cannot judge the dance. For that, put a pattern on the
Cardputer, turn its volume up, and watch — or play something percussive from
the host. A **sustained** tone is a bad test signal: 250 ms beeps at 120 bpm
read as ~85 bpm because each beep produces more than one onset. A kick with
a real transient locks to 120 exactly.
