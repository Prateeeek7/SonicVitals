"""Figures for the final report / PPT (architecture, pipeline, corrected setup photo, result charts).
All numbers plotted here are measured values from the benchmark files and the test/evaluation runs."""
import os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(os.path.dirname(HERE), 'Images')
OUT = os.path.join(HERE, 'figs')
G, A, B, R, GREY = '#0F6A4A', '#D98C00', '#2E86C1', '#B85430', '#6E6E66'
plt.rcParams.update({'font.size': 9, 'font.family': 'DejaVu Sans', 'axes.spines.top': False, 'axes.spines.right': False})


def box(ax, x, y, w, h, title, body, col):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.3,rounding_size=1.2', fc=col, ec='#3A3A3A', lw=0.7))
    ax.text(x + w / 2, y + h - 1.6, title, ha='center', va='top', fontsize=7.6, weight='bold')
    ax.text(x + w / 2, y + h - 4.6, body, ha='center', va='top', fontsize=6.5, linespacing=1.35)


def arrow(ax, x1, y1, x2, y2, text=None):
    ax.annotate('', (x2, y2), (x1, y1), arrowprops=dict(arrowstyle='->', lw=0.9, color='#3A3A3A'))
    if text:
        ax.text((x1 + x2) / 2 + 0.8, (y1 + y2) / 2, text, fontsize=6.2, color=GREY, va='center')


def architecture():
    fig, ax = plt.subplots(figsize=(11, 7.2)); ax.axis('off'); ax.set_xlim(0, 110); ax.set_ylim(0, 74)
    L1, L2, L3 = '#E8F1EC', '#FBF0DC', '#E1ECF6'
    ax.text(55, 73, 'SonicVitals system architecture', ha='center', fontsize=12, weight='bold')
    ax.text(1, 68.5, 'TIER 1  EDGE NODE (ESP32-S3)', fontsize=8, weight='bold', color=G)
    box(ax, 1, 52, 25, 15, 'GC2145 camera', 'RGB565, 240x160 (HQVGA)\n10 fps capture\nskin-metered exposure', L1)
    box(ax, 28, 52, 26, 15, 'On-node processing', 'raw-pixel skin-box RGB sums\n(10 Hz, clipped/dark pixels excluded)\nsoftware JPEG q65 video, 5 fps', L1)
    box(ax, 56, 52, 24, 15, 'INMP441 MEMS mic', 'I2S, 16 kHz capture\nanti-alias FIR, decimated\nto 4 kHz for streaming', L1)
    box(ax, 82, 52, 27, 15, 'SSD1306 OLED (I2C)', 'local readout of heart rate,\nbreathing rate and status\nsent back by the host', L1)
    arrow(ax, 26, 59.5, 28, 59.5)
    ax.text(1, 44.2, 'LINK  Wi-Fi TCP :3333 line protocol  (uplink <<FRAME>> <<RGB>> <<AUDIO>> <<INFO>>,  downlink <<ROI>> <<CAM:EXP>> <<VITALS>>)   |   alternative input: host webcam 30 fps',
            fontsize=7, color='#3A3A3A')
    for x in (13, 41, 68):
        arrow(ax, x, 52, x, 46.5)
    arrow(ax, 95.5, 46.5, 95.5, 52, None)
    ax.text(1, 40, 'TIER 2  HOST SIGNAL-PROCESSING ENGINE (Python)', fontsize=8, weight='bold', color=A)
    box(ax, 1, 22, 21, 17, 'Face & skin', 'Haar detection, full-face gate\nphase-correlation tracking\n4 skin boxes + YCrCb masks', L2)
    box(ax, 23.5, 22, 21, 17, 'Pulse (rPPG)', 'artifact repair, illumination\nrectification; CHROM/POS/GREEN\nSNR + consensus gate', L2)
    box(ax, 46, 22, 21, 17, 'Fusion & display', 'ensemble spectrum, Bayes tracker\ndeep models (TS-CAN, PhysNet,\nEfficientPhys); robust consensus', L2)
    box(ax, 68.5, 22, 19, 17, 'Breathing, HRV,\nface insights', '4-source breathing fusion\ncamera HRV (beat timing)\nperfusion map, liveness, blinks', L2)
    box(ax, 89, 22, 20, 17, 'Acoustic & imaging', 'PCG envelope (Shannon energy)\nautocorrelation, S1 beats\ncolorimetric indices', L2)
    for x in (22, 44.5, 67, 87.5):
        arrow(ax, x, 30.5, x + 1.5, 30.5)
    for x in (11, 34, 56.5, 78, 99):
        arrow(ax, x, 22, x, 15.5)
    ax.text(1, 14, 'TIER 3  WEB DASHBOARD (Flask REST API -> HTML / JavaScript / Plotly)', fontsize=8, weight='bold', color=B)
    labels = [('Dashboard', 'video, readout cards,\nmethod comparison,\nface insights'), ('Signal Analysis', 'spectrum, spectrogram,\npulse decomposition,\ncolour traces'),
              ('Diagnostics Studio', 'sharpest-frame capture,\ncolour maps, indices'), ('Sessions', 'recording, Bland-Altman\nagreement'), ('Device', 'link, frame rate,\nexposure, config')]
    for k, (t, b) in enumerate(labels):
        box(ax, 1 + k * 21.8, 1, 20.5, 12, t, b, L3)
    fig.savefig(os.path.join(OUT, 'architecture.png'), dpi=200, bbox_inches='tight'); plt.close(fig)


def pipeline():
    fig, ax = plt.subplots(figsize=(8.5, 10)); ax.axis('off'); ax.set_xlim(0, 100); ax.set_ylim(0, 120)
    C, P, D = '#E8F1EC', '#FBF0DC', '#E1ECF6'
    steps = [
        ('Camera frame', 'webcam 30 fps or ESP32-S3 node (RGB sums 10 Hz + video 5 fps)', C),
        ('Face detection + full-face gate', 'Haar cascade every 3rd frame; face size, framing and aspect checks', C),
        ('Skin regions, motion compensated', 'forehead, cheeks, nose; sub-pixel phase-correlation tracking; YCrCb skin masks', C),
        ('Signal conditioning', '15 Hz resampling, derivative-domain artifact repair, still-stretch selection,\nillumination rectification against the background', P),
        ('Pulse extraction', 'CHROM (primary), POS, GREEN; Welch spectrum 0.75-2.5 Hz', P),
        ('Quality gate', 'de Haan SNR >= -2 dB, 2/2 method agreement, coverage, artifact share', P),
        ('Tracking + consensus', 'ensemble spectrum and Bayes tracker; robust average of all methods\n(incl. deep models); display stabilizer flags rapid changes', P),
        ('Derived measurements', 'breathing (4-source fusion), camera HRV, perfusion map, liveness,\nblink rate, head steadiness, colorimetric indices', P),
        ('Dashboard + OLED', 'cards with status badges, live graphs, method table, session logs', D),
    ]
    y = 113
    for k, (t, b, c) in enumerate(steps):
        ax.add_patch(FancyBboxPatch((8, y - 9), 84, 9, boxstyle='round,pad=0.3,rounding_size=1.2', fc=c, ec='#3A3A3A', lw=0.7))
        ax.text(50, y - 2.2, t, ha='center', va='top', fontsize=9, weight='bold')
        ax.text(50, y - 5.0, b, ha='center', va='top', fontsize=7.2, linespacing=1.3)
        if k < len(steps) - 1:
            arrow(ax, 50, y - 9.4, 50, y - 12.1)
        y -= 12.6
    ax.text(50, 118, 'SonicVitals processing pipeline', ha='center', fontsize=12, weight='bold')
    fig.savefig(os.path.join(OUT, 'pipeline.png'), dpi=200, bbox_inches='tight'); plt.close(fig)


def setup_photo():
    im = Image.open(os.path.join(IMG, 'labeled_setup.png')).convert('RGB')
    W, H = im.size
    arr = np.asarray(im.convert('L'))
    # right-hand labels all start at the same x; the camera label row is the one between 0.30 H and 0.37 H
    x0 = int(0.795 * W)
    band = arr[int(0.30 * H):int(0.37 * H), x0 + 10:int(0.98 * W)] < 110
    rows = np.where(band.any(axis=1))[0]
    y0, y1 = int(0.30 * H) + rows.min() - 6, int(0.30 * H) + rows.max() + 8
    d = ImageDraw.Draw(im)
    d.rectangle((x0, y0, W, y1), fill='white')
    try:
        font = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', int((y1 - y0) * 0.78))
    except OSError:
        font = ImageFont.load_default()
    d.text((x0 + 2, y0 + 2), 'Camera module (GC2145)', fill='black', font=font)
    im.save(os.path.join(OUT, 'setup_labeled.png'))


def shot(stamp):
    """Screenshot by time stamp, e.g. '8.54.48' (macOS puts a narrow no-break space before PM)."""
    import glob
    return glob.glob(os.path.join(IMG, f'Screenshot 2026-10-22 at {stamp}*'))[0]


def synthetic_map_crop():
    im = Image.open(shot('8.54.48')).convert('RGB')
    arr = np.asarray(im.convert('L')).astype(int)
    dark = (arr < 200).sum(axis=1)
    rows = np.where(dark > 0.4 * arr.shape[1])[0]               # rows crossing the map image
    cols = np.where((arr[rows.min():rows.max()] < 200).sum(axis=0) > 0.4 * len(rows))[0]
    im.crop((cols.min(), rows.min(), cols.max(), rows.max())).save(os.path.join(OUT, 'synthetic_map.png'))


def bench():
    m = ['GREEN', 'CHROM', 'POS', 'EfficientPhys*', 'PhysNet*', 'TS-CAN*', 'SonicVitals\n(raw)', 'SonicVitals\n(gated)']
    mae = [22.04, 2.40, 2.08, 3.88, 1.90, 1.68, 2.30, 1.56]
    rmse = [34.21, 6.48, 5.41, 9.09, 5.00, 4.95, 4.92, 2.73]
    col = [GREY, A, A, B, B, B, G, G]
    fig, axs = plt.subplots(1, 2, figsize=(10, 3.4))
    for ax, v, t in ((axs[0], mae, 'MAE (BPM)'), (axs[1], rmse, 'RMSE (BPM)')):
        bars = ax.bar(range(len(m)), v, color=col)
        ax.set_xticks(range(len(m))); ax.set_xticklabels(m, fontsize=7, rotation=0)
        ax.set_ylim(0, 12); ax.set_title(t + ', UBFC-rPPG, 30 s windows')
        for b_, val in zip(bars, v):
            ax.text(b_.get_x() + b_.get_width() / 2, min(val, 11.3) + 0.2, f'{val:.2f}', ha='center', fontsize=7)
    fig.text(0.5, -0.02, '* deep models trained on PURE, tested on UBFC-rPPG (cross-dataset). GREEN bars clipped at 12.', ha='center', fontsize=7.5)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, 'benchmark.png'), dpi=200, bbox_inches='tight'); plt.close(fig)


def rr():
    rates = [8, 12, 15, 18, 24]
    old = [5.97, 0.88, 2.05, 2.71, 7.82]
    new = [0.14, 0.11, 0.09, 0.08, 0.08]
    fig, ax = plt.subplots(figsize=(6.4, 3))
    x = np.arange(len(rates))
    ax.bar(x - 0.2, old, 0.4, color=GREY, label='single green peak (earlier method)')
    ax.bar(x + 0.2, new, 0.4, color=G, label='4-source fusion (final method)')
    ax.set_xticks(x); ax.set_xticklabels([f'{r}/min' for r in rates]); ax.set_ylabel('Mean absolute error (breaths/min)')
    ax.set_title('Breathing-rate error on synthetic face signals with realistic drift'); ax.legend(frameon=False, fontsize=7.5)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, 'rr_accuracy.png'), dpi=200); plt.close(fig)


def hrv():
    snr = [1.2, -2.1, -3.5]
    err = [11.5, 64.2, np.nan]
    fig, ax = plt.subplots(figsize=(6.4, 3))
    ax.plot(snr[:2], err[:2], 'o-', color=R)
    ax.axvline(1.0, ls='--', color=G); ax.text(1.1, 50, 'display gate\n(SNR >= +1 dB)', color=G, fontsize=8)
    ax.annotate('beat timing\nnot measurable', (-3.5, 70), fontsize=8, color=GREY, ha='center')
    ax.set_xlabel('Pulse SNR (dB)'); ax.set_ylabel('RMSSD error (ms)'); ax.set_xlim(-4.5, 2.5); ax.set_ylim(0, 80)
    ax.set_title('Camera HRV: RMSSD error versus pulse signal quality (30 fps)')
    fig.tight_layout(); fig.savefig(os.path.join(OUT, 'hrv_snr.png'), dpi=200); plt.close(fig)


def liveness():
    photos = [0.028, 0.039, 0.032, 0.027, 0.042, 0.031, 0.025, 0.039, 0.045, 0.044, 0.045, 0.053, 0.036]
    faces = [0.611, 0.571, 0.642, 0.391, 0.439]
    fig, ax = plt.subplots(figsize=(6.4, 2.6))
    ax.scatter(photos, np.zeros(len(photos)) + 0.0, color=R, label='still photos (13)')
    ax.scatter(faces, np.zeros(len(faces)) + 0.0, color=G, marker='s', label='pulsing faces (5)')
    ax.axvline(0.08, ls='--', color=R); ax.axvline(0.15, ls='--', color=G)
    ax.text(0.085, 0.02, 'NO PULSE below', color=R, fontsize=7.5); ax.text(0.155, 0.02, 'LIVE above', color=G, fontsize=7.5)
    ax.set_yticks([]); ax.set_xlabel('Liveness evidence = share of skin pulsing in phase x phase coherence')
    ax.set_xlim(0, 0.7); ax.set_ylim(-0.05, 0.05); ax.legend(frameon=False, loc='upper right', fontsize=7.5)
    ax.set_title('Pulse-based liveness evidence (30 fps and 5 fps test videos)')
    fig.tight_layout(); fig.savefig(os.path.join(OUT, 'liveness.png'), dpi=200); plt.close(fig)


def perf():
    fig, axs = plt.subplots(1, 2, figsize=(9, 3))
    axs[0].bar(['before', 'after'], [16.4, 27.0], color=[GREY, G]); axs[0].set_ylabel('processed frames per second')
    axs[0].set_title('Webcam frame rate (live, median)')
    for i, v in enumerate([16.4, 27.0]): axs[0].text(i, v + 0.5, f'{v:.1f}', ha='center')
    axs[1].bar(['before', 'after'], [21.4, 10.6], color=[GREY, G]); axs[1].set_ylabel('ms per frame (camera thread)')
    axs[1].set_title('Per-frame processing time')
    for i, v in enumerate([21.4, 10.6]): axs[1].text(i, v + 0.3, f'{v:.1f}', ha='center')
    fig.tight_layout(); fig.savefig(os.path.join(OUT, 'performance.png'), dpi=200); plt.close(fig)


def map_cov():
    cases = ['synthetic\n0.15 % pulse', 'synthetic\n0.08 % pulse', 'live capture\n(30 s, still)']
    old = [28, 10, 7]; new = [94, 71, 46]
    x = np.arange(3)
    fig, ax = plt.subplots(figsize=(6.4, 3))
    ax.bar(x - 0.2, old, 0.4, color=GREY, label='per-cell detection (first version)')
    ax.bar(x + 0.2, new, 0.4, color=G, label='phase-referenced map (final)')
    for xi, (o, n) in enumerate(zip(old, new)):
        ax.text(xi - 0.2, o + 1.5, f'{o}%', ha='center', fontsize=8); ax.text(xi + 0.2, n + 1.5, f'{n}%', ha='center', fontsize=8)
    ax.set_xticks(x); ax.set_xticklabels(cases); ax.set_ylabel('skin area mapped (%)'); ax.set_ylim(0, 105)
    ax.set_title('Blood-flow map coverage'); ax.legend(frameon=False, fontsize=7.5, loc='upper right')
    fig.tight_layout(); fig.savefig(os.path.join(OUT, 'map_coverage.png'), dpi=200); plt.close(fig)


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    for f in (architecture, pipeline, setup_photo, synthetic_map_crop, bench, rr, hrv, liveness, perf, map_cov):
        f(); print('ok', f.__name__)
