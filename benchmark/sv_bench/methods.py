"""Signal-processing baselines and shared HR post-processing.

GREEN, CHROM and POS are ported line for line from rPPG-Toolbox (unsupervised_methods/,
commit b7500b8) so the baselines match the published reference implementations; the only
change is np.mat -> np.asarray (np.mat no longer exists in NumPy 2). Each takes an N x 3
RGB trace (spatial mean of the skin/face region per frame) and returns a BVP signal.

HR from any BVP follows the toolbox evaluation: smoothness-priors detrending (lambda = 100),
first-order Butterworth band-pass and the periodogram peak, with the band 0.75-2.5 Hz
(45-150 beats/min) that the toolbox paper recommends. Ground truth is processed identically.
"""
import math

import numpy as np
from scipy import signal, sparse
from scipy.sparse.linalg import spsolve

HR_BAND = (0.75, 2.5)


def detrend(x, lam=100.0):
    """Tarvainen et al. smoothness-priors detrending (same result as the toolbox's dense inverse)."""
    x = np.asarray(x, float)
    n = len(x)
    if n < 3:
        return x - x.mean()
    d = sparse.diags([np.ones(n - 2), -2 * np.ones(n - 2), np.ones(n - 2)], [0, 1, 2], shape=(n - 2, n))
    a = (sparse.identity(n) + lam ** 2 * (d.T @ d)).tocsc()
    return x - spsolve(a, x)


def green(rgb, fs):
    return np.asarray(rgb, float)[:, 1].copy()


def chrom(rgb, fs):
    """De Haan & Jeanne 2013 (toolbox CHROME_DEHAAN)."""
    RGB = np.asarray(rgb, float)
    LPF, HPF, WinSec = 0.7, 2.5, 1.6
    FN = RGB.shape[0]
    NyquistF = 0.5 * fs
    B, A = signal.butter(3, [LPF / NyquistF, HPF / NyquistF], 'bandpass')
    WinL = math.ceil(WinSec * fs)
    if WinL % 2:
        WinL += 1
    NWin = math.floor((FN - WinL // 2) / (WinL // 2))
    WinS, WinM, WinE = 0, WinL // 2, WinL
    S = np.zeros((WinL // 2) * (NWin + 1))
    for _ in range(NWin):
        RGBNorm = RGB[WinS:WinE] / np.mean(RGB[WinS:WinE], axis=0)
        Xs = 3 * RGBNorm[:, 0] - 2 * RGBNorm[:, 1]
        Ys = 1.5 * RGBNorm[:, 0] + RGBNorm[:, 1] - 1.5 * RGBNorm[:, 2]
        Xf = signal.filtfilt(B, A, Xs, axis=0)
        Yf = signal.filtfilt(B, A, Ys)
        SWin = (Xf - (np.std(Xf) / np.std(Yf)) * Yf) * signal.windows.hann(WinL)
        S[WinS:WinM] = S[WinS:WinM] + SWin[:WinL // 2]
        S[WinM:WinE] = SWin[WinL // 2:]
        WinS, WinM, WinE = WinM, WinM + WinL // 2, WinM + WinL
    return S[:FN]                       # (WinL/2)*(NWin+1) samples, as in the toolbox


def pos(rgb, fs):
    """Wang et al. 2017 (toolbox POS_WANG)."""
    RGB = np.asarray(rgb, float)
    N = RGB.shape[0]
    H = np.zeros(N)
    l = math.ceil(1.6 * fs)
    P = np.array([[0, 1, -1], [-2, 1, 1]])
    for n in range(N):
        m = n - l
        if m >= 0:
            Cn = (RGB[m:n] / np.mean(RGB[m:n], axis=0)).T
            S = P @ Cn
            h = S[0] + (np.std(S[0]) / np.std(S[1])) * S[1]
            H[m:n] += h - np.mean(h)
    BVP = detrend(H, 100)
    b, a = signal.butter(1, [0.75 / fs * 2, 3 / fs * 2], btype='bandpass')
    return signal.filtfilt(b, a, BVP)


BASELINES = {'GREEN': green, 'CHROM': chrom, 'POS': pos}


def postprocess(bvp, fs, band=HR_BAND):
    """Toolbox evaluation post-processing: detrend (lambda 100) + 1st-order band-pass."""
    x = detrend(np.asarray(bvp, float), 100)
    b, a = signal.butter(1, [band[0] / fs * 2, band[1] / fs * 2], btype='bandpass')
    return signal.filtfilt(b, a, x)


def fft_hr(bvp, fs, band=HR_BAND, nfft_min=4096):
    """Periodogram peak in the HR band (beats/min). Zero-padding to >= nfft_min for all methods alike."""
    x = np.asarray(bvp, float)
    if len(x) < 4 or not np.all(np.isfinite(x)) or np.std(x) == 0:
        return None
    nfft = max(nfft_min, 1 << (len(x) - 1).bit_length())
    f, p = signal.periodogram(x, fs=fs, nfft=nfft, detrend=False)
    m = (f >= band[0]) & (f <= band[1])
    return float(f[m][np.argmax(p[m])] * 60.0)
