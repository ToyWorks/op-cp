# Rules for working in this repo

For an AI coding agent, or anyone new. The reference material lives in
[`docs/`](docs/); this file is only the things that will bite you.

## The gate

**A change is not done until `make check` passes**, and if you touched anything
visual, until you have run `make shots` and *looked at the PNGs*. Both loops,
every time — they prove different things
([docs/development.md](docs/development.md)).

```bash
make check      # compile + upload + self-test on the board + read back
make shots      # render every screen on the host, ghost check, then look
make probe      # what this firmware actually exposes
```

## Rules

**1. Never call an M5 API you have not confirmed exists on this board.** The
number one cause of failure here — a plausible-looking method that UIFlow1 had,
or that another M5 board has, and this firmware does not. `make probe` or
`make api OBJ=M5.Lcd` first, then write the call. Use
`getattr(obj, "name", None)` for anything optional, and wrap every optional
subsystem (keyboard, speaker, power, RTC) in `try/except` so the program degrades
instead of dying at line 1.

**2. Never `dir()` the `hardware` package.** `import hardware` is fine and fast.
`dir(hardware)` makes MicroPython import every submodule, which initialises
peripherals and **wedges the board until it is power-cycled**. Import the class
and inspect that.

**3. Modules deploy flat.** There is no `/flash/lib` on `sys.path`. `lib/*.py`
here lands as `/flash/opcp_*.py` there; the Makefile does it.

**4. Keep `app.py` importable.** Everything behind `if __name__ == '__main__':` —
`selftest.py` and the simulator both import the modules and drive them by hand.

**5. Never hardcode the resolution or a font size.** Read `M5.Lcd.width()` /
`height()` in `layout()`. Font names are **aliases** —
`FONTS.Montserrat12 is FONTS.DejaVu9` is True. Measure with `textWidth()`.

**6. Greys must be multiples of `0x10`.** RGB565 keeps 6 bits of green and 5 of
red/blue, so an arbitrary grey picks up a green cast.

**7. Redraw only what changed, and erase only the box you are about to paint.**
Clearing a region then painting into it *is* the flicker. And **text is the
expensive primitive** — four short `drawString`s cost more than clearing the
whole animation band. Numbers in
[docs/development.md](docs/development.md#what-a-frame-costs).

**8. Measure against pushed code.** `mpremote run host_script.py` takes the
script from the host and imports everything it uses from the *device's* flash.
Benchmark without `make push` first and you measure the old code.

## Layering

Imports run strictly one way. If a new module needs to be imported by something
below it in this list, fix the layering rather than adding a late import.

```
opcp_conf -> opcp_state -> opcp_audio / opcp_ui -> opcp_screen -> opcp_seq -> opcp_keys -> app
```

Add a screen to `opcp_screen`, a binding to `opcp_keys`, a constant to
`opcp_conf`. Reasoning in [docs/architecture.md](docs/architecture.md).

## Design language

Near-black ground; **at most one saturated colour lit at a time**, and a lit
colour always means "the track you are editing". Flat primitives only — no
gradients, no bevels, no outlines-plus-fills. Extreme type contrast: roughly a 3x
jump between a label and the value it labels.

## Where the rest is

| | |
|---|---|
| [docs/development.md](docs/development.md) | the two loops, the ghost check, frame costs, every target |
| [docs/architecture.md](docs/architecture.md) | layering, redraw discipline, timing and why no asyncio |
| [docs/uiflow2-notes.md](docs/uiflow2-notes.md) | measured platform facts: `playRaw`, fonts, filesystem, the hour-costing gotchas |
| [docs/instrument.md](docs/instrument.md) | what the thing does, from a player's side |
| [docs/screens.md](docs/screens.md) | every view, rendered |

**Keep those current.** When a bring-up teaches you something the hard way, fold
it back into the right file and commit it — that is why they read the way they do.
