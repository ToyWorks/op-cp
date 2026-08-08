# SCD — onset detection over a stream of frame energies.
#
# Pure integer logic, no hardware imports: selftest feeds it synthetic
# energy sequences and asserts on the beats that come out, on the device
# and on the host alike. The mic layer only ever calls feed().
#
# Three references, three jobs — the first version conflated them and went
# numb the moment the music was continuous:
#
#   floor  — the QUIET reference. Falls quickly, rises one unit a frame,
#            so sustained music cannot drag it up to its own average
#            (which is exactly what the old 1/24 EMA did: within a second
#            the "floor" was the music, level collapsed, the face froze).
#   peak   — a decaying maximum, so the level self-normalises to this
#            track at this volume and distance, whatever they are.
#   local  — a short EMA of the near past; a beat is a jump against it,
#            not against the global floor, or every loud frame of a
#            sustained chord counts as an onset and the head jitters.

import scd_conf as C
from scd_state import S


class Beat:
    def __init__(self):
        self.floor = 0
        self.peak = 1
        self.local = 0
        self.env = 0
        self.disp = 0             # eased display level: snaps up, drifts down
        self.last = -10000
        self.ibis = []

    def feed(self, rms, now):
        """One energy frame in; 0 (no beat) or an intensity 1..3 out.

        Side effects on S: level, bpm, ibi — this is the single writer.
        """
        self.env = rms if rms > self.env else (self.env * 3) >> 2

        if self.floor == 0:
            self.floor = rms
        elif rms < self.floor:
            self.floor += (rms - self.floor) // 4      # fall fast
        else:
            self.floor += 1                            # rise 1/frame, ~30/s

        if self.env > self.peak:
            self.peak = self.env
        else:
            self.peak -= (self.peak >> 7) + 1          # ~4 s half-life

        span = self.peak - self.floor
        raw = 0 if span <= 0 else (self.env - self.floor) * C.LEVEL_MAX // span
        if raw < 0:
            raw = 0
        elif raw > C.LEVEL_MAX:
            raw = C.LEVEL_MAX
        if raw > self.disp:
            self.disp += (raw - self.disp) // 2        # attack
        elif self.disp > 0:
            self.disp -= (self.disp - raw) // 6 + 1    # release
        S.level = self.disp

        # onset: audible over the floor AND a 1.5x jump on the near past —
        # and never while our own servos are whining into the microphone
        beat = 0
        local = self.local if self.local else 1
        if (rms > C.MIN_RMS and rms > self.floor * 2
                and rms * 2 > local * 3
                and now - self.last > C.REFRACT_MS
                and now >= S.servo_mask_until):
            gap = now - self.last
            self.last = now
            if C.IBI_MIN <= gap <= C.IBI_MAX:
                # fold into one octave so missed/doubled beats vote for the
                # same tempo instead of dragging the median to 64 or 256
                while gap < C.FOLD_MIN_MS:
                    gap *= 2
                while gap >= C.FOLD_MAX_MS:
                    gap //= 2
                self.ibis.append(gap)
                if len(self.ibis) > C.IBI_KEEP:
                    self.ibis.pop(0)
                srt = sorted(self.ibis)
                med = srt[len(srt) // 2]
                # the readout claims a tempo only once the votes agree
                agree = 0
                for v in self.ibis:
                    d = v - med if v > med else med - v
                    if d * 10 <= med:
                        agree += 1
                if agree >= 4:
                    S.ibi = med
                    S.bpm = 60000 // med
                else:
                    S.bpm = 0
            r = rms * 2 // local
            beat = 1 if r < 5 else (2 if r < 8 else 3)

        self.local += (rms - self.local) // 6          # updated AFTER judging
        return beat

    def quiet(self, now):
        """True once nothing beat-like has happened for SILENCE_MS."""
        return now - self.last > C.SILENCE_MS


B = Beat()
