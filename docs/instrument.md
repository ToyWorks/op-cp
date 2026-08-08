# The instrument

Four tracks, sixteen steps, a piano hiding in the keyboard.

## The keybed

The middle two keyboard rows are a piano — white keys on the home row, black keys
in the physical gaps above them:

```
     w e   t y u   o p          black keys
    a s d f g h j k l ;         white keys   C D E F G A B C D E

1 2 3 4 5 6 7 8                 steps 1-8
z x c v b n m ,                 steps 9-16
```

Those two rows are **nothing but piano**. Every function that used to squat
between the keys lives on a ctrl layer now, so a missed black key can no longer
wipe a track:

```
SPACE play/stop      ENTER record arm (live, quantized to 16ths)
^G generate  ^C clear  ^M mute  ^P pattern bank  ^[ ^] tempo  ^F files  ^N link
- = octave   ` scale   9 swing  0 volume   . / track   \ next view
```

`ctrl` is read from the keyboard driver's cached pressed-key table, so testing it
is a dict lookup rather than an I²C transaction; a keyboard without that API — a
plain Cardputer's — simply never reports ctrl, and the piano still works.

## Tracks

Four — **LEAD, BASS, KEYS, PERC** — colour-coded with OP-1's four encoder
colours, which double as the colours of the four parameter slots along the
bottom. PERC's steps are drum indices rather than semitones.

Four pattern banks (`^P`), each holding all four tracks.

## Sound

Signed-16-bit PCM, not `tone()` beeps. `M5.Speaker.tone()` is a bare square wave
at constant amplitude — no envelope, one timbre, drums as pure tones — so it is
the fallback here, not the sound source.

The kit is synthesised **on the host** by `make kit` into `lib/opcp_kit.bin` and
played with `playRaw`: one buffer per melodic track, replayed at
`rate * 2**(semitones/12)` to pitch it. Rendering it on the device costs ~5.4 s,
which is no way to boot. The noise source is a seeded xorshift, so the blob is
reproducible; `make audio` renders it to WAV on the host, old against new, so you
can listen before flashing.

The measured `playRaw` behaviour it relies on is in
[uiflow2-notes.md](uiflow2-notes.md#audio).

## Files

`^F` opens eight save slots plus four factory patterns — ACID, DISCO, DUB, CHIP.

Slots live on the **SD card when one is in** and `/flash` otherwise, so patterns
survive a firmware reflash. Three direct-access columns, and **no cursor**: every
entry is labelled with the key that fires it, the same contract as the step keys.
`1`-`8` load; `s` then a digit saves; `w e t y` drop in a preset. A preset lands
in the *current* bank, so `^P` then a preset key stacks different grooves into
different banks.

## Link

`^N` toggles it; on by default, because a broadcast nobody hears costs nothing.

Every step played is broadcast over ESP-NOW — 9 bytes: magic, version, type,
step, per-track hit bitmask, drum index, bpm — so a companion device can dance
from ground truth instead of listening to the room. Connectionless, channel 1
pinned at both ends, no pairing. The wire format is documented in
`lib/opcp_link.py`'s header; a receiver has to agree with it.

The radio comes up lazily, so a missing `espnow` module degrades to link-off
rather than dying at boot.
