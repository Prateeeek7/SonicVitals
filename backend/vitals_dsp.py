"""Signal-processing core for SonicVitals.

All functions here are pure (no global state) so that the live server
(`usb_streamer.py`) and the offline evaluation (`analysis/evaluate.py`) run
exactly the same code. Section numbers refer to the accompanying paper.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfiltfilt, filtfilt, welch, resample_poly, find_peaks, hilbert

# ---------------------------------------------------------------- constants
FS_OPT = 15.0                 # uniform analysis rate for the optical channel (Hz)
CARDIAC_BAND = (0.75, 2.5)    # 45-150 beats/min
RESP_BAND = (0.15, 0.40)      # 9-24 breaths/min
MAX_GAP_S = 2.0               # dropouts up to this long are bridged by interpolation; longer ones restart the segment
MIN_COVERAGE = 0.8            # share of the segment that must be backed by real (not bridged) frames
MIN_SEG_HR_S = 10.0           # shortest contiguous segment for an HR estimate
MIN_SNR_HR_DB = -2.0          # HR needs this SNR *and* full method consensus (CONSENSUS_MIN). Together they
                              # accept noise-only 10/20/30 s windows in 8/4/1 % of cases (about 4 % overall;
                              # see tests), and accept a 0.6 % pulse ~70 % of the time vs ~25 % for SNR >= 0 dB.
CONSENSUS_MIN = 2             # how many of POS and green must agree with the CHROM peak
TRACK_HALF_BPM = 12.0         # tracking window around the previous accepted HR
TRACK_POWER_RATIO = 0.5       # keep the in-window peak if it has at least this share of the global peak power
ARTIFACT_MAD_K = 4.0          # frame-to-frame colour changes beyond this many robust SDs are motion/ROI steps
MIN_ARTIFACT_SCALE = 0.0015     # robust-SD floor for the log-colour frame difference
MAX_ARTIFACT_FRAC = 0.15      # HR is withheld when more of the segment than this had to be repaired
MIN_STILL_S = 12.0            # after a movement, analyse only the still stretch since then if it is at least this long
BG_REJECT_RATIO = 1.0         # a spectral peak at least this strong (relative) on the background is lighting, not pulse
EXCLUDE_HZ = 0.06             # half-width of the frequency zone skipped around a background (lighting) peak
BG_PEAK_FACTOR = 4.0          # ... and it must stand out on the background (x median background bin power)
AGREE_BPM = 6.0               # consensus: POS or green must find the CHROM peak within this distance
MIN_SEG_RR_S = 15.0           # shortest contiguous segment for an RR estimate
MIN_Q_RR = 0.5                # RR is reported only if this share of 0.05-1 Hz power lies at the peak
                              # (synthetic: breathing ~0.9, noise <= 0.36; re-tune on development data)
NFFT = 4096

FS_AUDIO = 16000
FS_PCG = 1000                 # PCG analysis rate after decimation
PCG_BAND = (25.0, 400.0)
HR_LAG_S = (0.4, 60.0 / 45.0) # 45-150 beats/min
FUSION_DELTA_BPM = 8.0
MIN_RHO_ACOUSTIC = 0.4         # envelope-autocorrelation peak needed for a PCG heart rate
MIN_BEAT_CONSISTENCY = 0.6     # share of detected S1-S1 intervals within +-15 % of the autocorrelation period.
                               # Ambient room sound (mic not on the chest, 187 s, 10 s windows): the old gate
                               # (rho >= 0.3) accepted 16 % of windows; rho >= 0.4 plus this check accepted 0 %.


# ================================================================ helpers
def last_contiguous_segment(t: np.ndarray, max_gap: float = MAX_GAP_S) -> int:
    """Index at which the most recent gap-free run of timestamps starts."""
    if len(t) < 2:
        return 0
    gaps = np.where(np.diff(t) > max_gap)[0]
    return int(gaps[-1] + 1) if len(gaps) else 0


def resample_uniform(t: np.ndarray, x: np.ndarray, fs: float = FS_OPT):
    """Linearly interpolate irregularly sampled `x` (N or N x C) onto a uniform grid.

    Only the most recent contiguous segment (no gap > MAX_GAP_S) is used.
    Returns (t_uniform, x_uniform); both empty if fewer than 2 samples remain.
    """
    t = np.asarray(t, dtype=float)
    x = np.asarray(x, dtype=float)
    start = last_contiguous_segment(t)
    t, x = t[start:], x[start:]
    if len(t) < 2 or t[-1] - t[0] < 1.0 / fs:
        return np.array([]), np.empty((0,) + x.shape[1:])
    tu = np.arange(t[0], t[-1] + 1e-9, 1.0 / fs)
    if x.ndim == 1:
        return tu, np.interp(tu, t, x)
    return tu, np.column_stack([np.interp(tu, t, x[:, c]) for c in range(x.shape[1])])


def segment_coverage(t: np.ndarray, frame_gap: float = 0.25) -> float:
    """Share of the most recent segment covered by real frames.

    Gaps longer than `frame_gap` (two frame intervals at 8 frames/s) count as
    missing time beyond `frame_gap`; that time is filled by interpolation.
    """
    t = np.asarray(t, dtype=float)
    t = t[last_contiguous_segment(t):]
    if len(t) < 2 or t[-1] <= t[0]:
        return 0.0
    missing = np.sum(np.maximum(0.0, np.diff(t) - frame_gap))
    return float(1.0 - missing / (t[-1] - t[0]))


def standardize(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    sd = np.std(x)
    return (x - np.mean(x)) / sd if sd > 0 else x - np.mean(x)


def bandpass(x: np.ndarray, fs: float, band, order: int) -> np.ndarray:
    """Zero-phase Butterworth band-pass (forward-backward)."""
    b, a = butter(order, [band[0] / (fs / 2), band[1] / (fs / 2)], btype="band")
    padlen = min(len(x) - 1, 3 * max(len(a), len(b)))
    return filtfilt(b, a, x, padlen=padlen)


def parabolic_peak(y: np.ndarray, k: int) -> float:
    """Sub-bin location of a peak at index k (paper Eq. 6)."""
    if k <= 0 or k >= len(y) - 1:
        return float(k)
    a, b, c = y[k - 1], y[k], y[k + 1]
    denom = a - 2 * b + c
    if denom >= 0:                     # not a strict local maximum (flat or concave-up)
        return float(k)
    # The vertex of a parabola through a local maximum lies within half a bin.
    return float(k + np.clip(0.5 * (a - c) / denom, -0.5, 0.5))


def band_peak(freqs: np.ndarray, psd: np.ndarray, band, exclude=()):
    """Interpolated location and bin power of the largest local maximum inside `band`.

    A band-edge value that keeps rising outside the band is the skirt of out-of-band
    power (e.g. slow drift), not a peak, so only true local maxima are considered.
    Maxima within EXCLUDE_HZ of a frequency in `exclude` (lighting seen on the background)
    are skipped; the spectrum itself is not edited, so their flanks cannot become peaks.
    """
    mask = (freqs >= band[0]) & (freqs <= band[1])
    idx = np.where(mask)[0]
    idx = idx[(idx > 0) & (idx < len(psd) - 1)]
    idx = idx[(psd[idx] >= psd[idx - 1]) & (psd[idx] >= psd[idx + 1])]
    for fr in exclude:
        idx = idx[np.abs(freqs[idx] - fr) > EXCLUDE_HZ]
    if len(idx) == 0:
        return None, 0.0
    k = int(idx[np.argmax(psd[idx])])
    return float(parabolic_peak(psd, k) * (freqs[1] - freqs[0])), float(psd[k])


def welch_peak(x: np.ndarray, fs: float, band, nperseg: int, nfft: int = NFFT):
    """Welch PSD (Hann, 50 % overlap, zero-padded) and interpolated in-band peak."""
    nperseg = int(min(len(x), nperseg))
    freqs, psd = welch(x, fs=fs, window="hann", nperseg=nperseg,
                       noverlap=nperseg // 2, nfft=max(nfft, nperseg))
    f0, _ = band_peak(freqs, psd, band)
    return f0, freqs, psd


def tracked_peak(freqs: np.ndarray, psd: np.ndarray, band, prior_hz: float | None, exclude=()):
    """Global in-band peak, or the peak near `prior_hz` if it is nearly as strong (paper Sec. V-E).

    Returns (f0, tracked) where tracked is True when the local peak replaced the global one.
    """
    f_g, p_g = band_peak(freqs, psd, band, exclude)
    if f_g is None or prior_hz is None:
        return f_g, False
    half = TRACK_HALF_BPM / 60.0
    local = (max(band[0], prior_hz - half), min(band[1], prior_hz + half))
    if local[0] >= local[1]:
        return f_g, False
    f_l, p_l = band_peak(freqs, psd, local, exclude)
    if f_l is not None and p_l >= TRACK_POWER_RATIO * p_g and abs(f_l - f_g) > 1e-9:
        return f_l, True
    return f_g, False


def dehaan_snr(freqs: np.ndarray, psd: np.ndarray, f0: float,
               band=(0.5, 4.0), half_fund: float = 0.1, half_harm: float = 0.2) -> float:
    """SNR of de Haan & Jeanne (2013), paper Eq. 7, in dB."""
    inband = (freqs >= band[0]) & (freqs <= band[1])
    signal = inband & ((np.abs(freqs - f0) <= half_fund) | (np.abs(freqs - 2 * f0) <= half_harm))
    noise = inband & ~signal
    ps, pn = np.sum(psd[signal]), np.sum(psd[noise])
    if ps <= 0 or pn <= 0:
        return float("nan")
    return float(10 * np.log10(ps / pn))


def spectral_concentration(freqs, psd, f0, band=CARDIAC_BAND, half: float = 0.1) -> float:
    """Fraction of in-band power within +/- half Hz of f0 (paper Eq. 8)."""
    inband = (freqs >= band[0]) & (freqs <= band[1])
    total = np.sum(psd[inband])
    if total <= 0:
        return 0.0
    near = inband & (np.abs(freqs - f0) <= half)
    return float(np.sum(psd[near]) / total)


# ================================================================ optical
def chrom_pulse(rgb: np.ndarray, L: int | None = None) -> np.ndarray:
    """CHROM projection with overlap-add (paper Eqs. 3-5). `rgb` is N x 3 (R, G, B).
    Vectorised over all windows; identical to the per-window loop."""
    rgb = np.asarray(rgb, float)
    N = len(rgb)
    if L is None:
        L = min(45, max(12, N // 2))
    L = min(L, N)
    w = np.lib.stride_tricks.sliding_window_view(rgb, (L, 3))[:, 0]           # W x L x 3
    cn = w / (w.mean(axis=1, keepdims=True) + 1e-9) - 1.0
    X = 3.0 * cn[..., 0] - 2.0 * cn[..., 1]
    Y = 1.5 * cn[..., 0] + cn[..., 1] - 1.5 * cn[..., 2]
    sy = Y.std(axis=1)
    alpha = np.where(sy > 0, X.std(axis=1) / np.where(sy > 0, sy, 1.0), 0.0)
    sw = X - alpha[:, None] * Y
    sw = sw - sw.mean(axis=1, keepdims=True)
    h = np.zeros(N)
    idx = np.arange(len(sw))[:, None] + np.arange(L)[None, :]
    np.add.at(h, idx.ravel(), sw.ravel())
    return h


def suppress_artifacts(rgb: np.ndarray, k: float = ARTIFACT_MAD_K):
    """Remove motion spikes and ROI steps in the derivative domain.

    The frame-to-frame change of log(R, G, B) is mostly sensor noise plus the small pulse.
    A face movement or an ROI re-lock shows up as a change many robust SDs larger; those
    differences are set to zero and the trace is re-integrated, so a step becomes flat
    instead of a broadband edge that swamps the cardiac band. Returns (clean_rgb, fraction
    of frame pairs that were repaired).
    """
    if len(rgb) < 4:
        return rgb, 0.0
    L = np.log(np.maximum(rgb, 1e-6))
    d = np.diff(L, axis=0)
    med = np.median(d, axis=0)
    # Floor: a 0.15 % change per frame is never an artefact (it also keeps 8-bit quantisation
    # steps of a nearly constant channel from being flagged when its MAD is zero).
    mad = np.maximum(1.4826 * np.median(np.abs(d - med), axis=0), MIN_ARTIFACT_SCALE)
    bad = (np.abs(d - med) / mad > k).any(axis=1)
    d[bad] = 0.0
    clean = np.exp(np.vstack([L[:1], L[0] + np.cumsum(d, axis=0)]))
    return clean, float(np.mean(bad))


def still_tail_start(rgb: np.ndarray, fs: float, k: float = ARTIFACT_MAD_K) -> int:
    """Index where the most recent motion-free stretch begins (0 if there was no movement).

    A movement is two or more artefact-sized frame-to-frame changes within 0.5 s (a single
    flagged frame is left to suppress_artifacts). Analysing only the still stretch keeps the
    pulse from being averaged with motion that happened earlier in the buffer.
    """
    if len(rgb) < 4:
        return 0
    L = np.log(np.maximum(rgb, 1e-6))
    d = np.diff(L, axis=0)
    med = np.median(d, axis=0)
    mad = np.maximum(1.4826 * np.median(np.abs(d - med), axis=0), MIN_ARTIFACT_SCALE)
    idx = np.where((np.abs(d - med) / mad > k).any(axis=1))[0]
    near = int(0.5 * fs)
    events = [i for i in idx if np.sum(np.abs(idx - i) <= near) >= 2]
    return int(events[-1]) + 1 if events else 0


def pos_pulse(rgb: np.ndarray, fs: float) -> np.ndarray:
    """POS projection (Wang et al. 2017) with 1.6 s overlap-add windows (vectorised)."""
    rgb = np.asarray(rgb, float)
    N = len(rgb)
    L = min(N, max(4, int(round(1.6 * fs))))
    w = np.lib.stride_tricks.sliding_window_view(rgb, (L, 3))[:, 0]
    c = w / (w.mean(axis=1, keepdims=True) + 1e-9)
    s1 = c[..., 1] - c[..., 2]
    s2 = -2.0 * c[..., 0] + c[..., 1] + c[..., 2]
    sd2 = s2.std(axis=1)
    k = np.where(sd2 > 0, s1.std(axis=1) / np.where(sd2 > 0, sd2, 1.0), 0.0)
    p = s1 + k[:, None] * s2
    p = p - p.mean(axis=1, keepdims=True)
    h = np.zeros(N)
    idx = np.arange(len(p))[:, None] + np.arange(L)[None, :]
    np.add.at(h, idx.ravel(), p.ravel())
    return h


def _hp_peak(x: np.ndarray, fs: float, exclude=()):
    """Cardiac-band peak frequency of a drift-removed trace (same spectral settings as the HR path),
    skipping +-0.05 Hz around each frequency in `exclude` (lighting peaks seen on the background)."""
    hp = sosfiltfilt(butter(4, 0.6 / (fs / 2), btype="high", output="sos"), x, padlen=min(len(x) - 1, 3 * 9))
    _, freqs, psd = welch_peak(standardize(hp), fs, CARDIAC_BAND, nperseg=256)
    if len(freqs) == 0:
        return None
    f0, _ = band_peak(freqs, psd, CARDIAC_BAND, exclude)
    return f0


def trend_decomposition(x: np.ndarray):
    """Moving-average split into trend / pulsatile / first difference (paper Sec. V-F)."""
    N = len(x)
    W = min(14, max(4, N // 4))
    trend = np.convolve(x, np.ones(W) / W, mode="same")
    pulsatile = x - trend
    diff = np.diff(x, prepend=x[0])
    ratio = float(np.sum(pulsatile ** 2) / (np.sum(trend ** 2) + 1e-12))
    return trend, pulsatile, diff, ratio


RECTIFY_MIN_RATIO = 0.3     # background band RMS / skin band RMS below which nothing is removed
RECTIFY_MAX_BETA = 1.5


def rectify_illumination(tu, xu, bg_t, bg_rgb, fs):
    """Remove the part of the skin signal that the background shares (illumination rectification,
    after Li et al., CVPR 2014). Camera auto-exposure / white-balance hunting and lighting flicker
    change the wall and the face together; the pulse is only on the skin. Per channel, the
    relative change of the skin is regressed on the relative change of the background in the
    pulse band (0.6-3 Hz) and that component is subtracted. Returns (rectified N x 3, betas).

    A shared lighting change moves wall and skin by about the same relative amount (beta ~ 1,
    capped at RECTIFY_MAX_BETA). A background that is much quieter than the skin
    (< RECTIFY_MIN_RATIO of its band RMS) has no lighting change to remove; what it shares with
    the skin is then pulse leaking in (hair, shadowed skin outside the skin mask), and regressing
    on it would subtract the pulse itself, so that channel is left unchanged (beta 0).
    """
    if bg_t is None or len(bg_t) < 8 or len(tu) < 25:
        return xu, None
    bg_t = np.asarray(bg_t, float)
    bg_rgb = np.asarray(bg_rgb, float).reshape(-1, 3)
    m = (bg_t >= tu[0] - 0.5) & (bg_t <= tu[-1] + 0.5) & np.all(np.isfinite(bg_rgb), axis=1)
    if m.sum() < 8 or bg_t[m][-1] - bg_t[m][0] < 0.8 * (tu[-1] - tu[0]):
        return xu, None
    sos = butter(3, [0.6 / (fs / 2), min(3.0, 0.45 * fs) / (fs / 2)], btype="band", output="sos")
    pad = min(len(tu) - 1, 3 * 7)
    out = np.array(xu, float)
    betas = []
    for c in range(3):
        b = np.interp(tu, bg_t[m], bg_rgb[m][:, c])
        mb, mf = np.mean(b), np.mean(out[:, c])
        if mb <= 0 or mf <= 0:
            betas.append(0.0)
            continue
        bf = sosfiltfilt(sos, b / mb - 1.0, padlen=pad)
        ff = sosfiltfilt(sos, out[:, c] / mf - 1.0, padlen=pad)
        den = float(np.dot(bf, bf))
        if den <= 0 or np.std(bf) < RECTIFY_MIN_RATIO * np.std(ff):
            betas.append(0.0)
            continue
        beta = float(np.clip(np.dot(ff, bf) / den, 0.0, RECTIFY_MAX_BETA))
        out[:, c] = mf * (out[:, c] / mf - beta * bf)
        betas.append(beta)
    return out, betas


def background_peaks(freqs, psd, bg_t, bg_rgb, tu, fs, skin_g=None):
    """(rejected, wall): skin-spectrum peaks at least as strong on the background, and all
    distinct background peaks (Hz).

    The background (wall, curtain: no blood) sees the same illumination as the skin. A peak in
    the skin spectrum that is equally present there is lighting flicker or camera exposure
    hunting, not the pulse. Both spectra are normalised to their in-band totals.

    skin_g (skin green on tu): when the background's band RMS is below RECTIFY_MIN_RATIO of the
    skin's, the background carries no lighting change and its only rhythm is pulse leaking in
    from skin outside the mask; nothing is rejected then (normalised, that leak would look as
    strong as the skin's pulse and reject the true heart rate).
    """
    if bg_t is None or len(bg_t) < 8 or len(freqs) < 3:
        return [], []
    bg_t = np.asarray(bg_t, float)
    bg_rgb = np.asarray(bg_rgb, float).reshape(-1, 3)
    m = (bg_t >= tu[0] - 0.5) & (bg_t <= tu[-1] + 0.5)
    if m.sum() < 8 or bg_t[m][-1] - bg_t[m][0] < 0.8 * (tu[-1] - tu[0]):
        return [], []
    g = np.interp(tu, bg_t[m], bg_rgb[m][:, 1])
    g = g / max(np.mean(g), 1e-9) - 1.0
    sos = butter(4, 0.6 / (fs / 2), btype="high", output="sos")
    hp = sosfiltfilt(sos, g, padlen=min(len(g) - 1, 3 * 9))
    if skin_g is not None and len(skin_g) == len(g):
        sg = np.asarray(skin_g, float)
        sg = sosfiltfilt(sos, sg / max(np.mean(sg), 1e-9) - 1.0, padlen=min(len(sg) - 1, 3 * 9))
        if np.std(hp) < RECTIFY_MIN_RATIO * np.std(sg):
            return [], []
    _, bf, bp = welch_peak(standardize(hp), fs, CARDIAC_BAND, nperseg=256)
    band = (freqs >= CARDIAC_BAND[0]) & (freqs <= CARDIAC_BAND[1])
    bband = (bf >= CARDIAC_BAND[0]) & (bf <= CARDIAC_BAND[1])
    if not band.any() or not bband.any() or psd[band].sum() <= 0 or bp[bband].sum() <= 0:
        return [], []
    face_n = psd / psd[band].sum()
    bg_n = np.interp(freqs, bf, bp / bp[bband].sum())
    med = np.median(bg_n[band])
    rejected = []
    idx = np.where(band)[0]
    for i in idx[1:-1]:
        if psd[i] >= psd[i - 1] and psd[i] >= psd[i + 1]:
            near = np.abs(freqs - freqs[i]) <= 0.05
            b = bg_n[near].max()
            if b >= BG_REJECT_RATIO * face_n[i] and b >= BG_PEAK_FACTOR * med:
                rejected.append(float(freqs[i]))
    wall = [float(freqs[i]) for i in idx[1:-1]
            if bg_n[i] >= bg_n[i - 1] and bg_n[i] >= bg_n[i + 1] and bg_n[i] >= BG_PEAK_FACTOR * med]
    return rejected, wall


def estimate_optical(t, rgb, method: str = "chrom", fs: float = FS_OPT,
                     spo2_calibration: dict | None = None, prior_hr: float | None = None,
                     bg_t=None, bg_rgb=None) -> dict:
    """Optical HR / RR / SpO2-ratio estimate from timestamped ROI means.

    t   : frame timestamps in seconds (only frames that passed the face gate)
    rgb : N x 3 array of ROI mean (R, G, B)
    method: "chrom" (default; the configuration benchmarked on UBFC-rPPG), "pos" or "green"
    bg_t, bg_rgb: optional background (non-skin) mean RGB over time, for lighting rejection
    prior_hr: previous accepted HR (beats/min) for peak tracking, or None
    Returns a dict; quantities that cannot be estimated are None. `hr_ok` is True
    when the HR estimate passes the SNR and coverage gates.
    """
    out = dict(hr=None, hr_ok=False, tracked=False, f0=None, snr=None, quality=0.0, rr=None, rr_quality=0.0,
               spo2_ratio=None, spo2=None, coverage=0.0,
               segment_s=0.0, fs=fs, bvp=np.array([]), resp=np.array([]),
               freqs=np.array([]), psd=np.array([]),
               trend=np.array([]), pulsatile=np.array([]), diff=np.array([]), motion_ratio=None,
               artifact_frac=0.0, hr_pos=None, hr_green=None, hr_chrom=None, consensus=0, still_trimmed_s=0.0,
               rgb_norm=np.empty((0, 3)), bg_rejected=[], method=method, rr_estimate=None, illum_beta=None)
    tu, xu = resample_uniform(t, rgb, fs)
    if len(tu) < 8:
        return out
    start = still_tail_start(xu, fs)
    if start and (len(xu) - start) / fs >= MIN_STILL_S:
        tu, xu = tu[start:], xu[start:]          # use only the still stretch after the last movement
        out["still_trimmed_s"] = float(start / fs)
    xu, out["artifact_frac"] = suppress_artifacts(xu)
    xu, out["illum_beta"] = rectify_illumination(tu, xu, bg_t, bg_rgb, fs)
    out["rgb_norm"] = xu / np.maximum(np.mean(xu, axis=0), 1e-9) - 1.0     # relative colour change per channel
    seg_s = tu[-1] - tu[0]
    out["segment_s"] = float(seg_s)
    t = np.asarray(t, dtype=float)
    out["coverage"] = segment_coverage(t[t >= tu[0] - 1e-6])
    if len(tu) < 25:
        return out

    extractors = {
        "pos": lambda x: pos_pulse(x, fs),
        "chrom": lambda x: chrom_pulse(x),
        "green": lambda x: -(x[:, 1] - np.mean(x[:, 1])),   # blood absorbs green: invert so systole is positive
    }
    pulse = extractors[method](xu)
    bvp = standardize(bandpass(pulse, fs, CARDIAC_BAND, 3))
    out["bvp"] = bvp
    out["trend"], out["pulsatile"], out["diff"], out["motion_ratio"] = trend_decomposition(bvp)

    if seg_s >= MIN_SEG_HR_S:
        # SNR is evaluated on the un-band-passed pulse so the harmonic is not filtered out.
        # Drift below 0.6 Hz is removed first so it cannot leak into the bottom of the
        # cardiac band; harmonics stay in for the SNR.
        hp = sosfiltfilt(butter(4, 0.6 / (fs / 2), btype="high", output="sos"), pulse,
                         padlen=min(len(pulse) - 1, 3 * 9))
        _, freqs, psd = welch_peak(standardize(hp), fs, CARDIAC_BAND, nperseg=256)
        prior_hz = None if prior_hr is None else prior_hr / 60.0
        # Peaks that are equally strong on the background are lighting: excluded from the search.
        rejected, wall = background_peaks(freqs, psd, bg_t, bg_rgb, tu, fs, skin_g=xu[:, 1])
        out["bg_rejected"] = [round(60.0 * fr, 1) for fr in rejected]
        f0, tracked = tracked_peak(freqs, psd, CARDIAC_BAND, prior_hz, exclude=rejected)
        if f0 is not None:
            snr = dehaan_snr(freqs, psd, f0)
            # Consensus: the two other pulse extractors must see the same peak. Noise and motion
            # give method-specific peaks; a real pulse is common to all of them.
            peaks = {m: (f0 if m == method else _hp_peak(fn(xu), fs, rejected)) for m, fn in extractors.items()}
            near = lambda f: f is not None and abs(60.0 * (f - f0)) <= AGREE_BPM
            consensus = sum(int(near(peaks[m])) for m in extractors if m != method)
            bpm = lambda f: None if f is None else 60.0 * f
            out.update(hr=60.0 * f0, f0=f0, freqs=freqs, psd=psd, snr=snr, tracked=tracked,
                       quality=spectral_concentration(freqs, psd, f0),
                       hr_pos=bpm(peaks["pos"]), hr_chrom=bpm(peaks["chrom"]),
                       hr_green=bpm(peaks["green"]), consensus=consensus,
                       hr_ok=bool(np.isfinite(snr) and snr >= MIN_SNR_HR_DB
                                  and out["coverage"] >= MIN_COVERAGE
                                  and out["artifact_frac"] <= MAX_ARTIFACT_FRAC
                                  and consensus >= CONSENSUS_MIN))

        # SpO2 ratio-of-ratios from band-passed AC (paper Eq. 13); uncalibrated unless A, B given.
        r_ac = np.std(bandpass(xu[:, 0], fs, CARDIAC_BAND, 3))
        b_ac = np.std(bandpass(xu[:, 2], fs, CARDIAC_BAND, 3))
        r_dc, b_dc = np.mean(xu[:, 0]), np.mean(xu[:, 2])
        if b_ac > 0 and r_dc > 0 and b_dc > 0:
            ratio = (r_ac / r_dc) / (b_ac / b_dc)
            out["spo2_ratio"] = float(ratio)
            if spo2_calibration and "A" in spo2_calibration and "B" in spo2_calibration:
                out["spo2"] = float(spo2_calibration["A"] - spo2_calibration["B"] * ratio)

    green = xu[:, 1]
    out["resp"] = standardize(bandpass(green - np.mean(green), fs, RESP_BAND, 2))
    out["rr_quality"] = 0.0
    if seg_s >= MIN_SEG_RR_S:
        # Peak search on the un-band-passed green trace so the in-band power share is meaningful.
        g = standardize(green - np.mean(green))
        fr, rfreqs, rpsd = welch_peak(g, fs, RESP_BAND, nperseg=len(g))
        if fr is not None:
            # Half-width of one nominal resolution bin (1/T) around the peak.
            q = spectral_concentration(rfreqs, rpsd, fr, band=(0.05, 1.0), half=1.0 / seg_s)
            out["rr_quality"] = q
            out["rr"] = 60.0 * fr if q >= MIN_Q_RR else None
            out["rr_estimate"] = 60.0 * fr                  # shown as low confidence when rr is None
    return out


# ================================================================ acoustic
def pcg_envelope(x16k: np.ndarray, fs: int = FS_AUDIO):
    """Band-pass 25-400 Hz, decimate to 1 kHz, Shannon energy smoothed over 20 ms.

    Returns (band-passed 1 kHz signal, envelope at 1 kHz, envelope at 100 Hz).
    """
    x = np.asarray(x16k, dtype=float)
    x = x - np.mean(x)
    sos = butter(4, [PCG_BAND[0] / (fs / 2), PCG_BAND[1] / (fs / 2)], btype="band", output="sos")
    xb = sosfiltfilt(sos, x)
    x1k = resample_poly(xb, 1, fs // FS_PCG)
    peak = np.max(np.abs(x1k))
    if peak <= 0:
        return x1k, np.zeros_like(x1k), np.zeros(len(x1k) // 10)
    xn = x1k / peak
    se = -(xn ** 2) * np.log(xn ** 2 + 1e-12)                  # Shannon energy (Eq. 10)
    win = int(0.020 * FS_PCG)
    env1k = np.convolve(se, np.ones(win) / win, mode="same")   # 20 ms smoothing, hop 1 ms
    env100 = env1k[::10]                                       # 10 ms hop
    return x1k, standardize(env1k), standardize(env100)


def estimate_acoustic(x16k: np.ndarray, t0: float = 0.0, fs: int = FS_AUDIO) -> dict:
    """PCG heart rate by envelope autocorrelation (paper Eq. 11) and S1 beat times.

    t0 is the timestamp (s) of the first sample, so beat times are absolute.
    """
    out = dict(hr=None, rho=0.0, beats=np.array([]), rms=0.0, x1k=np.array([]), env=np.array([]),
               beat_consistency=0.0)
    if len(x16k) < fs * 3:
        return out
    out["rms"] = float(np.sqrt(np.mean((np.asarray(x16k, float) - np.mean(x16k)) ** 2)))
    x1k, env1k, env100 = pcg_envelope(x16k, fs)
    out["x1k"], out["env"] = x1k, env1k

    e = env100 - np.mean(env100)
    acf = np.correlate(e, e, mode="full")[len(e) - 1:]
    if acf[0] <= 0:
        return out
    acf = acf / acf[0]
    lo, hi = int(HR_LAG_S[0] * 100), int(HR_LAG_S[1] * 100)
    if hi >= len(acf):
        return out
    k = lo + int(np.argmax(acf[lo:hi + 1]))
    tau = parabolic_peak(acf, k) / 100.0
    out["hr"] = 60.0 / tau
    out["rho"] = float(np.clip(acf[k], 0.0, 1.0))

    # Beat fiducials: the Shannon energy de-emphasizes the loudest sound, so S1 is
    # located on the Hilbert amplitude envelope instead (20 ms smoothing, 1 ms
    # resolution), taking the largest peak within each 0.6*tau neighbourhood.
    amp = np.abs(hilbert(x1k))
    win = int(0.020 * FS_PCG)
    amp = np.convolve(amp, np.ones(win) / win, mode="same")
    dist = max(1, int(0.6 * tau * FS_PCG))
    peaks, _ = find_peaks(amp, distance=dist, height=np.median(amp))
    out["beats"] = t0 + peaks / FS_PCG
    # Real heart sounds give S1 peaks spaced by the rhythm period; noise bursts that happen to
    # make the envelope autocorrelation peak do not.
    ibi = np.diff(peaks) / FS_PCG
    if len(ibi) >= 2:
        out["beat_consistency"] = float(np.mean(np.abs(ibi - tau) <= 0.15 * tau))
    return out


def clean_ibis(beat_times: np.ndarray):
    """Inter-beat intervals with physiological and median-deviation rejection."""
    if len(beat_times) < 3:
        return np.array([])
    ibi = np.diff(np.sort(beat_times))
    ibi = ibi[(ibi >= 0.4) & (ibi <= 1.5)]
    if len(ibi) < 2:
        return np.array([])
    med = np.median(ibi)
    return ibi[np.abs(ibi - med) <= 0.2 * med]


def rmssd_ms(beat_times: np.ndarray, min_intervals: int = 20):
    """RMSSD (ms) over successive clean inter-beat intervals; None if too few."""
    ibi = clean_ibis(beat_times)
    if len(ibi) < min_intervals:
        return None
    return float(1000.0 * np.sqrt(np.mean(np.diff(ibi) ** 2)))


# ================================================================ fusion
def fuse_hr(hr_o, w_o, hr_a, w_a, delta: float = FUSION_DELTA_BPM) -> dict:
    """Quality-weighted fusion with agreement gate (paper Eq. 12).

    Weights must already include the gating terms (g_o, g_a). Returns
    {hr, source, w_o, w_a, disagreement} with hr None if no channel is usable.
    """
    o_ok = hr_o is not None and w_o > 0
    a_ok = hr_a is not None and w_a > 0
    res = dict(hr=None, source=None, w_o=float(w_o if o_ok else 0.0),
               w_a=float(w_a if a_ok else 0.0), disagreement=False)
    if o_ok and a_ok:
        if abs(hr_o - hr_a) <= delta:
            res.update(hr=(w_o * hr_o + w_a * hr_a) / (w_o + w_a), source="fused")
        else:
            res["disagreement"] = True
            if w_o >= w_a:
                res.update(hr=hr_o, source="optical")
            else:
                res.update(hr=hr_a, source="acoustic")
    elif o_ok:
        res.update(hr=hr_o, source="optical")
    elif a_ok:
        res.update(hr=hr_a, source="acoustic")
    return res


# ================================================================ ensemble spectrum + HR tracker
# Continuous HR with a confidence, so the display always has a best estimate:
#  * ensemble: every skin patch x every extractor (CHROM, POS, green) gives a drift-removed Welch
#    spectrum normalised to unit in-band power; the median across them is robust to a bad patch or
#    method (patch-wise median fusion as in pyVHR, Boccignone et al., PeerJ Comput. Sci. 2022);
#  * tracker: a discrete Bayes filter over a 0.5 BPM grid (spectral peak tracking in the spirit of
#    TROIKA, Zhang et al., IEEE TBME 2015): HR drifts by about TRACKER_SIGMA_BPM per 2 s, a small
#    floor allows genuine jumps, and the posterior mass within +-3 BPM is the confidence.
TRACK_GRID_BPM = np.arange(45.0, 150.0 + 1e-9, 0.5)
TRACKER_SIGMA_BPM = 3.0       # expected HR drift per 2 s update (1 SD)
TRACKER_FLOOR = 0.02          # share of probability that may jump anywhere (sudden real changes)
TRACKER_GAMMA = 1.5           # sharpening of the spectral likelihood
TRACKER_HIGH_CONF = 0.8       # simulated (30 s windows, 2 s updates): pure noise reaches this 0.0 % of the time;
                              # a 0.3 % pulse 57 %, a 0.6 % pulse 90 %; tracked MAE 1.5 / 1.1 BPM over all windows
TRACKER_RESET_S = 10.0        # no update for this long: forget the track


def _norm_band_spectrum(x: np.ndarray, fs: float):
    """Drift-removed Welch spectrum of a pulse trace on TRACK_GRID_BPM, normalised to sum 1."""
    if len(x) < 25 or not np.all(np.isfinite(x)) or np.std(x) == 0:
        return None
    hp = sosfiltfilt(butter(4, 0.6 / (fs / 2), btype="high", output="sos"), x, padlen=min(len(x) - 1, 3 * 9))
    _, freqs, psd = welch_peak(standardize(hp), fs, CARDIAC_BAND, nperseg=256)
    s = np.interp(TRACK_GRID_BPM / 60.0, freqs, psd)
    tot = s.sum()
    return s / tot if tot > 0 else None


def ensemble_spectrum(t, patches_rgb, fs: float = FS_OPT, bg_t=None, bg_rgb=None):
    """Median of normalised spectra over skin patches x extractors for one analysis window.

    t: frame times; patches_rgb: N x P x 3 (P skin patches; P = 1 for a single summed region).
    Returns (spectrum on TRACK_GRID_BPM or None, number of spectra fused, lighting peaks in BPM).
    """
    t = np.asarray(t, float)
    pr = np.asarray(patches_rgb, float)
    if pr.ndim == 2:
        pr = pr[:, None, :]
    if len(t) < 25 or pr.shape[0] != len(t):
        return None, 0, []
    whole = np.nanmean(pr, axis=1)
    tu, xu = resample_uniform(t, whole, fs)
    if len(tu) < 25:
        return None, 0, []
    start = still_tail_start(xu, fs)
    keep = start if start and (len(xu) - start) / fs >= MIN_STILL_S else 0
    t0 = tu[keep]
    if tu[-1] - t0 < MIN_SEG_HR_S:
        return None, 0, []
    m = t >= t0 - 1e-6
    extract = {"chrom": lambda x: chrom_pulse(x), "pos": lambda x: pos_pulse(x, fs),
               "green": lambda x: -(x[:, 1] - np.mean(x[:, 1]))}
    spectra = []
    for k in range(pr.shape[1]):
        ok = m & np.all(np.isfinite(pr[:, k, :]), axis=1)
        if ok.sum() < 25:
            continue
        tk, xk = resample_uniform(t[ok], pr[ok, k, :], fs)
        if len(tk) < 25:
            continue
        xk, _ = suppress_artifacts(xk)
        xk, _ = rectify_illumination(tk, xk, bg_t, bg_rgb, fs)
        for fn in extract.values():
            s = _norm_band_spectrum(fn(xk), fs)
            if s is not None:
                spectra.append(s)
    if not spectra:
        return None, 0, []
    spec = np.median(np.array(spectra), axis=0)
    # lighting: peaks of the fused spectrum that are as strong on the background
    tu2 = np.arange(t0, t[-1], 1.0 / fs)
    rejected = []
    if len(tu2) > 25:
        g = np.nanmean(pr[:, :, 1], axis=1)
        okg = m & np.isfinite(g)
        skin_g = np.interp(tu2, t[okg], g[okg]) if okg.sum() > 25 else None
        rejected, _ = background_peaks(TRACK_GRID_BPM / 60.0, spec, bg_t, bg_rgb, tu2, fs, skin_g=skin_g)
    for fr in rejected:
        spec = spec.copy()
        spec[np.abs(TRACK_GRID_BPM / 60.0 - fr) <= EXCLUDE_HZ] *= 0.05
    tot = spec.sum()
    return (spec / tot if tot > 0 else None), len(spectra), [round(60.0 * f, 1) for f in rejected]


class HRTracker:
    """Online Bayes filter over TRACK_GRID_BPM fed with ensemble spectra."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.post = None
        self.t = None

    def update(self, spectrum, t):
        """Returns (hr_bpm, confidence 0..1) or (None, 0.0)."""
        if spectrum is None:
            if self.t is not None and t - self.t > TRACKER_RESET_S:
                self.reset()
            return self.estimate()
        like = np.power(np.maximum(spectrum, 1e-12), TRACKER_GAMMA)
        like = like / like.sum()
        if self.post is None or (self.t is not None and t - self.t > TRACKER_RESET_S):
            post = like
        else:
            dt = max(0.5, t - self.t)
            sigma = TRACKER_SIGMA_BPM * np.sqrt(dt / 2.0) / 0.5          # in grid steps
            half = int(np.ceil(4 * sigma))
            k = np.exp(-0.5 * (np.arange(-half, half + 1) / sigma) ** 2)
            pred = np.convolve(self.post, k / k.sum(), mode="same")
            pred = (1 - TRACKER_FLOOR) * pred / pred.sum() + TRACKER_FLOOR / len(pred)
            post = pred * like
        self.post = post / post.sum()
        self.t = t
        return self.estimate()

    def estimate(self):
        if self.post is None:
            return None, 0.0
        i = int(np.argmax(self.post))
        hr = float(TRACK_GRID_BPM[i])
        conf = float(self.post[np.abs(TRACK_GRID_BPM - hr) <= 3.0].sum())
        return hr, conf


def camera_rmssd(bvp: np.ndarray, fs: float, hr_bpm: float | None, min_beats: int = 10):
    """Exploratory RMSSD (ms) from systolic peaks of the camera pulse wave.

    The wave is upsampled 4x (cubic) and peaks are located with sub-sample (parabolic) precision,
    but at 15 Hz video beat timing is still coarse: report as exploratory only.
    """
    if hr_bpm is None or len(bvp) < 4 * fs:
        return None
    from scipy.interpolate import CubicSpline
    up = 4
    tt = np.arange(len(bvp)) / fs
    tu = np.arange(0, tt[-1], 1.0 / (fs * up))
    y = CubicSpline(tt, bvp)(tu)
    period = 60.0 / hr_bpm
    pk, _ = find_peaks(y, distance=max(1, int(0.6 * period * fs * up)), prominence=0.3 * np.std(y))
    if len(pk) < min_beats:
        return None
    times = np.array([tu[p] + (parabolic_peak(y, p) - p) / (fs * up) if 0 < p < len(y) - 1 else tu[p] for p in pk])
    ibi = np.diff(times)
    ok = np.abs(ibi - period) <= 0.2 * period
    ibi = ibi[ok]
    if len(ibi) < min_beats - 1:
        return None
    return float(1000.0 * np.sqrt(np.mean(np.diff(ibi) ** 2)))
