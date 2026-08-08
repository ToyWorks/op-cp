# Development: two loops

UIFlow2 firmware is ordinary MicroPython, so `mpremote` is the whole toolchain,
and `mpremote run` sends stdout and tracebacks back to the terminal. That makes
two cheap loops possible. **Neither replaces the other**, and a change is not
done until both are green.

```
        host loop                              device loop
        ─────────                              ───────────
edit ─► render the program's OWN draw     edit ─► mpy-cross every module
     ─► one PNG per screen state               ─► upload (flat, to /flash)
     ─► look at them                           ─► run selftest.py ON the board
                                               ─► read the printout back

   sub-second, no hardware                  ~30 s, proves it on silicon
   geometry · typography · RGB565           dispatch · timing · memory · peripherals
```

The host loop is honest about geometry and typography and lies about colour cast,
gamma, backlight and refresh. The device loop is honest about everything the host
cannot see and blind to whether the result looks any good. **Neither judges
taste** — that is still a human, looking at the panel.

## The device loop

```bash
make check
```

compiles every module with `mpy-cross`, uploads, runs `selftest.py` on the board
and prints the result.

It is a **report, not an assertion suite**: it prints the numbers a human would
otherwise read off the screen — frame times, the heap floor under sustained
play, save-slot state, the pitch each MIDI note resolves to — and *then* asserts
on them. The printout is what makes a failure diagnosable without the board in
front of you.

What it proves: every computed rectangle lands inside the 240×135 panel, regions
do not overlap, every string fits the box it is drawn into, all four tracks × 49
key bindings dispatch without raising, the transport advances, save/load
round-trips, no `MemoryError` over ~1350 frames of playback, and headroom
remains.

It found four real layout bugs on its first run: three drum labels overflowed
their step cell, and the help page ran 47 px past the bottom of the screen.

## The host loop

```bash
make shots
```

renders every screen state to `sim/shots/` by running the program's own draw
functions against a Pillow-backed `M5` stub. The hardware boundary is drawn
exactly at the `M5.Lcd` primitives — everything above it is the real program, so
the simulator cannot drift from the device the way a hand-written HTML mock
would.

Two things make it faithful rather than approximate:

- **Font metrics are measured off the device.** `sim/metrics.json` holds the real
  per-character advance for every font, dumped by `make metrics`. Glyphs are drawn
  one at a time and advanced by the device's width, so a centred string lands on
  the same pixel it does on the panel. Re-dump after a firmware update — the
  fonts are firmware, not app.
- **Colour is quantised through RGB565**, as the panel does. This is how the
  green cast on every dark grey was caught: `0x0E0E0E` quantises to `rgb(8,12,8)`
  because green keeps 6 bits and red/blue only 5. The greys are all multiples of
  `0x10` now.

It also caught the parameter strip drowning out the sequence, the total absence
of type hierarchy, and a playhead mark floating detached above its column.

## The ghost check

`make shots` ends by driving each animated view **40 frames with no clearing in
between**, then diffing the band against the same state drawn onto a clean
screen. Any difference is a pixel some element failed to erase. It fails the
build and prints the coordinates.

This exists because the animated views deliberately **do not** clear themselves
each frame — see below — so every element owes an exact erase, and no single
screenshot can show whether it paid.

Two things it caught immediately:

- A long-standing bug: two burst sparks were drawn *outside* the rectangle that
  erases them, so they never went away.
- Its own author, going the other way: converting the ring to per-dot erasing
  reported **missing** pixels rather than left-over ones — the signature of
  erasing too much. Adjacent ring dots are 9 px apart and the erase boxes were
  13 px wide, so erasing dot B took a bite out of dot A. All erasing now happens
  before any drawing.

## What a frame costs

Clearing a region and then painting into it **is** the flicker: the panel spends
part of every frame showing the cleared state. So each view erases only the box
it is about to paint over, and a repaint is wrapped in `startWrite`/`endWrite` so
it reaches the panel as one SPI transaction instead of dozens.

Measured on the panel, for the 240×69 animation band:

| primitive | cost |
|---|---|
| 4× `drawString`, 4 characters each | **7.6 ms** |
| `fillRect` over the whole band | 6.8 ms |
| `fillRect` over a 128×52 box | 2.8 ms |
| 4× `fillRect` over a bar column | 1.2 ms |
| 4× `textWidth` | 0.07 ms |

**Text is the expensive primitive** — four short strings cost more than clearing
the entire band, which is not what you would guess. Caching the four track names
against the selection is what actually made BARS fast.

| view | before | after |
|---|---|---|
| FACE | 9.8 ms | 6.2 ms |
| RING | 8.3 ms | 3.2 ms |
| BARS | 16.5 ms | 1.7 ms (steady selection) |

against a 55 ms frame budget.

> **Measure, but check what you are measuring.** `mpremote run host_script.py`
> takes the script from the host and imports everything it uses **from the
> device's flash**. Two of the numbers above initially showed no improvement and
> the change was reverted as useless — it was not; the benchmark had been running
> against un-pushed code. `make push` first.

## Targets

| target | what it does |
|---|---|
| `make venv` | create `.venv/` with mpremote, mpy-cross, esptool |
| `make check` | compile + upload + run the self-test on hardware + read back |
| `make shots` | render every screen, run the ghost check, and look |
| `make kit` | rebuild `lib/opcp_kit.bin` after tuning sounds in `opcp_synth` |
| `make audio` | render the kit to WAV on the host, old vs new, then listen |
| `make metrics` | re-dump font metrics from the board after a firmware update |
| `make run` | run `app.py` live; tracebacks return here, Ctrl-C stops |
| `make deploy` / `undeploy` | install as `main.py` and reboot / remove it |
| `make probe` | dump the API surface this firmware actually has |
| `make api OBJ=M5.Lcd` | list one object's attributes |
| `make repl` / `ls` / `mem` / `reset` / `port` | the usual |

The serial port is found by matching the board's USB **product** string, so a
second `/dev/cu.usbmodem*` from a monitor, a dock or another M5 board does not
confuse it.
