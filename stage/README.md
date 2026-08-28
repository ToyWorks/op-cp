# Stage — the show's watcher, on an M5Stack StickS3

The third machine on the desk. OP-CP plays, `dance/` dances — this one
**watches**: a status panel that animates to the beat, a microphone that
measures the tempo actually reaching the room, and the emergency stop.

This directory is the *instrument*: hardware, panel, animation, ear. Its
control interface — the manifest, the validated command table, the serial
protocol an agent drives it through — lives in
[**tiny-MHS**](https://github.com/ToyWorks/tiny-mhs) under
`examples/stage-node/`, which imports these modules from the submodule and
adds only the table. Same split as the sequencer itself: the instrument here,
the interface there.

| File | Role |
| --- | --- |
| `lib/stage_board.py` | The only file that touches M5: screen, button, and the microphone's queued double-buffer capture. |
| `lib/stage_anim.py` | The panel: tap / face / fist / bars, in dance's design language — one accent hue, tight erases. `tap` is the seven-frame sprite cycle; the rest are drawn. |
| `lib/stage_beat.py` | The ear's logic: dance's onset detector made standalone, plus a grid fit over the onset train for ±2 bpm tempo. |
| `lib/stage_espnow.py` | Receive-only ESP-NOW listener for OP-CP's step broadcast. It has no transmit path, deliberately. |
| `art/` | The tap and punch frames, how they were made, and what the panel had to be told about them. |
| `tools/build_tap.py` | Source strip -> the seven panel sprites. Re-run it if the art changes. |

## Facts measured on this hardware

- `M5.Speaker.end()` must run before `M5.Mic.begin()`, or the mic "works"
  while every frame reads exactly zero (the same lesson as dance's cube).
- `M5.Mic.record()` **queues** — `isRecording()` is the queue depth — so two
  one-second buffers ping-pong gaplessly and sub-frame timestamps come from
  sample arithmetic, which is exact.
- A kick re-triggers on its own tail ~160 ms after the attack; the beat
  tracker's refractory window is 200 ms because of it.
- Firmware is UIFlow2 for StickS3; `boot_option` must be 0 (see
  `../dance/tools/bootopt.py`) or `main.py` silently never runs.

Deploy and drive it from the tiny-MHS repo, which carries the serial tooling
these boards need (`tools/devrepl.py` — mpremote's DTR/RTS handshake resets
this board).
