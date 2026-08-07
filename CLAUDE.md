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

**8. Redraw only what changed.** `fillScreen()` per frame flickers visibly.
Use `setTextColor(fg, bg)` so glyphs paint their own background, and `fillRect`
only the band whose width can change.

## The loop

```bash
make check      # compile + upload + run selftest on hardware + read back
make shots      # render every screen to sim/shots/ and look at them
make run        # run app.py live; tracebacks come back here, Ctrl-C stops
make deploy     # install as main.py and reboot — starts on power-up
make undeploy   # remove main.py, boot back to the UIFlow2 menu
make probe      # dump the real API surface
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
opcp_audio    the mixer and the voices
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
