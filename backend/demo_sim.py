"""Labelled demo mode (user-approved 2026-10-22).

For demonstrations while the chest microphone cannot find a heart rhythm (rho < 0.4), the dashboard
can show what the system looks like when it works:

  * the microphone graph and spectrogram show a normal heart-sound pattern (S1/S2) timed at the
    camera heart rate shown on the card (72 BPM if there is none);
  * the SpO2 and HRV cards show typical resting values (SpO2 96-99 %, RMSSD 30-55 ms).

Everything produced here is SIMULATED and is marked so on every screen element that shows it. It is
returned in separate fields (`demo` in /api/vitals, `simulated` in /api/audio) and never written into
the measured fields (spo2, hrv, acoustic_*), the heart-rate consensus, the OLED or the session
recordings. When the real microphone finds a rhythm (rho >= 0.4) the real graph is shown again.
"""
import threading
import time

import numpy as np

SPO2_RANGE = (96.0, 99.0)
RMSSD_RANGE_MS = (30.0, 55.0)
DEFAULT_HR = 72.0


class DemoMode:
    def __init__(self, seed=None):
        self.enabled = False
        self._lock = threading.Lock()
        self._rng = np.random.default_rng(seed)
        self._spo2 = 97.5
        self._rmssd = 42.0
        self._t = None

    def set(self, enabled):
        with self._lock:
            self.enabled = bool(enabled)
            self._t = None

    def values(self, now=None):
        """Slowly wandering typical values (a bounded random walk, updated at most every 2 s)."""
        now = time.time() if now is None else now
        with self._lock:
            if self._t is None or now - self._t >= 2.0:
                self._spo2 = float(np.clip(self._spo2 + self._rng.normal(0, 0.15), *SPO2_RANGE))
                self._rmssd = float(np.clip(self._rmssd + self._rng.normal(0, 1.2), *RMSSD_RANGE_MS))
                self._t = now
            return dict(spo2=round(self._spo2, 1), hrv=round(self._rmssd, 1))


def heart_sound_pattern(hr_bpm, seconds, fs, t_end=None):
    """Normal phonocardiogram pattern ending at wall-clock t_end (so successive polls scroll).

    Each beat: S1 (about 0.10 s, 40-90 Hz) then S2 about 0.30 s later (about 0.08 s, 60-120 Hz,
    softer), on a little background noise. Beat k starts at k * 60 / hr seconds of wall-clock time.
    """
    hr = float(hr_bpm) if hr_bpm and 40 <= hr_bpm <= 180 else DEFAULT_HR
    t_end = time.time() if t_end is None else t_end
    n = int(seconds * fs)
    t = t_end - (n - 1 - np.arange(n)) / fs
    period = 60.0 / hr
    systole = min(0.33, 0.38 * period)            # S1-S2 interval shortens a little at high rates
    x = 0.02 * np.random.default_rng(int(t_end * 10) % 2**32).standard_normal(n)
    first = int(np.floor(t[0] / period)) - 1
    for k in range(first, int(np.ceil(t[-1] / period)) + 1):
        for onset, dur, freqs, amp in ((k * period, 0.10, (45.0, 70.0, 90.0), 1.0),
                                       (k * period + systole, 0.08, (65.0, 95.0, 120.0), 0.6)):
            m = (t >= onset) & (t < onset + dur)
            if not m.any():
                continue
            tau = t[m] - onset
            win = np.sin(np.pi * tau / dur) ** 2
            x[m] += amp * win * sum(np.sin(2 * np.pi * f * tau) / (i + 1) for i, f in enumerate(freqs))
    return (x / np.max(np.abs(x)) * 8000.0).astype(np.int16)
