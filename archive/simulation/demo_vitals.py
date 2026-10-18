"""Demo-values mode: live camera and face detection, simulated vital signs.

Enabled only with SONICVITALS_DEMO_VITALS=1 (tools/demo_live.sh). The camera stream,
face detection and face gate stay live; the vital-sign values and waveforms come from
synthetic physiology run through the real DSP code. Every API response carries
demo_vitals=True and the dashboard shows a DEMO VALUES banner. Demo values are never
written to session recordings or sent to the OLED.

Behaviour: after a face has passed the gate for CALIBRATION_S, values appear; if no
face is seen for RESET_AFTER_S, everything resets and the next face starts a new
calibration with a new simulated baseline.
"""
import threading
import time

import numpy as np

import vitals_dsp as dsp
from acoustic_engine import AcousticEngine

CALIBRATION_S = 30.0
RESET_AFTER_S = 5.0
FS_RGB = 10.0
FS_AUDIO = 4000


class _Heart:
    """Beat schedule with a slowly drifting mean rate, respiratory sinus arrhythmia and jitter."""

    def __init__(self, rng, hr, rr):
        self.rng, self.hr, self.rr = rng, hr, rr
        self.beats = [0.0]

    def extend(self, until):
        while self.beats[-1] < until + 2.0:
            t = self.beats[-1]
            rsa = 0.04 * np.sin(2 * np.pi * self.rr / 60.0 * t)
            self.beats.append(t + 60.0 / self.hr * (1 + rsa) + self.rng.normal(0, 0.012))
        if len(self.beats) > 400:
            self.beats = self.beats[-300:]

    def phase(self, t):
        self.extend(t)
        b = np.asarray(self.beats)
        k = np.clip(np.searchsorted(b, t, side='right') - 1, 0, len(b) - 2)
        return np.clip((t - b[k]) / (b[k + 1] - b[k]), 0, 1)

    def pcg(self, t0, n, fs):
        t = t0 + np.arange(n) / fs
        self.extend(t[-1])
        x = np.zeros(n)
        for b0, b1 in zip(self.beats[:-1], self.beats[1:]):
            if b0 > t[-1] or b1 < t[0] - 1.0:
                continue
            for off, amp, f in [(0.0, 1.0, 60.0), (0.3 * (b1 - b0), 0.6, 90.0)]:
                m = (t >= b0 + off) & (t < b0 + off + 0.08)
                u = t[m] - b0 - off
                x[m] += amp * np.sin(2 * np.pi * f * u) * np.sin(np.pi * u / 0.08)
        x = 3000 * x + 150 * self.rng.standard_normal(n)
        return np.clip(x, -32768, 32767).astype('<i2')


class DemoVitals:
    def __init__(self, face_state, update_s=0.5):
        """face_state() -> (patient_detected, full_face_visible) from the live optical engine."""
        self.face_state = face_state
        self.update_s = update_s
        self.rng = np.random.default_rng()
        self.lock = threading.Lock()
        self._reset()
        threading.Thread(target=self._run, daemon=True).start()

    # ------------------------------------------------------------ state
    def _reset(self):
        self.face_since = None
        self.last_face = None
        self.heart = None
        self.t_sim = 0.0
        self.t_rgb, self.rgb = [], []
        self.acoustic = AcousticEngine(fs=FS_AUDIO)
        self.audio_seq = 0
        self.spo2 = None
        self.optical = dsp.estimate_optical([], np.empty((0, 3)))
        self.display = {}

    def _start_person(self):
        r = self.rng
        self.base_hr = r.uniform(66, 84)
        self.base_rr = r.uniform(12.5, 17.0)
        self.heart = _Heart(r, self.base_hr, self.base_rr)
        self.spo2 = r.uniform(96.5, 98.5)
        self.display = {}

    def _step(self, dt):
        r, h = self.rng, self.heart
        # slow drifts (Ornstein-Uhlenbeck) so values move like a real reading
        h.hr += 0.08 * (self.base_hr - h.hr) * dt + 0.6 * np.sqrt(dt) * r.standard_normal()
        h.rr += 0.05 * (self.base_rr - h.rr) * dt + 0.08 * np.sqrt(dt) * r.standard_normal()
        self.spo2 = float(np.clip(self.spo2 + 0.05 * np.sqrt(dt) * r.standard_normal(), 95.5, 99.2))
        t1 = self.t_sim + dt
        # skin colour at 10 Hz: pulse (green strongest), breathing-borne illumination, sensor noise
        for t in np.arange(self.t_sim, t1, 1.0 / FS_RGB):
            ph = h.phase(t)
            pulse = np.exp(-((ph - 0.15) / 0.08) ** 2) + 0.35 * np.exp(-((ph - 0.45) / 0.1) ** 2)
            illum = 1 + 0.006 * np.sin(2 * np.pi * h.rr / 60.0 * t)
            rgb = np.array([180.0, 120.0, 100.0]) * illum * (1 - 0.01 * pulse * np.array([0.33, 0.77, 0.53]))
            self.t_rgb.append(t)
            self.rgb.append(rgb + 0.08 * r.standard_normal(3))
        while self.t_rgb and self.t_rgb[-1] - self.t_rgb[0] > 30.0:
            self.t_rgb.pop(0)
            self.rgb.pop(0)
        # heart sounds at 4 kHz in 256-sample blocks
        n0 = int(self.t_sim * FS_AUDIO) // 256 * 256
        for s0 in range(n0, int(t1 * FS_AUDIO) - 255, 256):
            if s0 < self.audio_seq * 256:
                continue
            self.acoustic.add_block(self.audio_seq, int(s0 / FS_AUDIO * 1e6), h.pcg(s0 / FS_AUDIO, 256, FS_AUDIO))
            self.audio_seq += 1
        self.t_sim = t1

    def _run(self):
        last = time.time()
        while True:
            time.sleep(self.update_s)
            now = time.time()
            dt, last = now - last, now
            detected, visible = self.face_state()
            with self.lock:
                if visible:
                    self.last_face = now
                    if self.face_since is None:
                        self.face_since = now
                        self._start_person()
                if self.last_face is not None and now - self.last_face > RESET_AFTER_S:
                    self._reset()
                    continue
                if self.heart is None:
                    continue
                self._step(dt)
                self.acoustic.update()
                prior = self.display.get('hr')
                self.optical = dsp.estimate_optical(np.array(self.t_rgb), np.array(self.rgb), fs=dsp.FS_OPT,
                                                    prior_hr=prior)
                self._update_display()

    def _update_display(self):
        o, a = self.optical, self.acoustic.result
        w_o = o['quality'] if o['hr_ok'] else 0.0
        w_a = a['rho'] if a['hr'] is not None else 0.0
        fused = dsp.fuse_hr(o['hr'], w_o, a['hr'], w_a)
        d = self.display

        def ema(key, v, alpha=0.3):
            if v is not None:
                d[key] = v if d.get(key) is None else (1 - alpha) * d[key] + alpha * v
        ema('hr', fused['hr'])
        ema('rr', o['rr'])
        ema('hrv', a['rmssd'])
        d.update(fused=fused, q=max(fused['w_o'], fused['w_a']))

    # ------------------------------------------------------------ API
    def vitals(self):
        """Fields that override /api/vitals in demo mode."""
        now = time.time()
        with self.lock:
            out = {'demo_vitals': True}
            if self.face_since is None:
                return out
            elapsed = now - self.face_since
            o, a, d = self.optical, self.acoustic.result, self.display
            if elapsed < CALIBRATION_S:
                out.update(status='CALIBRATING', calibrating=True,
                           calibration_progress=int(100 * elapsed / CALIBRATION_S),
                           calibration_remaining_sec=int(round(CALIBRATION_S - elapsed)),
                           hr=None, rr=None, hrv=None, spo2=None, quality=None, fusion_source=None,
                           optical_hr=None, acoustic_hr=None, hr_age_s=None, rr_age_s=None)
                return out
            fused = d.get('fused', {})
            disp = (o['freqs'] >= 0.5) & (o['freqs'] <= 3.5) if len(o['freqs']) else np.array([], bool)
            psd_db = 10 * np.log10(np.maximum(o['psd'][disp], 1e-12)) if np.any(disp) else np.array([])
            if len(psd_db):
                psd_db = psd_db - np.max(psd_db)
            tail = lambda x: [round(float(v), 4) for v in np.asarray(x)[-int(10 * dsp.FS_OPT):]]
            r1 = lambda v, n=1: None if v is None else round(float(v), n)
            out.update(
                status='STABLE', calibrating=False, calibration_progress=100, calibration_remaining_sec=0,
                segment_seconds=r1(o['segment_s']), optical_hr=r1(o['hr']), optical_hr_ok=bool(o['hr_ok']),
                cardiac_peak_freq=r1(o['f0'], 3), cardiac_snr=r1(o['snr']), optical_quality=r1(o['quality'], 3),
                optical_rr=r1(o['rr']), rr_quality=r1(o['rr_quality'], 3),
                hr=r1(d.get('hr')), rr=r1(d.get('rr')), hrv=r1(d.get('hrv')),
                spo2=r1(self.spo2), spo2_estimate=r1(self.spo2), spo2_ratio=r1((110 - self.spo2) / 25, 4),
                quality=r1(100 * d.get('q', 0.0)), fusion_hr=r1(fused.get('hr')),
                fusion_source=fused.get('source'), fusion_disagreement=bool(fused.get('disagreement')),
                acoustic_hr=r1(a['hr']), acoustic_rho=r1(a['rho'], 3), hr_age_s=0.0, rr_age_s=0.0,
                psd_freqs=[round(float(f), 3) for f in o['freqs'][disp]] if np.any(disp) else [],
                psd_power=[round(float(p), 1) for p in psd_db],
                bvp_wave=tail(o['bvp']), resp_wave=tail(o['resp']), trend_wave=tail(o['trend']),
                pulsatile_wave=tail(o['pulsatile']), diff_wave=tail(o['diff']),
                motion_ratio=r1(o['motion_ratio'], 2),
            )
            return out

    def audio(self):
        """Overrides /api/audio in demo mode."""
        with self.lock:
            p = self.acoustic.display_payload()
            p.update(self.acoustic.result)
            p.update(connected=True, demo_vitals=True, blocks_lost=0)
            return p
