"""Steady readout for a dashboard vital (heart rate, breathing rate).

The estimators underneath update every 2 s and, on a weak signal, can hop between spectral
peaks. A resting heart rate measured over a 30 s window cannot do that: it drifts by a few beats
per minute over several seconds. The stabilizer therefore

  * starts showing a value only after several readings agree (ACQUIRING until then);
  * follows readings that stay within `jump` of the shown value, smoothed (EMA), so the shown
    value moves at most alpha * jump per update;
  * holds the shown value and raises RAPID_CHANGE when a reading jumps further than that;
  * switches to the new level only when *accepted* readings (all quality checks passed) agree
    with each other for `confirm_n` updates in a row (CHANGED flag for `changed_s`). Readings that
    did not pass every check (tracker, microphone estimate) can never move the value by a jump: it
    stays held and flagged, and if they do not come back within `hold_s` the value is withdrawn
    and the card shows UNSTABLE until a new value is acquired. Scattering readings raise UNSTABLE;
  * keeps the last value for `hold_s` without new readings (HOLDING), then shows nothing
    (NO_SIGNAL).

Status labels change no faster than `dwell_s` (except flags, which are raised at once), so the
badge under the number does not flicker either.
"""
import numpy as np

# tier of the reading fed in: only 'accepted' passed every quality check. The tracker's own
# confidence ('tracked_high') was calibrated on simulations and is not trusted to show a value as
# STABLE or to confirm a jump on its own.
CONFIDENT = ('accepted', 'consensus_strong')
LOW = ('tracked_high', 'tracked_low', 'mic_estimate', 'consensus_weak')

CONSENSUS_TOL_BPM = 8.0       # a method within this of the consensus counts as agreeing
CONSENSUS_MIN = 3             # fewest agreeing methods for a value at all
STRONG_MIN = 4                # ... and for a confident (green) value, with STRONG_SHARE of the methods
STRONG_SHARE = 0.6


def robust_consensus(readings, tol=CONSENSUS_TOL_BPM):
    """Average of the methods that agree with each other.

    readings: [(name, hr or None)]. The median of all available values picks the majority; methods
    within `tol` of it are averaged, the average is re-centred once on those, and methods further
    away are excluded as outliers (a plain mean would be pulled by a single method that locked onto
    the wrong peak). Returns None without values, else dict(value, n, agree, used, excluded, spread,
    tier) where tier is consensus_strong / consensus_weak / None (no majority).
    """
    vals = [(n, float(v)) for n, v in readings if v is not None and np.isfinite(v)]
    if not vals:
        return None
    centre = float(np.median([v for _, v in vals]))
    for _ in range(2):
        used = [(n, v) for n, v in vals if abs(v - centre) <= tol]
        if not used:
            break
        centre = float(np.mean([v for _, v in used]))
    used = [(n, v) for n, v in vals if abs(v - centre) <= tol]
    n, a = len(vals), len(used)
    tier = None
    if a >= CONSENSUS_MIN and a / n >= 0.5:
        tier = 'consensus_strong' if a >= STRONG_MIN and a / n >= STRONG_SHARE else 'consensus_weak'
    return dict(value=round(float(np.mean([v for _, v in used])), 1) if used else None, n=n, agree=a,
                used=[x for x, _ in used], excluded=[x for x, v in vals if abs(v - centre) > tol],
                spread=round(float(np.ptp([v for _, v in used])), 1) if used else None, tier=tier,
                median=round(float(np.median([v for _, v in vals])), 1))

LABEL = {
    'NO_SIGNAL': 'NO SIGNAL',
    'ACQUIRING': 'ACQUIRING',
    'STABLE': 'STABLE',
    'LOW_CONFIDENCE': 'LOW CONFIDENCE',
    'HOLDING': 'HOLDING LAST VALUE',
    'RAPID_CHANGE': 'RAPID CHANGE - HELD',
    'UNSTABLE': 'UNSTABLE READING',
    'CHANGED': 'CHANGE CONFIRMED',
    'DISAGREE': 'METHODS DISAGREE',
}
LEVEL = {   # badge colour class in the UI
    'NO_SIGNAL': 'idle', 'ACQUIRING': 'idle', 'HOLDING': 'idle',
    'STABLE': 'ok', 'CHANGED': 'ok',
    'LOW_CONFIDENCE': 'warn',
    'RAPID_CHANGE': 'flag', 'UNSTABLE': 'flag', 'DISAGREE': 'flag',
}


class DisplayStabilizer:
    def __init__(self, jump=8.0, agree=5.0, start_n=3, confirm_n=4, alpha=0.3, hold_s=15.0,
                 changed_s=10.0, dwell_s=4.0, unstable_spread=10.0, window_n=6, lo=None, hi=None):
        self.jump, self.agree, self.start_n, self.confirm_n = jump, agree, start_n, confirm_n
        self.alpha, self.hold_s, self.changed_s, self.dwell_s = alpha, hold_s, changed_s, dwell_s
        self.unstable_spread, self.window_n, self.lo, self.hi = unstable_spread, window_n, lo, hi
        self.reset()

    def reset(self):
        self.value = None
        self.fresh_t = None
        self.recent = []            # (t, reading) that were in range of the shown value, or before a value existed
        self.pending = []           # (t, reading, tier) far from the shown value
        self.state, self.state_t = 'NO_SIGNAL', None
        self.changed_t, self.change = None, None
        self.tier = None
        self.last_reading = None
        self.withdrawn = False      # value dropped after readings jumped and never settled
        self.dispute = None

    # ------------------------------------------------------------------ update
    def update(self, reading, tier, now, dispute=None):
        """Feed one reading (None if there is none) with its tier; returns snapshot().

        dispute: text when an independent cross-check contradicts the reading (e.g. the other methods
        agree on a different heart rate). The reading is then not used: the shown value is held (as
        without a reading) and the card is flagged.
        """
        self.dispute = dispute if reading is not None else None
        if self.dispute:
            reading = None
        if reading is not None and (self.lo is not None and reading < self.lo or self.hi is not None and reading > self.hi):
            reading = None
        self.last_reading = reading
        flag = None
        if reading is None:
            if self.value is not None and self.fresh_t is not None and now - self.fresh_t > self.hold_s:
                disputed = self.dispute
                self.reset()
                if disputed:                              # readings exist but contradict: withdrawn, not "no signal"
                    self.withdrawn, self.dispute = True, disputed
            want = 'NO_SIGNAL' if self.value is None else 'HOLDING'
            if self.value is None and self.recent:
                want = 'ACQUIRING'
            if self.value is None and self.withdrawn:
                want = 'UNSTABLE'
            if self.dispute:
                want = flag = 'DISAGREE'
        else:
            self.tier = tier
            if self.value is None:
                self._acquire(reading, now)
                if self.value is not None:
                    self.withdrawn = False
                want = ('UNSTABLE' if self.withdrawn else 'ACQUIRING') if self.value is None else self._quality_state()
            elif abs(reading - self.value) <= self.jump:
                self.pending = []
                self.value = (1 - self.alpha) * self.value + self.alpha * reading
                self.fresh_t = now
                self.recent = (self.recent + [(now, reading)])[-self.window_n:]
                want = self._quality_state()
            else:
                self.pending = (self.pending + [(now, reading, tier)])[-self.confirm_n:]
                vals = np.array([v for _, v, _ in self.pending])
                med = float(np.median(vals))
                all_accepted = all(tr in CONFIDENT for _, _, tr in self.pending)
                if len(vals) == self.confirm_n and all_accepted and np.all(np.abs(vals - med) <= self.agree):
                    self.change = med - self.value         # a sustained, consistent new level: accept it
                    self.value, self.fresh_t, self.changed_t = med, now, now
                    self.recent, self.pending = [(t, v) for t, v, _ in self.pending], []
                    want = 'CHANGED'
                else:
                    flag = 'UNSTABLE' if len(vals) >= 3 and np.ptp(vals) > self.unstable_spread else 'RAPID_CHANGE'
                    want = flag
                    if self.fresh_t is not None and now - self.fresh_t > self.hold_s:
                        self.reset()                      # never confirmed and nothing in range for hold_s
                        self.withdrawn = True
                        want = 'UNSTABLE'
        if self.value is not None and reading is not None and want in ('STABLE', 'LOW_CONFIDENCE') and \
                len(self.recent) >= 3 and np.ptp([v for _, v in self.recent]) > self.unstable_spread:
            want = flag = 'UNSTABLE'
        if want not in ('RAPID_CHANGE', 'UNSTABLE', 'CHANGED') and self.changed_t is not None \
                and now - self.changed_t < self.changed_s:
            want = 'CHANGED'                              # keep the confirmation visible for changed_s
        self._set_state(want, now, immediate=flag is not None or want in ('CHANGED', 'NO_SIGNAL', 'ACQUIRING'))
        return self.snapshot(now)

    def _acquire(self, reading, now):
        need = 2 * self.start_n if self.withdrawn else self.start_n   # after a withdrawal, ask for twice the evidence
        self.recent = (self.recent + [(now, reading)])[-need:]
        vals = np.array([v for _, v in self.recent])
        med = float(np.median(vals))
        if len(vals) == need and np.all(np.abs(vals - med) <= self.agree):
            self.value, self.fresh_t = med, now

    def _quality_state(self):
        return 'STABLE' if self.tier in CONFIDENT else 'LOW_CONFIDENCE'

    def _set_state(self, want, now, immediate):
        if want == self.state:
            return
        if immediate or self.state_t is None or now - self.state_t >= self.dwell_s \
                or self.state in ('NO_SIGNAL', 'ACQUIRING', 'RAPID_CHANGE', 'UNSTABLE', 'CHANGED', 'HOLDING', 'DISAGREE'):
            self.state, self.state_t = want, now

    # ------------------------------------------------------------------ output
    def snapshot(self, now):
        held = None if self.fresh_t is None or self.value is None else round(now - self.fresh_t, 1)
        detail = {
            'NO_SIGNAL': 'No reading yet.',
            'ACQUIRING': f'Waiting for {self.start_n} readings that agree within +-{self.agree:.0f}.',
            'STABLE': 'Readings agree and pass the quality checks.',
            'LOW_CONFIDENCE': 'Best estimate from a weak signal; readings are steady but did not pass every check.',
            'HOLDING': f'No new reading for {held} s; last value kept for up to {self.hold_s:.0f} s.',
            'RAPID_CHANGE': (f'Latest reading {self.last_reading:.0f} differs from the shown value by more than '
                             f'{self.jump:.0f}; value held until {self.confirm_n} readings in a row agree.')
            if self.last_reading is not None and self.value is not None else 'Value held.',
            'UNSTABLE': ('Readings jumped and did not settle, so the value was withdrawn; a new value is shown '
                         f'once {2 * self.start_n} readings in a row agree.') if self.value is None else
                        'Readings scatter widely: the signal is not reliable now (movement, lighting).',
            'DISAGREE': (self.dispute or 'Other methods disagree with this reading.') +
                        (' Last value held.' if self.value is not None else ' No value shown.'),
            'CHANGED': (f'New level confirmed by {self.confirm_n} agreeing readings '
                        f'({self.change:+.0f} from before).') if self.change is not None else 'New level confirmed.',
        }[self.state]
        return dict(value=None if self.value is None else round(self.value, 1), state=self.state,
                    label=LABEL[self.state], level=LEVEL[self.state], detail=detail, tier=self.tier,
                    held_s=held, reading=None if self.last_reading is None else round(self.last_reading, 1))
