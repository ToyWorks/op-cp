# UIFlow2 on the M5Stack Cardputer-ADV

UIFlow2 firmware is plain MicroPython, so `mpremote` is the CLI. There is no
official UIFlow2 command-line tool — M5Burner is a GUI, the Web IDE is a browser
tab, and `pip install CoreMP135-UiFlow2` is for a Debian-based Linux board and
has nothing to do with ESP32. Ignore all three.

Two loops make this directory self-verifying:

- **`make check`** runs the code on the real board and reads the result back.
- **`make shots`** runs the *real draw functions* on the host and writes PNGs,
  so the UI can be looked at without flashing.

## Rules

**1. Never call an M5 API you have not confirmed exists on this board.**
This is the number one cause of failure here — a plausible-looking method that
UIFlow1 had, or that another M5 board has, and this firmware does not:

```bash
make api OBJ=M5.Lcd
make probe            # everything, plus firmware version and screen size
```

Use `getattr(obj, "name", None)` for anything optional, and wrap every optional
subsystem (keyboard, speaker, power, RTC) in `try/except` so the program
degrades instead of dying at line 1.

**2. After every change, run `make check`.** It compiles every module with
`mpy-cross`, uploads, runs `selftest.py` on the board, and prints the result. A
change is not done until that passes. If you touched anything visual, run
`make shots` and *look at the PNGs* too.

**3. Never `dir()` the `hardware` package.** `import hardware` is fine and fast.
`dir(hardware)` makes MicroPython import every submodule, which initialises
peripherals and **wedges the board until it is power-cycled** — it looks like a
hung serial port. Import the class and inspect that:

```python
from hardware import MatrixKeyboard
dir(MatrixKeyboard)          # fine
```

**4. Modules deploy flat, next to `main.py`.** The device's `sys.path` is
`['', '.frozen', '/lib', '/system', '/flash/libs']` — there is **no
`/flash/lib`**. A `lib/` subdirectory uploads happily and then fails to import.
`''` is the working directory, `/flash`. So `lib/*.py` here lands as
`/flash/opcp_*.py` there; the Makefile already does this.

**5. Keep `app.py` importable.** Everything lives behind
`if __name__ == '__main__':`. `selftest.py` and the simulator both import the
modules and drive them by hand; import-time side effects break both.

**6. Never hardcode the resolution or a font size.** Read `M5.Lcd.width()` /
`height()` in `layout()`. Fonts are named objects, and **the names are aliases**:
`FONTS.Montserrat12 is FONTS.DejaVu9` returns True. There is exactly one
typeface here, at eight heights — 15, 16, 18, 21, 27, 44, 49, 52. Pick by
measuring with `textWidth()`, never by assuming a size exists.

**7. Greys must be multiples of `0x10`.** The panel is RGB565: green keeps 6
bits, red and blue only 5. An arbitrary grey like `0x0E0E0E` quantises to
`rgb(8,12,8)` and the whole background picks up a **green cast**. Multiples of
`0x10` land on the same value in all three channels. The simulator reproduces
this, which is how it was caught.

**8. Redraw only what changed — and know what things cost.** Measured on this
panel, for the 240x69 animation band:

| primitive | cost |
|---|---|
| 4x `drawString` (4 chars each) | **7.6 ms** |
| `fillRect` over the whole band | 6.8 ms |
| `fillRect` over the face box (128x52) | 2.8 ms |
| 4x `fillRect` over a bar column | 1.2 ms |
| 4x `textWidth` | 0.07 ms |

**Text is the expensive primitive here** — four short strings cost more than
clearing the entire band. Cache what they depend on and redraw them only when
it changes. Fills are cheap by comparison; what makes them hurt is clearing a
region and then painting into it, because the panel spends part of every frame
showing the cleared state. That is what "flicker" is.

So: erase only the box you are about to paint over, and wrap a frame in
`U.hold()` / `U.release()` (LovyanGFX `startWrite`/`endWrite`) so the whole
repaint reaches the panel as one transaction instead of dozens.

`make shots` runs a **ghost check**: it drives each animated view 40 frames
without clearing between them, then diffs the band against the same state drawn
clean. Any difference fails the build and the coordinates are printed. It is
what catches an erase box that is too small — or, as happened here, one that is
too big and eats a neighbour.

## Sound

`M5.Speaker.tone()` is a bare square wave at constant amplitude — no envelope,
one timbre, and drums as pure tones. It is a fallback here, not the sound
source. The real kit is signed-16-bit PCM in `lib/opcp_kit.bin`, rendered on the
host by `make kit` and played with `playRaw`.

Facts about `playRaw`, all measured on device rather than assumed:

- **It interprets any buffer as int16**, whatever type you pass. `bytearray`,
  `array('B')` and `array('h')` all behave identically — 8000 bytes plays for
  459 ms at rate 8000, i.e. 4000 samples. There is no uint8 path.
- **The sample-rate argument really works**, and is how notes are pitched: one
  buffer per melodic track, replayed at `rate * 2**(semitones/12)`. Usable range
  is **700 Hz to 48 kHz**, verified against expected durations. Outside it,
  fold by octaves — clamping puts the note out of tune.
- **`memoryview` slices are accepted.**
- **`isPlaying()` leads the audio by ~39 ms** (one DMA buffer). Do not use it to
  measure durations without accounting for that.

Rendering the kit **on the device costs ~5.4 s** — far too slow for boot, which
is why `tools/build_kit.py` runs on the host. The noise source is a seeded
xorshift so the blob is reproducible; `lib/opcp_kit.bin` is a build artifact.

**Load per sound, never as one blob.** With the app running there is ~66 KB
free but no contiguous 36 KB block, so reading the whole file at once dies with
`MemoryError: memory allocation failed, allocating 36096 bytes`. Free heap is
not the largest free block. Twelve allocations of 1-4 KB fit fine.

## Timing, and why there is no asyncio here

The step clock schedules against an absolute deadline and accumulates
(`ticks_add(next_tick, interval)`), so it does not drift. Measured under real
playback: **median 1 ms late, p90 2 ms, max 3 ms** against a 133 ms sixteenth.

asyncio would not improve this and is deliberately not used:

- It is cooperative, so the one thing that *did* cause jitter — a 62 ms
  full-screen redraw — would block an event loop exactly as it blocks this one.
  The fix was to stop doing full redraws for control changes, not to change the
  concurrency model. Full redraw is now view-switch only; everything else
  repaints the header, footer or roll alone.
- It helps when code *waits* on I/O. Nothing here waits.
- Tasks and awaits allocate, and the heap floor under load is already ~23 KB
  with the PCM kit resident.

If you add something that genuinely blocks (a network fetch, an SD read), that
is the moment to reconsider — not before.

## The link

`lib/opcp_link.py` broadcasts every step over ESP-NOW (channel 1, 9-byte
packets: step, per-track hit bitmask, drum index, bpm) for the StackChan in
`../stackchan-dance`, which prefers packets over its microphone and falls
back automatically. The wire format lives in both files' headers — change
one, change both. ctrl+N toggles; on by default (a broadcast nobody hears
costs nothing). The radio comes up lazily, so `import espnow` failures
degrade to link-off instead of dying at boot.

## The loop

```bash
make check      # compile + upload + run selftest on hardware + read back
make shots      # render every screen to sim/shots/ and look at them
make run        # run app.py live; tracebacks come back here, Ctrl-C stops
make deploy     # install as main.py and reboot — starts on power-up
make undeploy   # remove main.py, boot back to the UIFlow2 menu
make probe      # dump the real API surface
make kit        # rebuild lib/opcp_kit.bin after tuning sounds in opcp_synth
make audio      # render the kit to WAV on the host, old vs new, then listen
make metrics    # re-dump font metrics from the board (after a firmware update)
make repl       # interactive REPL, Ctrl-] to exit
make port       # show the detected serial port
```

## Structure

`app.py` is the lifecycle and nothing else. State lives in one object, `S`, so
that modules can share it without threading arguments through every call.
Imports run strictly one way, so nothing cycles:

```
opcp_conf     constants: palette, musical tables, key maps       (no state)
   ^
opcp_state    S — every mutable field, in one object
   ^
opcp_synth    PCM synthesis — HOST side, run by tools/build_kit.py
opcp_audio    the mixer and the voices; loads lib/opcp_kit.bin
opcp_ui       fonts, layout, the roll, the header, the footer, help
   ^
opcp_screen   the three alternate views + the full-screen compositor
   ^
opcp_seq      pattern generation, the transport clock, persistence
   ^
opcp_keys     the keyboard bindings
   ^
app.py        setup() / loop()
```

Add a screen to `opcp_screen`, a binding to `opcp_keys`, a constant to
`opcp_conf`. If a new module needs to be imported by something below it in that
list, the layering is wrong — fix the layering, don't add a late import.

## What each loop can and cannot prove

`selftest.py` runs headless on the device. It proves that every computed
rectangle lands inside the panel, that regions do not overlap, that every string
fits the box it is drawn into, that all four tracks × 49 key bindings dispatch
without raising, that the transport advances, that save/load round-trips, and
that memory headroom remains.

`sim/` runs `opcp_ui`/`opcp_screen`'s real draw calls against a Pillow-backed M5
stub, with **font metrics measured off the device** (`sim/metrics.json`), so
geometry is pixel-exact and colour is quantised through RGB565 as the panel
does. String widths run up to 2px wide on a few lowercase pairs that kern —
conservative, so "fits in the sim" implies "fits on the panel".

Neither can judge whether the result is *good*: panel gamma, backlight, viewing
angle and refresh behaviour are still hardware questions, and so is taste.

## Gotchas that will cost an hour

- **The serial port is exclusive.** The UIFlow2 Web IDE and `mpremote` cannot
  both hold it. A stuck `could not open port` is usually a forgotten browser tab.
- **`while True` hangs automation.** `mpremote run app.py` never returns. That
  is why `selftest.py` exists — bounded frames, then `raise SystemExit`.
- **`mpremote exec` does not preserve globals between calls.** You cannot test
  "did main.py run at boot?" by checking whether a global still exists — it
  never will. Write a marker file instead.
- **`mpremote run host_script.py` imports the modules on `/flash`, not the ones
  you just edited.** The script comes from the host; everything it imports comes
  from the device. Benchmark a change without `make push` first and you will
  measure the old code and conclude, confidently and wrongly, that your change
  did nothing. (Cost an hour here: a fix worth 10x looked like it was worth 0x.)
- **USB re-enumerates on reset.** Right after `make deploy`, `mpremote` will
  fail with `Errno 6 Device not configured` until the port comes back. Wait for
  `/dev/cu.usbmodem*` to reappear, then a couple more seconds.
- **Boot mode.** This board is burned to run `main.py` directly (verified with a
  marker file: main.py executes ~4.2s after reset). If a board stops at a menu
  waiting for the network, it was burned with "show startup menu".
- **Wi-Fi and the access code live in NVS**, written by M5Burner. `mpremote`
  cannot touch them; only reflashing changes them.
- **Two `/dev/cu.usbmodem*` ports is normal** — monitors and docks enumerate as
  serial too. `tools/find-port.sh` matches the M5Stack manufacturer string.
