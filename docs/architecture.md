# Architecture

`app.py` is the lifecycle and nothing else — 121 lines. State lives in one
object, `S`, so modules share it without threading arguments through every call.

## Import direction, strictly one way

```
opcp_conf     constants: palette, layout, musical tables, key maps   (no state)
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
list, **the layering is wrong** — fix the layering, do not add a late import.

## Two constraints that shape everything

- **`app.py` must stay importable.** Everything lives behind
  `if __name__ == '__main__':`. `selftest.py` and the simulator both import the
  modules and drive them by hand, so an import-time side effect breaks both.
- **Modules deploy flat.** The device's `sys.path` is
  `['', '.frozen', '/lib', '/system', '/flash/libs']` — there is **no
  `/flash/lib`**. `lib/*.py` here lands as `/flash/opcp_*.py` there; the Makefile
  does that. A `lib/` subdirectory would upload happily and then fail to import.

## Redraw discipline

Full-screen redraw is **view-switch only**. Everything else repaints the header,
the footer or the roll alone, and the animated views erase only the box they are
about to paint over.

This is not premature optimisation — it was a timing fix. A 62 ms full-screen
redraw against a 133 ms sixteenth made the step clock fire up to 60 ms late
whenever you touched a control mid-play. See
[development.md](development.md#what-a-frame-costs).

## Timing, and why there is no asyncio

The step clock schedules against an **absolute deadline** and accumulates
(`ticks_add(next_tick, interval)`), so it does not drift. Measured under real
playback: median 1 ms late, p90 2 ms, max 3 ms against a 133 ms sixteenth.

asyncio would not improve this and is deliberately not used:

- It is cooperative, so the one thing that *did* cause jitter — that 62 ms
  redraw — would block an event loop exactly as it blocks this one. The fix was
  to stop doing full redraws, not to change the concurrency model.
- It helps when code *waits* on I/O. Nothing here waits.
- Tasks and awaits allocate, and the heap floor under load is already ~36 KB
  with the PCM kit resident.

If something genuinely blocking is added — a network fetch, an SD read — that is
the moment to reconsider, not before.
