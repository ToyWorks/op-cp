# UIFlow2 on the M5Stack Cardputer-ADV

UIFlow2 firmware is plain MicroPython, so `mpremote` is the CLI. There is no
official UIFlow2 command-line tool — M5Burner is a GUI, the Web IDE is a browser
tab, and `pip install CoreMP135-UiFlow2` is for a Debian-based Linux board and
has nothing to do with ESP32. Ignore all three.

What matters is that `mpremote run` sends stdout **and tracebacks** back to the
terminal. That is what makes this directory self-verifying: code runs on the
real board and the failure comes back as text.

## Rules

**1. Never call an M5 API you have not confirmed exists on this board.**
This is the number one cause of failure here — a plausible-looking method that
UIFlow1 had, or that another M5 board has, and this firmware does not. Confirm
first:

```bash
make api OBJ=M5.Lcd
make api OBJ=M5.Speaker
make probe            # everything at once, plus firmware version and screen size
```

Reach for `getattr(obj, "name", None)` for anything optional, and wrap every
optional subsystem (keyboard, speaker, power, RTC) in `try/except` so the
program degrades instead of dying at line 1.

**2. After every change, run `make check`.** It compiles with `mpy-cross`,
uploads, runs `selftest.py` on the board, and prints the result. A change is not
done until that passes.

**3. Never `dir()` the `hardware` package.** `import hardware` is fine and fast.
`dir(hardware)` makes MicroPython import every submodule, which initialises
peripherals and **wedges the board until it is power-cycled** — it will look
like a hung serial port. Import the class and inspect that:

```python
from hardware import MatrixKeyboard
dir(MatrixKeyboard)          # fine
```

**4. Keep `app.py` importable.** Everything lives in functions behind
`if __name__ == '__main__':`. `selftest.py` imports the module and drives
`setup()` and `loop()` by hand; if import has side effects, automation breaks.

**5. Never hardcode the resolution or a font size.** Read `M5.Lcd.width()` and
`height()` in `setup()`. Fonts are named objects (`M5.Lcd.FONTS.DejaVu12`), not
point sizes, and the available set varies by build — select at runtime by
measuring with `M5.Lcd.textWidth()`.

**6. Redraw only what changed.** `fillScreen()` per frame flickers visibly on
this panel. Use `setTextColor(fg, bg)` so glyphs paint their own background, and
`fillRect` only the band whose width can change.

## The loop

```bash
make check      # compile + upload + run selftest on hardware + read back  <- the one to use
make run        # run app.py live; tracebacks come back here, Ctrl-C stops
make deploy     # install as main.py and reboot — starts on power-up
make undeploy   # remove main.py, boot back to the UIFlow2 menu
make probe      # dump the real API surface
make repl       # interactive REPL, Ctrl-] to exit
make port       # show the detected serial port
```

## What the self-test can and cannot prove

`selftest.py` runs headless. It proves that every computed rectangle lands
inside the panel, that regions do not overlap, that every string fits the box it
is drawn into, that all 4×~40 key bindings dispatch without raising, that the
transport advances, and that memory headroom remains. It prints the numbers so
they can be checked rather than assumed.

It **cannot** see the screen. Whether the result is legible, well spaced, or
pretty is still a human question. When layout is in doubt, print the measured
values and reason about those — do not guess at pixels.

## Gotchas that will cost an hour

- **The serial port is exclusive.** The UIFlow2 Web IDE and `mpremote` cannot
  both hold it. A stuck `could not open port` almost always means a forgotten
  browser tab.
- **`while True` hangs automation.** `mpremote run app.py` never returns. That
  is why `selftest.py` exists — bounded frames, then `raise SystemExit`.
- **Boot mode.** If the board was burned with "show startup menu" it stops at a
  menu waiting for the network. Burn it to run `main.py` directly.
- **Wi-Fi and the access code live in NVS**, written by M5Burner. `mpremote`
  cannot touch them; only reflashing changes them.
- **Two `/dev/cu.usbmodem*` ports is normal** — USB monitors and docks enumerate
  as serial too. `tools/find-port.sh` matches the M5Stack manufacturer string
  rather than guessing.

## Layout

```
app.py           the program; deployed to the board as main.py
selftest.py      headless harness — what `make check` runs
lib/             shared modules, synced to :lib on push/deploy
tools/probe.py   API surface dump
tools/find-port.sh
```
