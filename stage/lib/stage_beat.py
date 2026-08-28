# Beat tracking over a stream of frame energies — the stage node's ear,
# upgraded from "packets arrived" to "I can hear the tempo".
#
# This is dance's scd_beat (vendor/op-cp/dance/lib/scd_beat.py) made
# standalone: same three references, same octave fold, same median vote,
# with the module globals and state object replaced by a class so the host
# harness can run several trackers side by side while tuning. The logic is
# deliberately byte-comparable to the original; divergences are bugs.
#
# Pure integers, no hardware imports: the conformance suite and the tuning
# harness feed it synthetic or recorded energy sequences and assert on the
# beats that come out, on the device and on the host alike.
#
# Three references, three jobs:
#   floor — the QUIET reference. Falls quickly, rises one unit a frame, so
#           sustained music cannot drag it up to its own average.
#   peak  — a decaying maximum: the level self-normalises to this track at
#           this volume and distance, whatever they are.
#   local — a short EMA of the near past; a beat is a jump against it, not
#           against the global floor.

REFRACT_MS = 200         # two beats can't be closer than this (300 bpm on
                         # the eighth grid). The original's 130 let a kick
                         # re-trigger on its own tail ~160 ms after the
                         # attack — read straight off mic.gaps at a true
                         # 100 bpm: a periodic (160, 448) pair where a flat
                         # 300 should be. Fast tempos masked the ghost with
                         # the next real hit, slow ones exposed it.
IBI_MIN = 170            # gaps under this are noise — 170 admits the
                         # eighth-note hits of a 140 bpm pattern (214 ms),
                         # which the original's 240 silently discarded, so
                         # fast tempos starved and read as "no tempo"
IBI_MAX = 1500           # gaps above this are silence, not tempo
ONSETS_KEEP = 24         # onset times kept for the precise estimator
FOLD_MIN_MS = 375        # fold gaps into one octave: 80..160 bpm, so missed
FOLD_MAX_MS = 750        # and doubled beats vote for the SAME tempo
KEEP = 6                 # votes kept
AGREE = 4                # votes within 10% of the median before a claim
SILENCE_MS = 2600
LEVEL_MAX = 255


class BeatTracker:
    def __init__(self, min_rms):
        self.min_rms = min_rms
        self.floor = 0
        self.peak = 1
        self.local = 0
        self.env = 0
        self.disp = 0
        self.last = -10000
        self.ibis = []
        self.bpm = 0             # 0 = no stable tempo yet
        self.ibi = 500
        self.level = 0
        self.beats = 0           # onsets seen since boot — the heartbeat
        self.evidence = 0        # gaps behind the last precise fit
        self.onsets = []         # recent onset times, for precise_bpm()

    def feed(self, rms, now):
        """One energy frame in; 0 (no beat) or an intensity 1..3 out."""
        self.env = rms if rms > self.env else (self.env * 3) >> 2

        if self.floor == 0:
            self.floor = rms
        elif rms < self.floor:
            self.floor += (rms - self.floor) // 4      # fall fast
        else:
            self.floor += 1                            # rise 1/frame

        if self.env > self.peak:
            self.peak = self.env
        else:
            self.peak -= (self.peak >> 7) + 1          # ~4 s half-life

        span = self.peak - self.floor
        raw = 0 if span <= 0 else (self.env - self.floor) * LEVEL_MAX // span
        raw = 0 if raw < 0 else (LEVEL_MAX if raw > LEVEL_MAX else raw)
        if raw > self.disp:
            self.disp += (raw - self.disp) // 2        # attack
        elif self.disp > 0:
            self.disp -= (self.disp - raw) // 6 + 1    # release
        self.level = self.disp

        beat = 0
        local = self.local if self.local else 1
        if (rms > self.min_rms and rms > self.floor * 2
                and rms * 2 > local * 3
                and now - self.last > REFRACT_MS):
            gap = now - self.last
            self.last = now
            self.beats += 1
            self.onsets.append(now)
            if len(self.onsets) > ONSETS_KEEP:
                self.onsets.pop(0)
            if IBI_MIN <= gap <= IBI_MAX:
                while gap < FOLD_MIN_MS:
                    gap *= 2
                while gap >= FOLD_MAX_MS:
                    gap //= 2
                self.ibis.append(gap)
                if len(self.ibis) > KEEP:
                    self.ibis.pop(0)
                srt = sorted(self.ibis)
                med = srt[len(srt) // 2]
                agree = 0
                for v in self.ibis:
                    d = v - med if v > med else med - v
                    if d * 10 <= med:
                        agree += 1
                if agree >= AGREE:
                    self.ibi = med
                    self.bpm = 60000 // med
                else:
                    self.bpm = 0           # honest: the votes disagree
            r = rms * 2 // local
            beat = 1 if r < 5 else (2 if r < 8 else 3)

        self.local += (rms - self.local) // 6          # updated AFTER judging
        return beat

    def precise_bpm(self):
        """Tempo from the whole onset train, not from single gaps.

        One gap is quantised by the ~32 ms frame clock — ±7% at 140 bpm,
        which is the difference between a reading and a guess. Fitting the
        train to a grid divides that error by the number of beats spanned:
        find the fundamental spacing (median of recent gaps), count how many
        grid units each gap spans, and divide total time by total units.
        Gaps that sit between grid lines (a missed beat's 1.5x, syncopation)
        are simply left out of the fit rather than voting wrongly.

        Returns 0 until there is enough agreeing evidence — same honesty
        contract as .bpm, roughly ±1-2 bpm once it speaks.
        """
        self.evidence = 0
        if len(self.onsets) < 5:
            return 0
        gaps = []
        for i in range(1, len(self.onsets)):
            g = self.onsets[i] - self.onsets[i - 1]
            if IBI_MIN <= g <= IBI_MAX:
                gaps.append(g)
        if len(gaps) < 4:
            return 0
        grid = sorted(gaps)[len(gaps) // 2]
        total_t = 0
        total_k = 0
        for g in gaps:
            k = (g + grid // 2) // grid            # round(g / grid)
            if 1 <= k <= 4 and abs(g - k * grid) * 5 <= grid:
                total_t += g
                total_k += k
        if total_k < 4 or total_t == 0:
            return 0
        self.evidence = len([g for g in gaps
                             if 1 <= (g + grid // 2) // grid <= 4])
        bpm = 60000 * total_k // total_t
        # the grid may be the eighth-note layer; fold to the 80..160 octave
        # the coarse voter uses, so the two readouts are comparable
        while bpm >= 160:
            bpm //= 2
        while bpm < 80:
            bpm *= 2
        return bpm

    def quiet(self, now):
        return now - self.last > SILENCE_MS
