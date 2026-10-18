"""Acoustic (INMP441) engine: reassembles timestamped PCM blocks from the edge
node, runs the PCG branch of `vitals_dsp` once per second, keeps S1 beat times
for RMSSD, and prepares a spectrogram for display.
"""
import threading
import time

import numpy as np
from scipy.signal import stft

import vitals_dsp as dsp


class AcousticEngine:
    def __init__(self, fs=dsp.FS_AUDIO, block=256, buffer_s=12.0, analysis_s=10.0,
                 update_interval_s=1.0, rms_floor=30.0):
        self.fs = int(fs)
        self.block = block                  # updated from the length of received blocks
        self.buffer_len = int(buffer_s * fs)
        self.analysis_len = int(analysis_s * fs)
        self.update_interval_s = update_interval_s
        self.rms_floor = rms_floor          # int16 counts after band-pass; below this the mic is treated as silent

        self._lock = threading.Lock()
        self.buf = np.zeros(self.buffer_len, dtype=np.int16)
        self.filled = 0
        self.t_last_sample = None           # device time (s) of the newest sample
        self.next_seq = None
        self.blocks_received = 0
        self.blocks_lost = 0
        self.last_block_host_time = 0.0

        self.beats = np.array([])           # absolute S1 times (device clock, s)
        self.result = dict(hr=None, rho=0.0, rms=0.0, rmssd=None, beats_in_window=0)
        self._last_update = 0.0

    # ------------------------------------------------------------ ingest
    def add_block(self, seq, t_us, pcm):
        """Append one block. Missing sequence numbers are filled with zeros so the
        sample clock stays continuous."""
        pcm = np.asarray(pcm, dtype=np.int16)
        self.block = len(pcm)
        with self._lock:
            if self.next_seq is not None and seq > self.next_seq:
                missing = min(seq - self.next_seq, self.buffer_len // self.block)
                self.blocks_lost += missing
                self._append(np.zeros(missing * self.block, dtype=np.int16))
            elif self.next_seq is not None and seq < self.next_seq:
                self.reset_locked()                       # device restarted
            self.next_seq = seq + 1
            self._append(pcm)
            self.t_last_sample = t_us / 1e6 + (len(pcm) - 1) / self.fs
            self.blocks_received += 1
            self.last_block_host_time = time.time()

    def _append(self, x):
        n = len(x)
        if n >= self.buffer_len:
            self.buf[:] = x[-self.buffer_len:]
        else:
            self.buf = np.roll(self.buf, -n)
            self.buf[-n:] = x
        self.filled = min(self.buffer_len, self.filled + n)

    def reset_locked(self):
        self.buf[:] = 0
        self.filled = 0
        self.next_seq = None
        self.beats = np.array([])

    def connected(self, timeout_s=2.0):
        return time.time() - self.last_block_host_time < timeout_s

    # ------------------------------------------------------------ analysis
    def recent(self, seconds):
        n = min(self.filled, int(seconds * self.fs))
        with self._lock:
            return self.buf[-n:].copy() if n else np.array([], dtype=np.int16), self.t_last_sample

    def update(self, force=False):
        now = time.time()
        if not force and now - self._last_update < self.update_interval_s:
            return self.result
        self._last_update = now
        if not self.connected():
            self.result = dict(hr=None, rho=0.0, rms=0.0, rmssd=None, beats_in_window=0)
            return self.result

        x, t_last = self.recent(self.analysis_len / self.fs)
        if len(x) < 3 * self.fs or t_last is None:
            return self.result
        t0 = t_last - (len(x) - 1) / self.fs
        est = dsp.estimate_acoustic(x, t0=t0, fs=self.fs)

        # Merge new beats, ignoring any within 0.2 s of a beat already stored. Beats in
        # the first/last 0.5 s of the window are skipped: filtering and truncated sounds
        # bias their timing, and the overlapping next window finds them in its interior.
        new = est['beats']
        new = new[(new >= t0 + 0.5) & (new <= t_last - 0.5)]
        if len(self.beats):
            new = np.array([b for b in new if np.min(np.abs(self.beats - b)) > 0.2])
        beats = np.sort(np.concatenate([self.beats, new])) if len(new) else self.beats
        self.beats = beats[beats >= t_last - 60.0]

        band_rms = float(np.std(est['x1k'])) if len(est['x1k']) else 0.0
        audible = band_rms > self.rms_floor
        rhythmic = est['rho'] >= dsp.MIN_RHO_ACOUSTIC and est['beat_consistency'] >= dsp.MIN_BEAT_CONSISTENCY
        self.result = dict(
            hr=est['hr'] if audible and rhythmic else None,
            hr_estimate=est['hr'] if audible else None,      # before the rhythm gate (low confidence)
            audible=bool(audible),
            rho=est['rho'] if audible else 0.0,
            rms=band_rms,
            rmssd=dsp.rmssd_ms(self.beats) if audible else None,
            beats_in_window=int(len(self.beats)),
            beat_consistency=round(est['beat_consistency'], 2),
        )
        return self.result

    # ------------------------------------------------------------ display
    def display_payload(self, seconds=4.0, n_points=600, n_cols=60, f_max=2000.0):
        """Band-passed PCG trace (min/max decimated) and a dB spectrogram for the UI."""
        x, _ = self.recent(seconds)
        payload = dict(connected=self.connected(), wave=[], wave_seconds=seconds,
                       spec=[], spec_freqs=[], spec_seconds=seconds,
                       blocks_received=self.blocks_received, blocks_lost=self.blocks_lost)
        if len(x) < self.fs:
            return payload
        x1k, _, _ = dsp.pcg_envelope(x, self.fs)
        if len(x1k) >= 2 * n_points:
            k = len(x1k) // n_points
            seg = x1k[:k * n_points].reshape(n_points, k)
            wave = np.where(np.arange(n_points) % 2 == 0, seg.max(axis=1), seg.min(axis=1))
        else:
            wave = x1k
        scale = np.max(np.abs(wave)) or 1.0
        payload['wave'] = [round(float(v / scale), 3) for v in wave]

        nper = 512 if self.fs >= 16000 else max(64, int(0.032 * self.fs))   # ~32 ms windows
        f, _, Z = stft(x.astype(float), fs=self.fs, window='hamming', nperseg=nper, noverlap=3 * nper // 4)
        keep = f <= f_max
        S = 20 * np.log10(np.abs(Z[keep]) + 1e-6)
        cols = np.array_split(np.arange(S.shape[1]), n_cols)
        S = np.column_stack([S[:, c].mean(axis=1) for c in cols if len(c)])
        S = S - np.max(S)
        payload['spec'] = np.round(S, 1).tolist()
        payload['spec_freqs'] = [round(float(v), 1) for v in f[keep]]
        return payload
