"""Figures for the graph guide: the dashboard's own telemetry, computed by replaying a recorded
webcam clip (benchmark/webcam_runs/20261016_213519) through the live engine."""
import os, sys
import numpy as np, cv2
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'backend'))
import rppg_engine as re_, vitals_dsp as dsp  # noqa: E402
OUT = os.path.join(os.path.dirname(__file__), 'figs')
RUN = os.path.join(ROOT, 'benchmark', 'webcam_runs', '20261016_213519')
G, O, R, B, GR = '#0F6A4A', '#D98C00', '#B85430', '#2E86C1', '#6B8E23'
plt.rcParams.update({'font.size': 8, 'axes.titlesize': 9, 'axes.spines.top': False, 'axes.spines.right': False})


def save(fig, name):
    fig.tight_layout(); fig.savefig(os.path.join(OUT, name), dpi=200); plt.close(fig)


def replay():
    times = np.load(os.path.join(RUN, 'webcam_times.npy'))
    eng = re_.RPPGEngine(update_interval_s=2.0); eng.async_estimate = False
    cap = cv2.VideoCapture(os.path.join(RUN, 'webcam.avi')); i = 0; hist = []; frame = None
    while True:
        ok, f = cap.read()
        if not ok or i >= len(times): break
        t = float(times[i]); i += 1
        eng.process_frame(f, t)
        if i % 30 == 0:
            tel = eng.telemetry()
            hist.append((t, tel.get('optical_hr'), tel.get('optical_hr_ok'), tel.get('cardiac_snr'), tel.get('snr_gate_db'),
                         tel.get('optical_consensus'), tel.get('optical_hr_pos'), tel.get('optical_hr_green'),
                         tel.get('tracked_hr'), tel.get('tracked_conf')))
        if i == 700: frame = (f.copy(), list(eng.current_rois or []))
    return eng.telemetry(), hist, frame


def main():
    tel, hist, frame = replay()
    fs = tel.get('analysis_fs') or 15.0
    ax_t = lambda n: (np.arange(n) - n + 1) / fs

    # ROI frame
    if frame:
        img, rois = frame
        for x, y, w, h in rois: cv2.rectangle(img, (x, y), (x + w, y + h), (74, 106, 15), 2)
        cv2.imwrite(os.path.join(OUT, 'roi.jpg'), img)

    # RGB
    rgb = tel['rgb_norm']; fig, ax = plt.subplots(figsize=(6.5, 2.2))
    for c, col, nm in zip(rgb, ('#C0392B', '#27AE60', '#2E86C1'), 'RGB'):
        ax.plot(ax_t(len(c)), c, color=col, lw=0.8, label={'R': 'Red', 'G': 'Green', 'B': 'Blue'}[nm])
    ax.set(title='Skin colour change (gated skin boxes, motion-suppressed)', xlabel='Time (s)', ylabel='Change from mean (%)')
    ax.legend(ncol=3, fontsize=7, frameon=False); save(fig, 'rgb.png')

    # pulse + resp
    fig, axs = plt.subplots(2, 1, figsize=(6.5, 3.4))
    axs[0].plot(ax_t(len(tel['bvp_wave'])), tel['bvp_wave'], color=G, lw=1.1)
    axs[0].set(title='Recovered pulse (CHROM, 0.75-2.5 Hz)', ylabel='z-score')
    axs[1].plot(ax_t(len(tel['resp_wave'])), tel['resp_wave'], color=R, lw=1.1)
    axs[1].set(title='Respiratory waveform (green, 0.15-0.40 Hz)', xlabel='Time (s)', ylabel='z-score'); save(fig, 'pulse_resp.png')

    # PSD
    f, p = np.array(tel['psd_freqs']), np.array(tel['psd_power']); f0 = tel.get('cardiac_peak_freq')
    fig, ax = plt.subplots(figsize=(6.5, 2.4))
    ax.axvspan(0.75, 2.5, color=G, alpha=0.07, label='cardiac band 45-150 BPM')
    ax.plot(f, p, color=G, lw=1.2)
    if f0:
        ok = tel.get('optical_hr_ok'); ax.axvline(f0, color=G if ok else R, ls=':', lw=1.3)
        ax.text(f0, ax.get_ylim()[1], f' {60 * f0:.1f} BPM ({"accepted" if ok else "rejected"})', color=G if ok else R, va='top', fontsize=7)
    ax.set(title='rPPG power spectral density (Welch)', xlabel='Frequency (Hz)', ylabel='Relative power (dB)')
    ax.legend(fontsize=7, frameon=False, loc='lower left'); save(fig, 'psd.png')

    # decomposition
    fig, ax = plt.subplots(figsize=(6.5, 2.2)); n = len(tel['trend_wave'])
    ax.plot(ax_t(n), tel['trend_wave'], color=G, lw=1.1, label='Trend (moving average)')
    ax.plot(ax_t(n), tel['pulsatile_wave'], color=O, lw=0.8, label='Pulsatile (signal - trend)')
    ax.plot(ax_t(n), tel['diff_wave'], color=R, lw=0.5, label='First difference')
    ax.set(title='Moving-average decomposition', xlabel='Time (s)', ylabel='z-score'); ax.legend(ncol=3, fontsize=7, frameon=False)
    save(fig, 'decomp.png')

    # history: HR, SNR, methods
    H = np.array([[np.nan if v is None else float(v) for v in h] for h in hist])
    t = H[:, 0] - H[-1, 0]
    fig, ax = plt.subplots(figsize=(6.5, 2.4))
    acc = H[:, 2] == 1
    ax.plot(t[acc], H[acc, 1], 'o', color=G, ms=4, label='Camera estimate (accepted)')
    ax.plot(t[~acc], H[~acc, 1], 'o', mfc='none', mec='#9A9A90', ms=4, label='Camera estimate (rejected)')
    hi = H[:, 9] >= 0.8
    ax.plot(t, np.where(hi, H[:, 8], np.nan), ':', color=G, lw=1.6, label='Tracked (high confidence)')
    ax.plot(t, np.where(~hi, H[:, 8], np.nan), ':', color=O, lw=1.3, label='Tracked (low confidence)')
    ax.set(title='Heart rate history', xlabel='Time (s)', ylabel='HR (BPM)', ylim=(40, 150))
    ax.legend(ncol=2, fontsize=7, frameon=False); save(fig, 'hr_history.png')

    fig, ax = plt.subplots(figsize=(6.5, 2.4)); ax2 = ax.twinx()
    ax.plot(t, H[:, 3], color='#3A3A3A', lw=1.2, label='SNR'); ax.plot(t, H[:, 4], '--', color=R, lw=1.1, label='Gate (SNR)')
    ax2.step(t, H[:, 5], where='post', color=O, lw=1); ax2.fill_between(t, 0, np.nan_to_num(H[:, 5]), step='post', color=O, alpha=0.12)
    ax2.set_ylim(-0.2, 2.6); ax2.set_ylabel('Methods agreeing'); ax2.spines['right'].set_visible(True)
    ax.set(title='Signal quality vs acceptance gate', xlabel='Time (s)', ylabel='Pulse SNR (dB)', ylim=(-12, 6))
    ax.legend(fontsize=7, frameon=False, loc='lower left'); save(fig, 'quality.png')

    fig, ax = plt.subplots(figsize=(6.5, 2.2))
    for k, col, nm, ls in ((1, G, 'CHROM', '-'), (6, O, 'POS', '-'), (7, GR, 'Green', ':')):
        ax.plot(t, H[:, k], ls, marker='o', ms=2.5, color=col, lw=1, label=nm)
    ax.set(title='Method agreement: CHROM vs POS vs green', xlabel='Time (s)', ylabel='HR (BPM)', ylim=(40, 150))
    ax.legend(ncol=3, fontsize=7, frameon=False); save(fig, 'methods_time.png')

    # standardized pulse (Signal Analysis, larger view)
    fig, ax = plt.subplots(figsize=(6.5, 2.0))
    ax.plot(ax_t(len(tel['bvp_wave'])), tel['bvp_wave'], color='#6E6E66', lw=1.0)
    ax.set(title='Standardized pulse signal', xlabel='Time (s)', ylabel='z-score'); save(fig, 'detrended.png')

    # telemetry strip values exactly as app.js formats them
    import json
    f0 = tel.get('cardiac_peak_freq')
    strip = {
        'CARDIAC PEAK (f0)': f'{f0:.2f} Hz ({60 * f0:.1f} BPM)' if f0 else '-- Hz (-- BPM)',
        'SNR (DE HAAN)': '-- dB' if tel.get('cardiac_snr') is None else f"{tel['cardiac_snr']:+.1f} dB",
        'SPECTRAL CONCENTRATION (Q)': f"{100 * tel['optical_quality']:.1f}%" if tel.get('optical_quality') else '--%',
        'RESPIRATION (fr)': '-- Hz (-- BrPM)' if tel.get('optical_rr') is None else
            f"{tel['optical_rr'] / 60:.3f} Hz ({tel['optical_rr']:.1f} BrPM)",
        'METHODS AGREEING | MOTION': '--' if tel.get('optical_hr') is None else
            f"{tel.get('optical_consensus')}/2 | {100 * (tel.get('artifact_frac') or 0):.0f}% REPAIRED"
            + (f" | {tel['still_trimmed_s']:.0f} s SKIPPED" if tel.get('still_trimmed_s') else ''),
        'VIDEO SOURCE (MEASURED FPS)': 'Recorded webcam clip (replayed)',
        'accepted': bool(tel.get('optical_hr_ok')),
        'rr_estimate': tel.get('optical_rr_estimate'),
    }
    json.dump(strip, open(os.path.join(OUT, 'strip.json'), 'w'), indent=1)

    audio_figures()
    overview_figure()
    pipeline_figure()
    print('figures written to', OUT)


AUDIO_SESSION = os.path.join(ROOT, 'data', 'sessions', '20261014_151513_AUTHOR01')


def audio_figures():
    """PCG waveform and spectrogram exactly as AcousticEngine.display_payload (last 4 s)."""
    import wave
    from scipy.signal import stft
    w = wave.open(os.path.join(AUDIO_SESSION, 'audio.wav')); fs = w.getframerate()
    x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(float)
    seg = x[int(40 * fs):int(44 * fs)]                       # a 4 s stretch, like the UI
    x1k, _, _ = dsp.pcg_envelope(seg, fs)
    t = np.linspace(-4, 0, len(x1k))
    fig, ax = plt.subplots(figsize=(6.5, 1.8))
    ax.plot(t, x1k / (np.max(np.abs(x1k)) or 1), color=GR, lw=0.5)
    ax.set(title='Microphone waveform (25-400 Hz)', xlabel='Time (s)', ylabel='Normalized amplitude'); save(fig, 'pcg_wave.png')
    nper = 512 if fs >= 16000 else max(64, int(0.032 * fs))
    f, tt, Z = stft(seg, fs=fs, window='hamming', nperseg=nper, noverlap=3 * nper // 4)
    keep = f <= 2000
    S = 20 * np.log10(np.abs(Z[keep]) + 1e-6); S -= S.max()
    fig, ax = plt.subplots(figsize=(6.5, 2.2))
    ax.pcolormesh(tt - 4, f[keep], S, vmin=-60, vmax=0, cmap=matplotlib.colors.LinearSegmentedColormap.from_list(
        'sv', ['#F2F2EE', GR, G]), shading='auto')
    ax.set(title='Chest microphone spectrogram (STFT, dB)', xlabel='Time (s)', ylabel='Frequency (Hz)')
    save(fig, 'spectrogram.png')


def overview_figure():
    """The six Signal Analysis panels in the tab's 3 x 2 grid order."""
    from PIL import Image
    names = ['psd.png', 'spectrogram.png', 'detrended.png', 'decomp.png', 'rgb.png', 'methods_time.png']
    ims = [Image.open(os.path.join(OUT, n)).convert('RGB') for n in names]
    W = 1300; ims = [im.resize((W, int(im.height * W / im.width))) for im in ims]
    H = max(im.height for im in ims)
    sheet = Image.new('RGB', (2 * W + 30, 3 * H + 40), 'white')
    for k, im in enumerate(ims):
        sheet.paste(im, ((k % 2) * (W + 30), (k // 2) * (H + 20)))
    sheet.save(os.path.join(OUT, 'analysis_overview.png'))


def pipeline_figure():
    fig, ax = plt.subplots(figsize=(7.2, 4.6)); ax.axis('off'); ax.set_xlim(0, 100); ax.set_ylim(0, 100)

    def box(x, y, w, h, txt, col):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.4,rounding_size=1.5', fc=col, ec='#3A3A3A', lw=0.6, alpha=0.9))
        ax.text(x + w / 2, y + h / 2, txt, ha='center', va='center', fontsize=6.6)

    def arr(x1, y1, x2, y2):
        ax.annotate('', (x2, y2), (x1, y1), arrowprops=dict(arrowstyle='->', lw=0.7, color='#3A3A3A'))
    L, M, A, D = '#E8F1EC', '#FBF0DC', '#F6E3DC', '#E1ECF6'
    box(1, 86, 18, 10, 'Camera frame\n(Mac webcam 30 fps /\nESP32 GC2145 10 fps)', L)
    box(23, 86, 18, 10, 'Face detection (Haar)\n+ full-face gate', L)
    box(45, 86, 20, 10, 'Skin boxes x4 locked\n+ phase-correlation\nmotion tracking', L)
    box(69, 86, 18, 10, 'YCrCb skin mask\nmean R,G,B per box', L)
    box(69, 70, 18, 10, 'Background strips (non-skin)\nmean RGB = wall reference\nfor rectification + rejection', L)
    box(45, 70, 20, 10, 'Resample 15 Hz\nartifact repair (MAD)\nstill-tail selection', M)
    box(23, 70, 18, 10, 'Illumination\nrectification\n(skin vs wall)', M)
    box(1, 70, 18, 10, 'Pulse extractors\nCHROM | POS | GREEN', M)
    box(1, 50, 26, 12, 'Welch PSD 0.75-2.5 Hz\nwall-peak rejection\npeak tracking, de Haan SNR', M)
    box(31, 50, 22, 12, 'GATE: SNR >= -2 dB\n+ 2/2 methods agree\n+ coverage, artifacts', M)
    box(57, 50, 22, 12, 'Ensemble spectrum\n(4 boxes x 3 methods)\n-> Bayes HR tracker', M)
    box(83, 50, 16, 12, 'Deep models\nTS-CAN, PhysNet,\nEfficientPhys', D)
    box(1, 28, 26, 12, 'INMP441 mic (node audio)\n25-400 Hz, Shannon energy\nautocorrelation -> PCG HR', A)
    box(31, 28, 22, 12, 'Fusion (Eq. 12)\nweighted if |dHR| <= 8\nelse higher quality', '#EEEEEE')
    box(57, 28, 22, 12, 'Display rules\n3-in-a-row confirm,\nmedian-3, EMA 0.2, hold 15 s', '#EEEEEE')
    box(31, 6, 48, 12, 'DASHBOARD: HR card (accepted -> tracked high -> tracked low -> raw), RR, HRV,\nquality, source, SpO2 ratio, graphs and live method comparison', '#DDEBE3')
    for a in ((19, 91, 23, 91), (41, 91, 45, 91), (65, 91, 69, 91), (78, 86, 78, 80), (69, 75, 65, 75), (45, 75, 41, 75),
              (23, 75, 19, 75), (10, 70, 12, 62), (27, 56, 31, 56), (53, 56, 57, 56), (42, 50, 42, 40), (27, 34, 31, 34),
              (53, 34, 57, 34), (68, 50, 68, 40), (68, 28, 60, 18), (91, 50, 79, 18)):
        arr(*a)
    ax.text(50, 99, 'SonicVitals processing chain', ha='center', fontsize=9, weight='bold')
    save(fig, 'pipeline.png')


if __name__ == '__main__':
    main()
