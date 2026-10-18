"""Closed-loop camera exposure from skin brightness.

The camera's own auto exposure meters the whole frame, so a dark background or a lamp on
the face drives the skin into clipping (no pulse left in saturated pixels) or into the
noise floor. This controller meters only the skin boxes the node sums, using the per-frame
counts of usable, saturated and near-black pixels the node reports, and asks the node for
a new manual exposure until the skin sits mid-range. Exposure is changed rarely and in one
proportional step; each change restarts the pulse analysis segment (see usb_streamer).
"""
import time

TARGET_LEVEL = 165.0      # brightest-channel mean of usable skin pixels (8-bit scale; RGB565 tops out at 248)
LEVEL_BAND = (115.0, 205.0)   # no change while the level is inside this band and clipping is low
MAX_CLIP = 0.02           # share of skin pixels allowed to be saturated
MAX_DARK = 0.10           # share of skin pixels allowed to be near-black
EVAL_S = 1.0              # metering window
SETTLE_S = 0.6            # ignore frames this long after a change (the sensor applies it over 1-2 frames)
MIN_INTERVAL_S = 3.0      # at most one change per this many seconds
STEP_LIMITS = (0.35, 2.5) # largest decrease / increase per change
EXP_LIMITS = (4, 880)     # GC2145 rows. Measured capture rate: 10.2 fps at 800 rows, 7.5 at 1200, 3.7 at 2400
                          # (frame period ~0.11 ms per row), so 880 is the longest exposure that keeps 10 fps.
GAMMA = 0.45              # measured on the node: brightness ~ exposure**0.45 (100->67, 400->137, 1600->216)


class ExposureController:
    def __init__(self, send, now=time.time):
        self.send = send              # callable(int) -> bool, sends <<CAM:EXP,n>>
        self.now = now
        self.exposure = None          # last value read back from the node
        self.pending = None           # value requested, not yet confirmed
        self.last_change = -1e9
        self.ignore_until = -1e9
        self._reset_window()
        self.state = dict(level=None, clip=None, dark=None, exposure=None, action='waiting')

    def _reset_window(self):
        self.w_start = None
        self.n = self.clip = self.dark = 0
        self.level_sum = 0.0

    def readback(self, exposure):
        """Exposure confirmed by the node (<<CAMEXP>> or <<INFO:...exp=>>). Returns True if it changed."""
        changed = self.exposure is not None and exposure != self.exposure
        self.exposure = exposure
        self.state['exposure'] = exposure
        if self.pending is not None and exposure == self.pending:
            self.pending = None
        elif self.pending is not None and self.now() - self.last_change > 3.0:
            self.pending = None               # never confirmed (e.g. link dropped): allow a new request
        if changed:
            self.ignore_until = self.now() + SETTLE_S
            self._reset_window()
        return changed

    def add(self, n, rgb, nclip, ndark):
        """One frame's skin statistics. Returns the exposure requested, or None."""
        t = self.now()
        if t < self.ignore_until or self.exposure is None:
            return None
        if self.w_start is None:
            self.w_start = t
        self.n += n
        self.clip += nclip
        self.dark += ndark
        if n and rgb is not None:
            self.level_sum += n * max(rgb)
        if t - self.w_start < EVAL_S:
            return None
        return self._evaluate(t)

    def _evaluate(self, t):
        total = self.n + self.clip + self.dark
        if total == 0:
            self._reset_window()
            return None
        clip, dark = self.clip / total, self.dark / total
        level = self.level_sum / self.n if self.n else (255.0 if self.clip >= self.dark else 0.0)
        self.state.update(level=round(level, 1), clip=round(clip, 3), dark=round(dark, 3), metered_at=t)
        self._reset_window()

        lo, hi = LEVEL_BAND
        if clip > MAX_CLIP:
            # Clipped pixels hide how bright the skin really is: step down harder the more is clipped.
            scale = STEP_LIMITS[0] if clip > 0.5 else min((TARGET_LEVEL / max(level, 1.0)) ** (1 / GAMMA), 0.7)
            action = 'darker (clipping)'
        elif level > hi:
            scale, action = (TARGET_LEVEL / level) ** (1 / GAMMA), 'darker'
        elif level < lo or dark > MAX_DARK:
            scale, action = (TARGET_LEVEL / max(level, 10.0)) ** (1 / GAMMA), 'brighter'
        else:
            self.state['action'] = 'ok'
            return None
        if self.pending is not None or t - self.last_change < MIN_INTERVAL_S:
            self.state['action'] = action + ' (waiting)'
            return None
        scale = min(max(scale, STEP_LIMITS[0]), STEP_LIMITS[1])
        new = int(round(min(max(self.exposure * scale, EXP_LIMITS[0]), EXP_LIMITS[1])))
        if abs(new - self.exposure) < max(2, 0.05 * self.exposure):
            self.state['action'] = action + (' (needs more light)' if action == 'brighter' else ' (at limit)')
            return None
        if self.send(new):
            self.pending = new
            self.last_change = t
            self.state['action'] = action
            return new
        return None
