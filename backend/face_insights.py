"""Face insights from the same camera video as the pulse: blood-flow (perfusion) map, perfusion index per
region, liveness (a live face pulses), blink rate and head steadiness.

Works for both cameras. The spatial measurements use the video frames (Mac webcam ~30 fps, ESP32-S3 JPEG
~5 fps): the face box (motion-compensated, so each cell stays on the same skin) is reduced to a GRID x GRID
grid of cell means, and the pulse in every cell is measured by lock-in detection at the heart rate shown on
the card (a narrowband measurement, so it works at 5 fps and with weak per-cell signals).

  * Perfusion map (after Kamshilin et al., Sci Rep 2011, "photoplethysmographic imaging"): per skin cell, the
    pulse amplitude at the heart rate as a perfusion index, shown only where the pulse stands out from the
    cell's own noise (lock-in amplitude at f0 >= CELL_SNR x the median at other frequencies).
  * Perfusion index (PI): peak-to-peak green pulse / mean green, in %, per region (forehead, cheeks, nose).
  * Liveness: a live face shows a pulse over a good share of its skin, in phase (blood arrives within tens of
    ms), and more than in the hair/background cells; a printed photo shows none. A video of a face played on
    a screen does pulse, so this is a check against photos, not a full anti-spoofing system.
  * Blink rate (MediaPipe face mesh, eye aspect ratio; Soukupova & Cech 2016) needs >= 15 fps: blinks last
    100-400 ms. Head steadiness uses the engine's face tracker and works on both cameras.
"""
import sys
import threading
import time
from collections import deque

import cv2
import numpy as np
from scipy.signal import butter, find_peaks, sosfiltfilt

GRID = 32
MAP_MIN_S = 15.0              # seconds of face video before a map is computed
MAP_WINDOW_S = 30.0
CELL_SNR = 2.5                # pure noise exceeds this amplitude ratio in ~1.3 % of cells (Rayleigh)
CAPTURE_S = 30.0              # blood-flow map capture: seconds of still face video (lock-in noise falls as 1/sqrt(T):
                              # 30 s gives ~22 % better per-cell SNR than 20 s)
MAP_Z = 2.5                   # a skin cell's blood flow is shown fully once its in-phase pulse is 2.5 SD above the
INPHASE_SIGMA = 1.5           # off-heart-rate spread; Gaussian sigma (cells) of the in-phase averaging over skin
MAP_FILL = 0.3                # below this share of skin cells pulsing, try a coarser map ...
MAP_MIN_COARSE = 0.15         # ... used only if >= 15 % of its skin cells pulse (~10x the chance rate of 1.3 %)
SMOOTH_CELLS = 1.0            # Gaussian sigma (cells) of the spatial averaging of the complex lock-in field
SKIN_CELL = 0.6               # share of skin-coloured pixels for a skin cell
BG_CELL = 0.2                 # ... and at most this for a hair / background cell
# Liveness evidence = share of skin cells pulsing at the best frequency x their phase coherence. On synthetic
# faces (25 s, 30 fps and ESP-like 5 fps JPEG noise) photos reached at most 0.053 and pulsing faces (0.15-0.3 %
# pulse) at least 0.39.
LIVE_SKIN_FRAC = 0.15         # liveness: share of skin cells with a pulse
LIVE_COHERENCE = 0.5          # ... whose pulses are in phase (mean resultant length)
LIVE_EVIDENCE = 0.15          # ... and their product
NO_PULSE_EVIDENCE = 0.08      # below this for NO_PULSE_N updates: no pulse (photo?)
NO_PULSE_N = 3
LIVE_BLINKS = 2               # blinks in the last 30 s that make a face live
STILL_RMS = 0.3               # % of face size: a head stiller than this is not living (used without landmarks)
BLINK_MIN_FPS = 15.0
BLINK_DEPTH = 0.35            # a blink dips EAR by at least this share of its median (eyes ~half closed or more)
BLINK_MAX_S = 0.5             # dip width at half depth; longer closures are not blinks
BLINK_REFRACTORY_S = 0.15     # two blinks are at least this far apart
STEADY_RMS = 0.015            # head movement RMS (fraction of face width) for STEADY ...
MOVING_RMS = 0.04             # ... and above which the head is MOVING

# ROI boxes in face coordinates (same as RPPGEngine.rppg_rois)
REGIONS = {'forehead': (0.20, 0.11, 0.60, 0.15), 'left cheek': (0.10, 0.50, 0.27, 0.18),
           'right cheek': (0.63, 0.50, 0.27, 0.18), 'nose': (0.41, 0.44, 0.18, 0.22)}


# ---------------------------------------------------------------- perfusion map + liveness
class PerfusionMapper:
    def __init__(self, grid=GRID, window_s=MAP_WINDOW_S):
        self.grid, self.window_s = grid, window_s
        self.lock = threading.Lock()
        self.reset()

    def reset(self):
        with self.lock:
            self.t = deque()
            self.cells = deque()
            self.skin = None
            self.box = None
            self.crop = None
            self.result = dict(ok=False, reason='needs 15 s of face video')

    def add(self, bgr, t, box, shift):
        """Cell means of the motion-compensated face box for one gated frame."""
        x, y, w, h = [int(v) for v in box]
        if w < 24 or h < 24:
            return
        cx, cy = x + shift[0] + (w - 1) / 2.0, y + shift[1] + (h - 1) / 2.0
        crop = cv2.getRectSubPix(bgr, (w, h), (cx, cy))
        cells = cv2.resize(crop, (self.grid, self.grid), interpolation=cv2.INTER_AREA).astype(np.float32)[..., ::-1]
        with self.lock:
            if self.box is None or tuple(box) != self.box:          # new lock: cells map to new skin
                self.t.clear()
                self.cells.clear()
                ycc = cv2.cvtColor(crop, cv2.COLOR_BGR2YCrCb)
                m = ((ycc[..., 1] > 133) & (ycc[..., 1] < 180) & (ycc[..., 2] > 77) & (ycc[..., 2] < 135))
                self.skin = cv2.resize(m.astype(np.float32), (self.grid, self.grid), interpolation=cv2.INTER_AREA)
                self.box = tuple(box)
            if self.t and t <= self.t[-1]:
                return
            self.t.append(t)
            self.cells.append(cells)
            self.crop = crop
            while self.t and self.t[-1] - self.t[0] > self.window_s:
                self.t.popleft()
                self.cells.popleft()

    def snapshot(self):
        with self.lock:
            if len(self.t) < 10:
                return None
            return np.array(self.t), np.stack(self.cells), self.skin.copy(), self.crop.copy()

    @staticmethod
    def compute(snap, hr_bpm, pool=1, search=True, detect='chrom'):
        """Lock-in perfusion map at the heart rate. Returns a dict (ok False with a reason if not possible).

        pool > 1 averages pool x pool blocks of cells first (a coarser map from a weak pulse: each cell pools
        more pixels); search=False skips the liveness frequency search (done once, at full resolution)."""
        if snap is None:
            return dict(ok=False, reason='needs 15 s of face video')
        t, X, skin, crop = snap
        if pool > 1:
            n, G0 = X.shape[0], X.shape[1]
            g = G0 // pool
            X = X[:, :g * pool, :g * pool].reshape(n, g, pool, g, pool, 3).mean(axis=(2, 4))
            skin = skin[:g * pool, :g * pool].reshape(g, pool, g, pool).mean(axis=(1, 3))
        sigma = max(0.3, SMOOTH_CELLS / pool)
        span = t[-1] - t[0]
        if span < MAP_MIN_S:
            return dict(ok=False, reason=f'needs {MAP_MIN_S:.0f} s of face video ({span:.0f} s)')
        if hr_bpm is None:
            return dict(ok=False, reason='needs a heart rate first')
        fps = (len(t) - 1) / span
        f0 = hr_bpm / 60.0
        fs = float(min(15.0, max(4.0, round(fps))))
        if f0 >= 0.45 * fs:
            return dict(ok=False, reason=f'heart rate too high for {fps:.0f} fps video')
        tu = np.arange(t[0], t[-1], 1.0 / fs)
        i1 = np.clip(np.searchsorted(t, tu, side='right'), 1, len(t) - 1)
        w = ((tu - t[i1 - 1]) / np.maximum(t[i1] - t[i1 - 1], 1e-6)).astype(np.float32)[:, None, None, None]
        Xu = (1 - w) * X[i1 - 1] + w * X[i1]                           # (M, G, G, 3) RGB
        Xn = Xu / np.maximum(Xu.mean(axis=0, keepdims=True), 1e-3) - 1.0
        sos = butter(3, [0.6 / (fs / 2), min(3.5, 0.45 * fs) / (fs / 2)], btype='band', output='sos')
        Xf = sosfiltfilt(sos, Xn, axis=0, padlen=min(len(tu) - 1, 3 * 7))
        g = Xf[..., 1]
        xc, yc = 3 * Xf[..., 0] - 2 * Xf[..., 1], 1.5 * Xf[..., 0] + Xf[..., 1] - 1.5 * Xf[..., 2]
        alpha = xc.std(axis=0) / np.maximum(yc.std(axis=0), 1e-9)
        s = xc - alpha * yc                                             # CHROM pulse per cell
        if detect == 'green':
            s = -Xf[..., 1]                     # still capture: green alone (no red/blue noise mixed in)
        win = np.hanning(len(tu))
        tt = tu - tu[0]
        skin_c, bg_c = skin >= SKIN_CELL, skin <= BG_CELL
        wsk = skin_c.astype(np.float32)
        wbg = bg_c.astype(np.float32)

        def lockin(sig, f):
            e = win * np.exp(-2j * np.pi * f * tt)
            return 2 * np.tensordot(e, sig, axes=(0, 0)) / win.sum()

        def smooth(z, wmap):
            """Spatially average a complex lock-in field over neighbouring cells of the same kind (skin or
            background): the pulse is in phase across neighbouring skin, noise is not, so SNR rises."""
            den = cv2.GaussianBlur(wmap, (0, 0), sigma) + 1e-6
            re = cv2.GaussianBlur((z.real * wmap).astype(np.float32), (0, 0), sigma) / den
            im = cv2.GaussianBlur((z.imag * wmap).astype(np.float32), (0, 0), sigma) / den
            return (re + 1j * im) * (wmap > 0)

        # lock-in of the CHROM pulse on a frequency grid; skin and background cells smoothed separately
        fmax = min(3.0, 0.45 * fs)
        grid_f = np.arange(0.6, fmax + 1e-9, 0.05)
        Z = np.stack([lockin(s, f) for f in grid_f])                   # (F, G, G)
        A = np.abs(np.stack([smooth(z, wsk) + smooth(z, wbg) for z in Z]))

        def cell_snr(f):
            # local noise floor: lock-in amplitudes within +-0.6 Hz of f (excluding +-0.2 Hz and the harmonic), so
            # the stronger drift / motion noise at low frequencies does not make low rates look like a pulse
            ref = (np.abs(grid_f - f) > 0.2) & (np.abs(grid_f - f) <= 0.6) & (np.abs(grid_f - 2 * f) > 0.2)
            if ref.sum() < 6:
                ref = (np.abs(grid_f - f) > 0.2) & (np.abs(grid_f - 2 * f) > 0.2)
            k = int(np.argmin(np.abs(grid_f - f)))
            amp = np.abs(smooth(lockin(s, f), wsk) + smooth(lockin(s, f), wbg)) if abs(grid_f[k] - f) > 1e-6 else A[k]
            return amp / np.maximum(np.median(A[ref], axis=0), 1e-12)

        def frac(snr_map):
            pulse = snr_map >= CELL_SNR
            return float((pulse & skin_c).sum() / max(skin_c.sum(), 1)), float((pulse & bg_c).sum() / max(bg_c.sum(), 1)), pulse

        snr = cell_snr(f0)
        skin_frac, bg_frac, pulse = frac(snr)
        zg = smooth(lockin(g, f0), wsk)
        pi = 2 * np.abs(zg) * 100.0                                     # peak-to-peak green / DC, %
        sel = pulse & skin_c
        phasors = zg[sel] / np.maximum(np.abs(zg[sel]), 1e-12)
        coherence = float(np.abs(phasors.mean())) if sel.sum() >= 3 else 0.0
        # Liveness does not rely on the heart-rate value: the frequency (45-150 BPM) at which the most skin
        # pulses, in phase, is searched; a photo pulses at no frequency.
        best = (0.0, None, 0.0, 0.0)
        for f in (grid_f[(grid_f >= 0.75) & (grid_f <= min(2.5, fmax))] if search else []):
            sf, bf, pm = frac(cell_snr(f))
            zz = smooth(lockin(g, f), wsk)[pm & skin_c]
            coh = float(np.abs((zz / np.maximum(np.abs(zz), 1e-12)).mean())) if len(zz) >= 3 else 0.0
            if sf * coh > best[0]:
                best = (sf * coh, f, sf, bf, coh)
        live_f = best[1]
        # ---- displayed map: phase-referenced (in-phase) pulse amplitude per skin cell ----
        # The face-wide pulse (sum over skin cells at f0) gives the reference phase. A cell's in-phase component is
        # an unbiased amplitude estimate (noise averages to zero, unlike the magnitude, which noise only inflates)
        # and is averaged over neighbouring skin. Its uncertainty comes from the same estimate at frequencies away
        # from the heart rate: z = (value - mean_off) / sd_off. Every skin cell gets a value; z sets its opacity.
        sig_ip = max(0.5, INPHASE_SIGMA / pool)
        den_ip = cv2.GaussianBlur(wsk, (0, 0), sig_ip) + 1e-6

        def inphase(f):
            zf = lockin(g, f)
            ref = (zf * wsk).sum()
            a = (np.real(zf * np.conj(ref)) / max(abs(ref), 1e-12)).astype(np.float32)
            return cv2.GaussianBlur(a * wsk, (0, 0), sig_ip) / den_ip

        off = [f for f in grid_f if abs(f - f0) > 0.2 and abs(f - 2 * f0) > 0.2]
        a0 = inphase(f0)                  # cells pulsing in step with the face are positive (any colour sign)
        offs = np.stack([inphase(f) for f in off])
        mu, sd = offs.mean(axis=0), np.maximum(offs.std(axis=0), 1e-12)
        zmap = (a0 - mu) / sd
        pi_map = 2 * 100.0 * np.clip(a0, 0, None)                      # peak-to-peak green / DC, %
        conf = (zmap >= MAP_Z) & skin_c
        coverage = float(conf.sum() / max(skin_c.sum(), 1))
        amap = np.where(skin_c, pi_map, np.nan)
        alpha = np.where(skin_c, np.clip((zmap - 1.0) / (MAP_Z - 0.5), 0.0, 1.0), 0.0)
        G = X.shape[1]
        regions = {}
        for name, (rx, ry, rw, rh) in REGIONS.items():
            r0, r1 = int(ry * G), max(int(ry * G) + 1, int(round((ry + rh) * G)))
            c0, c1 = int(rx * G), max(int(rx * G) + 1, int(round((rx + rw) * G)))
            m = skin_c[r0:r1, c0:c1]
            if m.sum() < 2:
                regions[name] = dict(pi=None, z=None)
                continue
            ra = float(a0[r0:r1, c0:c1][m].mean())
            ro = offs[:, r0:r1, c0:c1][:, m].mean(axis=1)
            rz = (ra - ro.mean()) / max(float(ro.std()), 1e-12)
            regions[name] = dict(pi=round(2 * 100.0 * ra, 3) if rz >= MAP_Z else None, z=round(float(rz), 1))
        vals = pi_map[conf]
        return dict(ok=True, reason='', hr=round(hr_bpm, 1), fps=round(fps, 1), seconds=round(span, 1), grid=X.shape[1],
                    skin_pulse_frac=round(coverage, 3), cells_snr_frac=round(skin_frac, 3), bg_pulse_frac=round(bg_frac, 3),
                    coherence=round(coherence, 2),
                    live_hr=None if live_f is None else round(60.0 * live_f, 1),
                    live_skin_frac=round(best[2], 3) if live_f is not None else 0.0,
                    live_bg_frac=round(best[3], 3) if live_f is not None else 0.0,
                    live_coherence=round(best[4], 2) if live_f is not None else 0.0,
                    pi_median=round(float(np.median(vals)), 3) if len(vals) else None,
                    pi_p90=round(float(np.percentile(vals, 90)), 3) if len(vals) else None,
                    regions=regions, map=amap, alpha=alpha, z=zmap, snr=snr, skin=skin, crop=crop)

    @staticmethod
    def render(res, size=240):
        """JPEG of the face with the perfusion map over the skin cells that pulse (inferno: weak -> strong)."""
        if not res or not res.get('ok'):
            return None
        crop = res['crop']
        h, w = crop.shape[:2]
        scale = size / max(h, w)
        base = cv2.resize(crop, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        amap, alpha = res['map'], res.get('alpha')
        out = 0.55 * base.astype(np.float32)                      # dimmed face; colour where blood flow is measured
        if alpha is not None and np.nanmax(alpha) > 0:
            conf = alpha >= 0.99
            ref = amap[conf] if conf.any() else amap[np.isfinite(amap)]
            hi = max(float(np.nanpercentile(ref, 95)), 1e-6)
            norm = np.clip(np.nan_to_num(amap / hi), 0, 1)
            heat = cv2.applyColorMap((norm * 255).astype(np.uint8), cv2.COLORMAP_INFERNO)
            heat = cv2.resize(heat, (base.shape[1], base.shape[0]), interpolation=cv2.INTER_CUBIC).astype(np.float32)
            mask = cv2.resize(alpha.astype(np.float32), (base.shape[1], base.shape[0]), interpolation=cv2.INTER_LINEAR)
            mask = cv2.GaussianBlur(mask, (0, 0), 2)[..., None] * 0.85
            out = out * (1 - mask) + heat * mask
        out = np.clip(out, 0, 255).astype(np.uint8)
        ok, enc = cv2.imencode('.jpg', out, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return enc.tobytes() if ok else None


def map_with_fallback(snap, hr_bpm):
    """Full-resolution map; with a weak pulse, a coarser map (cells pool 4x / 16x the pixels) instead of an
    almost empty one, used only if >= MAP_MIN_COARSE of its skin cells pulse. Liveness evidence always comes
    from the full-resolution search (its thresholds were set there)."""
    res = PerfusionMapper.compute(snap, hr_bpm)
    if res.get('ok') and res['skin_pulse_frac'] < MAP_FILL:
        for pool in (2, 4):
            coarse = PerfusionMapper.compute(snap, hr_bpm, pool=pool, search=False)
            if coarse.get('ok') and coarse['skin_pulse_frac'] >= MAP_MIN_COARSE and \
                    coarse['skin_pulse_frac'] > res['skin_pulse_frac']:
                coarse.update({k: res[k] for k in ('live_hr', 'live_skin_frac', 'live_bg_frac', 'live_coherence')})
                res = coarse
            if res['skin_pulse_frac'] >= MAP_FILL:
                break
    return res


def _summary(res):
    return {k: res.get(k) for k in ('hr', 'fps', 'seconds', 'grid', 'skin_pulse_frac', 'pi_median', 'pi_p90', 'regions')}


class LivenessCheck:
    """Is this a live face? Two independent cues, either of which is enough:
      * pulse: skin cells pulsing in phase at one frequency (evidence = pulsing share x coherence >= LIVE_EVIDENCE,
        2 updates in a row);
      * blinks: >= LIVE_BLINKS blinks in the last 30 s (a photo cannot blink; eye-blink liveness is a standard
        anti-spoofing cue).
    NO_PULSE ("photo?") needs positive evidence of absence for NO_PULSE_N updates: no pulse, no blink in 30 s
    and, if face landmarks are unavailable, a face stiller than a living head (< STILL_RMS of its size).
    A weak pulse in poor light is reported as CHECKING, never as a photo."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.state, self.live_n, self.none_n = 'CHECKING', 0, 0
        self.detail = 'Waiting for 15 s of face video.'

    def update(self, m, blinks_30s=None, head_rms=None):
        ok = bool(m and m.get('ok'))
        sf, bf, coh = (m['live_skin_frac'], m['live_bg_frac'], m['live_coherence']) if ok else (0.0, 0.0, 0.0)
        pulse = ok and sf >= LIVE_SKIN_FRAC and coh >= LIVE_COHERENCE and sf * coh >= LIVE_EVIDENCE and sf >= 2 * bf + 0.02
        blinking = blinks_30s is not None and blinks_30s >= LIVE_BLINKS
        no_pulse = ok and sf * coh < NO_PULSE_EVIDENCE
        no_blink = blinks_30s == 0 if blinks_30s is not None else (head_rms is not None and head_rms < STILL_RMS)
        self.live_n = self.live_n + 1 if pulse else 0
        self.none_n = self.none_n + 1 if (no_pulse and no_blink) else 0
        if self.live_n >= 2 or blinking:
            self.state = 'LIVE'
        elif self.none_n >= NO_PULSE_N:
            self.state = 'NO_PULSE'
        elif not (self.state == 'LIVE' and ok and sf * coh >= LIVE_EVIDENCE / 2):
            self.state = 'CHECKING'
        cues = []
        if ok:
            cues.append(f'{100 * sf:.0f}% of skin pulses in phase at {m["live_hr"] or 0:.0f} BPM (coherence {coh:.2f})')
        else:
            cues.append((m or {}).get('reason') or 'no pulse map yet')
        if blinks_30s is not None:
            cues.append(f'{blinks_30s} blink(s) in 30 s')
        self.detail = '; '.join(cues) + '.'
        return self.snapshot()

    def snapshot(self):
        label = dict(LIVE='LIVE', NO_PULSE='NO PULSE OR BLINK: PHOTO?', CHECKING='CHECKING')[self.state]
        level = dict(LIVE='ok', NO_PULSE='flag', CHECKING='idle')[self.state]
        return dict(state=self.state, label=label, level=level, detail=self.detail)


# ---------------------------------------------------------------- blink rate (MediaPipe face mesh)
_LEFT_EYE = (33, 160, 158, 133, 153, 144)
_RIGHT_EYE = (362, 385, 387, 263, 373, 380)
_POSE_IDX = (1, 152, 263, 33, 287, 57)                 # nose tip, chin, eye corners, mouth corners
_POSE_3D = np.array([(0.0, 0.0, 0.0), (0.0, -330.0, -65.0), (-225.0, 170.0, -135.0), (225.0, 170.0, -135.0),
                     (-150.0, -150.0, -125.0), (150.0, -150.0, -125.0)])


def _load_face_mesh():
    """MediaPipe face mesh, working around two incompatibilities of this environment without changing it:
    a broken optional TensorFlow (NumPy 2) and protobuf 7 (FieldDescriptor.label removed)."""
    try:
        if 'tensorflow' not in sys.modules:
            sys.modules['tensorflow'] = None             # optional dependency: make the import fail cleanly
        import inspect
        import textwrap
        import mediapipe as mp
        from mediapipe.python import solution_base as sb
        from google.protobuf import descriptor
        if not hasattr(descriptor.FieldDescriptor, 'label'):
            src = textwrap.dedent(inspect.getsource(sb.SolutionBase._modify_calculator_options))
            src = src.replace("field_name].label", "field_name]").replace(
                "if field_label == descriptor.FieldDescriptor.LABEL_REPEATED:", "if field_label.is_repeated:")
            ns = dict(sb.__dict__)
            exec(src, ns)
            sb.SolutionBase._modify_calculator_options = ns['_modify_calculator_options']
        mesh = mp.solutions.face_mesh.FaceMesh(static_image_mode=False, max_num_faces=1, refine_landmarks=True,
                                               min_detection_confidence=0.5, min_tracking_confidence=0.5)
        return mesh, ''
    except Exception as exc:                              # noqa: BLE001 - report why, keep the rest running
        return None, f'face landmarks unavailable ({exc.__class__.__name__})'


def eye_aspect_ratio(pts, idx):
    p = pts[list(idx)]
    return float((np.linalg.norm(p[1] - p[5]) + np.linalg.norm(p[2] - p[4])) / (2 * np.linalg.norm(p[0] - p[3]) + 1e-9))


class BlinkCounter:
    """Blinks in an eye-aspect-ratio (EAR) series: sharp dips relative to the openness around them.

    A blink is a local minimum of EAR whose prominence (depth below the neighbouring levels) is at least
    BLINK_DEPTH of the median EAR and which lasts at most BLINK_MAX_S at half depth. Prominence is relative
    to the levels on both sides, so a change of gaze that leaves the eye less open afterwards (a level shift)
    does not hide the blink, and one blink is one minimum (no double counting)."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.lock = threading.Lock()
        self.ear = deque()                # (t, ear)

    def add(self, t, ear, window_s=60.0):
        with self.lock:
            if self.ear and t <= self.ear[-1][0]:
                return
            self.ear.append((t, ear))
            while self.ear and t - self.ear[0][0] > window_s:
                self.ear.popleft()

    def series(self):
        with self.lock:
            return list(self.ear)

    @property
    def blinks(self):
        ear = self.series()
        if len(ear) < 10:
            return []
        t = np.array([x for x, _ in ear])
        e = np.array([y for _, y in ear])
        dt = float(np.median(np.diff(t)))
        pk, prop = find_peaks(-e, prominence=max(0.03, BLINK_DEPTH * float(np.median(e))),
                              width=(None, max(1.0, BLINK_MAX_S / dt)), rel_height=0.5,
                              distance=max(1, int(BLINK_REFRACTORY_S / dt)))
        return [float(t[k]) for k in pk]

    def rate(self, now):
        ear = self.series()
        if len(ear) < 2:
            return None, 0.0
        span = now - ear[0][0]
        if span < 20.0:
            return None, span
        return 60.0 * len(self.blinks) / span, span


class FaceInsights:
    """Per-frame collection (camera thread) + 2 s updates (estimate thread) for the dashboard."""

    def __init__(self, use_mesh=True):
        self.mapper = PerfusionMapper()                  # continuous, for liveness
        self.cap_mapper = PerfusionMapper()              # blood-flow map captures (on request)
        self.capture = dict(state='IDLE', message='Press capture and hold still for 30 s.')
        self.cap_jpeg = None
        self.liveness = LivenessCheck()
        self.blink = BlinkCounter()
        self.mesh, self.mesh_reason = (_load_face_mesh() if use_mesh else (None, 'disabled'))
        self.frame_t = deque(maxlen=60)
        self.pose = None
        self.perfusion = dict(ok=False, reason='needs 15 s of face video')
        self.last_jpeg = None
        self.lock = threading.Lock()
        self.mesh_async = False           # True (live server): landmarks run on their own thread, newest frame first
        self._mesh_cv = threading.Condition()
        self._mesh_job = None
        if self.mesh is not None:
            threading.Thread(target=self._mesh_loop, daemon=True).start()

    def reset(self):
        self.mapper.reset()
        self.liveness.reset()
        self.blink.reset()
        self.frame_t.clear()
        self.pose = None
        self.perfusion = dict(ok=False, reason='needs 15 s of face video')
        self.last_jpeg = None
        self.cap_mapper.reset()
        with self.lock:                          # a finished capture is kept; one in progress is cancelled
            if self.capture['state'] == 'RECORDING':
                self.capture = dict(state='IDLE', message='Capture cancelled (camera changed or face lost). Press capture again.')

    def note_frame(self, t):
        """Every camera frame (face or not), for the frame rate."""
        if not self.frame_t or t > self.frame_t[-1]:
            self.frame_t.append(t)

    def add_frame(self, bgr, t, face, locked, shift, gated):
        if gated:
            self.mapper.add(bgr, t, locked, shift)
            with self.lock:
                recording = self.capture['state'] == 'RECORDING'
                if recording:
                    if self.capture.get('t0') is None:
                        self.capture['t0'] = t
                    self.capture['t_last'] = t
            if recording:
                self.cap_mapper.add(bgr, t, locked, shift)
        if self.mesh is not None and face is not None:
            if self.mesh_async:
                with self._mesh_cv:                       # newest frame wins; the camera thread never waits
                    self._mesh_job = (bgr, t, face)
                    self._mesh_cv.notify()
            else:
                self._landmarks(bgr, t, face)

    def _mesh_loop(self):
        while True:
            with self._mesh_cv:
                while self._mesh_job is None:
                    self._mesh_cv.wait()
                job, self._mesh_job = self._mesh_job, None
            try:
                self._landmarks(*job)
            except Exception:                              # noqa: BLE001 - one bad frame must not stop blinks
                pass

    def fps(self):
        if len(self.frame_t) < 5:
            return None
        return (len(self.frame_t) - 1) / max(self.frame_t[-1] - self.frame_t[0], 1e-6)

    def _landmarks(self, bgr, t, face):
        h, w = bgr.shape[:2]
        x, y, fw, fh = [float(v) for v in face]
        x0, y0 = int(max(0, x - 0.3 * fw)), int(max(0, y - 0.3 * fh))
        x1, y1 = int(min(w, x + 1.3 * fw)), int(min(h, y + 1.3 * fh))
        crop = bgr[y0:y1, x0:x1]
        if crop.size == 0:
            return
        s = min(1.0, 256.0 / max(crop.shape[:2]))
        if s < 1.0:
            crop = cv2.resize(crop, (int(crop.shape[1] * s), int(crop.shape[0] * s)), interpolation=cv2.INTER_AREA)
        res = self.mesh.process(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
        if not res.multi_face_landmarks:
            return
        ch, cw = crop.shape[:2]
        pts = np.array([(p.x * cw, p.y * ch) for p in res.multi_face_landmarks[0].landmark])
        ear = 0.5 * (eye_aspect_ratio(pts, _LEFT_EYE) + eye_aspect_ratio(pts, _RIGHT_EYE))
        self.blink.add(t, ear)
        cam = np.array([[cw, 0, cw / 2], [0, cw, ch / 2], [0, 0, 1]], float)
        ok, rvec, _ = cv2.solvePnP(_POSE_3D, pts[list(_POSE_IDX)].astype(float), cam, np.zeros(4),
                                   flags=cv2.SOLVEPNP_ITERATIVE)
        if ok:
            rot, _ = cv2.Rodrigues(rvec)
            sy = np.hypot(rot[0, 0], rot[1, 0])
            pitch = np.degrees(np.arctan2(rot[2, 1], rot[2, 2]))
            yaw = np.degrees(np.arctan2(-rot[2, 0], sy))
            pitch = (pitch + 180) % 360 - 180
            pitch = pitch - 180 if pitch > 90 else pitch + 180 if pitch < -90 else pitch
            self.pose = (t, float(yaw), float(pitch))

    # ------------------------------------------------------------ 2 s update (estimate thread)
    def update(self, hr_bpm, motion, still_from=None):
        """motion: (t, x, y) arrays of the face position in face widths/heights (engine tracker);
        still_from: time after the last head movement (the map uses only the still stretch)."""
        snap = self.mapper.snapshot()
        res = None
        if snap is not None and still_from is not None:
            still_s = snap[0][-1] - still_from
            if still_s < MAP_MIN_S:
                res = dict(ok=False, reason=f'hold still ({MAP_MIN_S - still_s:.0f} s more)')
            else:
                keep = snap[0] >= still_from
                snap = (snap[0][keep], snap[1][keep], snap[2], snap[3])
        if res is None:
            res = map_with_fallback(snap, hr_bpm)
        self._capture_step(hr_bpm, still_from)
        jpeg = PerfusionMapper.render(res)
        head = head_steadiness(*motion) if motion is not None else dict(state='UNKNOWN', rms=None)
        blinks_30s = None
        ear = self.blink.series()
        if self.mesh is not None and ear and self.frame_t:
            seen = ear[-1][0] - ear[0][0]
            if seen >= 20.0:
                now = self.frame_t[-1]
                blinks_30s = sum(1 for b in self.blink.blinks if b >= now - 30.0)
        live = self.liveness.update(res, blinks_30s=blinks_30s, head_rms=head.get('rms'))
        with self.lock:
            self.perfusion = res
            if jpeg is not None:
                self.last_jpeg = jpeg
            self.live = live
            self.head = head

    def map_jpeg(self):
        """The last captured blood-flow map (the map is made on request from a still 30 s capture)."""
        with self.lock:
            return self.cap_jpeg

    def start_capture(self):
        self.cap_mapper.reset()
        with self.lock:
            self.capture = dict(state='RECORDING', t0=None, t_last=None, restarts=0,
                                message=f'Hold still and face the camera for {CAPTURE_S:.0f} s.')

    def _capture_step(self, hr_bpm, still_from):
        """Advance a capture (called every 2 s): restart on movement or a lost face, finish after CAPTURE_S."""
        with self.lock:
            c = dict(self.capture)
        if c['state'] != 'RECORDING' or c.get('t0') is None:
            return
        now = self.frame_t[-1] if self.frame_t else c['t_last']
        if (still_from is not None and still_from > c['t0'] + 0.5) or (c['t_last'] is not None and now - c['t_last'] > 3.0):
            reason = 'You moved' if still_from is not None and still_from > c['t0'] + 0.5 else 'Face lost'
            self.cap_mapper.reset()
            with self.lock:
                self.capture.update(t0=None, t_last=None, restarts=c.get('restarts', 0) + 1,
                                    message=f'{reason}: restarting. Hold still for {CAPTURE_S:.0f} s.')
            return
        if c['t_last'] - c['t0'] < CAPTURE_S:
            return
        res = map_with_fallback(self.cap_mapper.snapshot(), hr_bpm)
        jpeg = PerfusionMapper.render(res)
        when = time.strftime('%H:%M:%S')
        with self.lock:
            if res.get('ok') and jpeg is not None:
                self.cap_jpeg = jpeg
                self.capture = dict(state='DONE', captured_at=when, result=_summary(res),
                                    message=f'Captured at {when}: {100 * res["skin_pulse_frac"]:.0f}% of skin pulses '
                                            f'({res["grid"]}x{res["grid"]} map, {res["seconds"]:.0f} s at {res["fps"]:.0f} fps).')
            else:
                self.capture = dict(state='FAILED', message='Capture failed: ' + (res.get('reason') or 'no map') + '. Try again.')

    def capture_status(self):
        with self.lock:
            c = dict(self.capture)
        if c['state'] == 'RECORDING':
            done = (c['t_last'] - c['t0']) if c.get('t0') is not None and c.get('t_last') is not None else 0.0
            c['seconds_left'] = round(max(0.0, CAPTURE_S - done), 1)
        c.pop('t0', None)
        c.pop('t_last', None)
        return c

    def telemetry(self, now):
        with self.lock:
            p = self.perfusion
            perf = {k: p.get(k) for k in ('ok', 'reason', 'hr', 'fps', 'seconds', 'grid', 'skin_pulse_frac', 'bg_pulse_frac',
                                          'coherence', 'pi_median', 'pi_p90', 'regions', 'live_hr', 'live_skin_frac',
                                          'live_bg_frac', 'live_coherence')}
            live = getattr(self, 'live', self.liveness.snapshot())
            head = getattr(self, 'head', dict(state='UNKNOWN'))
        fps = self.fps()
        rate, span = self.blink.rate(now)
        if self.mesh is None:
            blink = dict(ok=False, rate=None, reason=self.mesh_reason)
        elif fps is not None and fps < BLINK_MIN_FPS:
            blink = dict(ok=False, rate=None, reason=f'needs >= {BLINK_MIN_FPS:.0f} fps video (have {fps:.0f})')
        elif rate is None:
            blink = dict(ok=False, rate=None, reason=f'counting ({span:.0f}/20 s)')
        else:
            blink = dict(ok=True, rate=round(rate, 1), blinks=len(self.blink.blinks), seconds=round(span),
                         reason='')
        pose = None
        if self.pose and now - self.pose[0] < 2.0:
            pose = dict(yaw=round(self.pose[1], 1), pitch=round(self.pose[2], 1))
        return dict(perfusion=perf, capture=self.capture_status(), liveness=live, blink=blink, head=dict(head, pose=pose))

    def live_traces(self, now, window_s=20.0):
        """Eye openness over the last window_s with the blinks in it (for the real-time chart)."""
        ear = [(t, e) for t, e in self.blink.series() if t >= now - window_s]
        step = max(1, len(ear) // 240)
        blinks = [b for b in self.blink.blinks if b >= now - window_s]
        return dict(ear_t=[round(t - now, 3) for t, _ in ear[::step]], ear=[round(e, 3) for _, e in ear[::step]],
                    blinks=[round(b - now, 2) for b in blinks])


MOVE_THRESH = 0.03            # a head movement: the face moves > 3 % of its size from its 1 s running median


def last_movement_end(t, x, y, thresh=MOVE_THRESH):
    """Time after which the head has stayed still (start of the series if it never moved), or None.

    One movement corrupts a whole 30 s analysis window (the skin cells and breathing signals jump), so the
    perfusion map and the breathing rate use only the stretch after the last movement."""
    t, x, y = (np.asarray(v, float) for v in (t, x, y))
    if len(t) < 5:
        return None
    moving = np.zeros(len(t), bool)
    j0 = 0
    for i in range(len(t)):
        while t[i] - t[j0] > 1.0:
            j0 += 1
        mx, my = np.median(x[j0:i + 1]), np.median(y[j0:i + 1])
        moving[i] = np.hypot(x[i] - mx, y[i] - my) > thresh
    if not moving.any():
        return float(t[0])
    return float(t[np.where(moving)[0][-1]] + 0.5)


def head_steadiness(t, x, y, window_s=10.0):
    """STEADY / SLIGHT MOVEMENT / MOVING from the face position over the last window_s (fractions of the
    face size): RMS distance from the mean position. Breathing moves the head by < 1 %."""
    t, x, y = (np.asarray(v, float) for v in (t, x, y))
    if len(t) < 5:
        return dict(state='UNKNOWN', rms=None)
    m = t >= t[-1] - window_s
    if m.sum() < 5 or t[m][-1] - t[m][0] < 3.0:
        return dict(state='UNKNOWN', rms=None)
    rms = float(np.sqrt(np.mean((x[m] - x[m].mean()) ** 2 + (y[m] - y[m].mean()) ** 2)))
    state = 'STEADY' if rms < STEADY_RMS else 'MOVING' if rms > MOVING_RMS else 'SLIGHT_MOVEMENT'
    return dict(state=state, rms=round(100 * rms, 2))
