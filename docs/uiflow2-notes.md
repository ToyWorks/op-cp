# UIFlow2 notes

Firmware and platform facts, all measured on a Cardputer-ADV rather than taken
from documentation. Most cost a debugging session.

## The toolchain

UIFlow2 firmware is plain MicroPython, so `mpremote` is the CLI. There is **no
official UIFlow2 command-line tool** — M5Burner is a GUI, the Web IDE is a
browser tab, and `pip install CoreMP135-UiFlow2` is for a Debian-based Linux
board and has nothing to do with ESP32. Ignore all three.

## The API surface

- **Never call an M5 API you have not confirmed exists on this board.** This is
  the number one cause of failure — a plausible-looking method that UIFlow1 had,
  or that another M5 board has, and this firmware does not. `make probe` dumps
  everything, `make api OBJ=M5.Lcd` dumps one object. Use
  `getattr(obj, "name", None)` for anything optional, and wrap every optional
  subsystem (keyboard, speaker, power, RTC) in `try/except` so the program
  degrades instead of dying at line 1.
- **Never `dir()` the `hardware` package.** `import hardware` is fine and fast.
  `dir(hardware)` makes MicroPython import every submodule, which initialises
  peripherals and **wedges the board until it is power-cycled** — it looks like a
  hung serial port. Import the class and inspect that:
  `from hardware import MatrixKeyboard; dir(MatrixKeyboard)`.

## Display

- **Never hardcode the resolution or a font size.** Read `M5.Lcd.width()` /
  `height()` in `layout()`.
- **Font names are aliases.** `FONTS.Montserrat12 is FONTS.DejaVu9` returns
  `True`. There is exactly one typeface here at eight heights — 15, 16, 18, 21,
  27, 44, 49, 52. Pick by measuring with `textWidth()`, never by assuming a size
  exists.
- **Greys must be multiples of `0x10`.** The panel is RGB565: green keeps 6 bits,
  red and blue only 5. An arbitrary grey like `0x0E0E0E` quantises to
  `rgb(8,12,8)` and the whole background picks up a **green cast**. Multiples of
  `0x10` land on the same value in all three channels. The simulator reproduces
  this, which is how it was caught.
- **Redraw only what changed, and know what it costs.** See
  [development.md](development.md#what-a-frame-costs) — text turns out to be the
  expensive primitive, not fills.

## Audio

Facts about `playRaw`, all measured rather than assumed:

- **It interprets any buffer as int16**, whatever type you pass. `bytearray`,
  `array('B')` and `array('h')` behave identically — 8000 bytes plays for 459 ms
  at rate 8000, i.e. 4000 samples. There is no uint8 path.
- **The sample-rate argument really works**, and is how notes are pitched: one
  buffer per melodic track, replayed at `rate * 2**(semitones/12)`. Usable range
  is **700 Hz to 48 kHz**, verified against expected durations. Outside it, fold
  by octaves — clamping puts the note out of tune.
- **`memoryview` slices are accepted.**
- **`isPlaying()` leads the audio by ~39 ms** (one DMA buffer). Do not use it to
  measure durations without accounting for that.
- **Load per sound, never as one blob.** With the app running there is ~66 KB
  free but no contiguous 36 KB block, so reading the whole kit at once dies with
  `MemoryError: memory allocation failed, allocating 36096 bytes`. Free heap is
  not the largest free block. Twelve allocations of 1–4 KB fit fine.
- Rendering the kit **on the device costs ~5.4 s** — far too slow for boot, which
  is why `tools/build_kit.py` runs on the host.

## Filesystem

**Modules deploy flat, next to `main.py`.** The device's `sys.path` is
`['', '.frozen', '/lib', '/system', '/flash/libs']` — there is **no
`/flash/lib`**. A `lib/` subdirectory uploads happily and then fails to import.
`''` is the working directory, `/flash`. The Makefile already lands `lib/*.py`
as `/flash/opcp_*.py`.

## Gotchas that will cost an hour

- **The serial port is exclusive.** The UIFlow2 Web IDE and `mpremote` cannot
  both hold it. A stuck `could not open port` is usually a forgotten browser tab.
- **`while True` hangs automation.** `mpremote run app.py` never returns. That is
  why `selftest.py` is bounded and ends in `raise SystemExit`.
- **`mpremote exec` does not preserve globals between calls.** You cannot test
  "did `main.py` run at boot?" by checking whether a global still exists — it
  never will. Write a marker file instead.
- **`mpremote run host_script.py` imports the modules on `/flash`, not the ones
  you just edited.** The script comes from the host; everything it imports comes
  from the device. Benchmark a change without `make push` first and you will
  measure the old code and conclude, confidently and wrongly, that your change
  did nothing.
- **USB re-enumerates on reset.** Right after `make deploy`, `mpremote` will fail
  with `Errno 6 Device not configured` until the port comes back. Wait for
  `/dev/cu.usbmodem*` to reappear, then a couple more seconds.
- **Boot mode.** This board is burned to run `main.py` directly (verified with a
  marker file: `main.py` executes ~4.2 s after reset). If a board stops at a menu
  waiting for the network, it was burned with "show startup menu".
- **Wi-Fi and the access code live in NVS**, written by M5Burner. `mpremote`
  cannot touch them; only reflashing changes them.
- **Two `/dev/cu.usbmodem*` ports is normal** — monitors and docks enumerate as
  serial too, and so does a second M5 board. `tools/find-port.sh` matches the USB
  product string, not just the manufacturer.
