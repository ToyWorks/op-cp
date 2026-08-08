# OP-CP

**A pocket step sequencer for the M5Stack Cardputer-ADV** — four tracks, sixteen
steps, a PCM synth, and a piano hiding in the keyboard. UIFlow2 MicroPython.

![the roll, playing](docs/screens/roll-playing.png)

| | | |
|:--:|:--:|:--:|
| ![face](docs/screens/face-lead-hit.png) | ![ring](docs/screens/ring-perc-hit.png) | ![bars](docs/screens/bars-perc-hit.png) |

## Build and run

Requires an M5Stack Cardputer-ADV with UIFlow2 firmware (M5Burner installs it;
`make probe` confirms what you have) and Python 3 on the host.

```bash
make venv       # mpremote, mpy-cross and esptool into .venv/
make check      # compile, upload, run the self-test on the board, read it back
make deploy     # install as main.py — starts on power-up
```

`make check` is the gate: it compiles every module with `mpy-cross`, uploads,
runs `selftest.py` **on the board**, and prints the result. A change is not done
until it passes.

```bash
make shots      # render every screen on the host, run the ghost check, look
```

`make shots` renders the program's *own* draw functions against a Pillow-backed
`M5` stub — with font metrics measured off the real device — and then diffs 40
live animation frames against a clean redraw to prove nothing was left behind.

Full target list in [docs/development.md](docs/development.md#targets).

## Results

The self-test found four layout bugs on its first run; the simulator found a
green cast on every dark grey (`0x0E0E0E` quantises to `rgb(8,12,8)` on RGB565);
the ghost check found two sparks that had never been erased since the feature was
written.

Frame cost on the panel, against a 55 ms budget — after switching from
"clear the band and redraw" to "erase only the box you are about to paint":

| animated view | before | after |
|---|---|---|
| FACE | 9.8 ms | **6.2 ms** |
| RING | 8.3 ms | **3.2 ms** |
| BARS | 16.5 ms | **1.7 ms** |

The surprise underneath those numbers: **text is the expensive primitive.** Four
4-character `drawString`s cost 7.6 ms — more than clearing the entire 240×69
animation band (6.8 ms), and six times four bar-column fills (1.2 ms). Caching
the labels is what made BARS fast, not touching the fills.

Step clock, measured under real playback: median 1 ms late, p90 2 ms, max 3 ms
against a 133 ms sixteenth. Heap floor over ~1350 frames of playback with the PCM
kit resident: ~36 KB, no `MemoryError`.

## Documentation

| | |
|---|---|
| [instrument.md](docs/instrument.md) | the manual — keybed, tracks, sound, files, link |
| [screens.md](docs/screens.md) | every view, rendered |
| [development.md](docs/development.md) | the two loops, the ghost check, frame costs, `make` targets |
| [architecture.md](docs/architecture.md) | module layering, redraw discipline, timing |
| [uiflow2-notes.md](docs/uiflow2-notes.md) | measured firmware and platform facts |

[CLAUDE.md](CLAUDE.md) is the short rulebook an AI coding agent reads before
touching this repo. The one rule worth repeating here: **confirm an M5 API exists
before calling it** — inventing a plausible method is the most common way UIFlow2
code fails.

## License

MIT — see [LICENSE](LICENSE).
