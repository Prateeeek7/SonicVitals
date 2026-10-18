"""Record a webcam clip (or use a video file) and run every method on it.

    python benchmark/webcam_compare.py --seconds 45            # record from the default webcam
    python benchmark/webcam_compare.py --video clip.avi        # analyse an existing clip
    python benchmark/webcam_compare.py --seconds 45 --ref 78   # also compare with a counted pulse

Methods: SonicVitals (raw / gated), GREEN, CHROM, POS and the pretrained deep models
(TS-CAN, PhysNet, EfficientPhys; PURE-trained weights from rPPG-Toolbox). There is no contact
reference for a webcam clip, so the table shows each method's HR per 30 s window, how far the
methods spread, and the error to --ref (a pulse counted at the wrist) if given.
"""
import argparse
import os
import queue
import sys
import threading
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sv_bench import datasets, dl, extract, methods   # noqa: E402
import vitals_dsp as dsp                              # noqa: E402

DL_MODELS = ('TS-CAN', 'PhysNet', 'EfficientPhys')


def record(seconds, out_dir, camera=0):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, 'webcam.avi')
    cap = cv2.VideoCapture(camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)
    if not cap.isOpened():
        sys.exit('cannot open the webcam (camera permission, or another program is using it)')
    for _ in range(15):                      # let auto exposure settle
        cap.read()
    ok, frame = cap.read()
    h, w = frame.shape[:2]
    vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*'FFV1'), 30, (w, h))
    # Lossless encoding is slow: it runs in its own thread so capture keeps the camera's frame rate.
    q = queue.Queue(maxsize=2000)

    def writer():
        while True:
            f = q.get()
            if f is None:
                return
            vw.write(f)
    th = threading.Thread(target=writer, daemon=True)
    th.start()
    times, t0 = [], time.time()
    print(f'recording {seconds:.0f} s: whole face in frame, look at the camera, sit still; '
          f'count your wrist pulse for 30 s', flush=True)
    while time.time() - t0 < seconds:
        ok, frame = cap.read()
        if not ok:
            continue
        times.append(time.time() - t0)
        q.put(frame)
        if len(times) % 150 == 0:
            print(f'  {times[-1]:.0f} s', flush=True)
    cap.release()
    q.put(None)
    th.join()
    vw.release()
    np.save(os.path.join(out_dir, 'webcam_times.npy'), np.asarray(times))
    print(f'saved {len(times)} frames ({len(times) / times[-1]:.1f} fps) to {path}', flush=True)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seconds', type=float, default=45)
    ap.add_argument('--video', help='analyse this video instead of recording')
    ap.add_argument('--out', default=os.path.join(os.path.dirname(__file__), 'webcam_runs', time.strftime('%Y%m%d_%H%M%S')))
    ap.add_argument('--ref', type=float, help='reference HR counted at the wrist (BPM)')
    ap.add_argument('--device', default=None)
    ap.add_argument('--window', type=float, default=30.0)
    ap.add_argument('--step', type=float, default=5.0)
    args = ap.parse_args()

    path = args.video or record(args.seconds, args.out)
    times_file = os.path.join(os.path.dirname(path), 'webcam_times.npy')
    ft = np.load(times_file) if os.path.isfile(times_file) else None
    fps, n = datasets._video_fps(path)
    rec = datasets.Recording('WEBCAM', os.path.splitext(os.path.basename(path))[0], 'self', path,
                             ppg=np.zeros(2), ppg_t=np.array([0.0, 1e6]), frame_times=ft, fps=fps)
    data = extract.extract(rec, os.path.join(args.out, 'cache'), keep_crops=True)
    t = data['t']
    print(f'face gate passed on {np.mean(~np.isnan(data["sv_rgb"][:, 0])):.0%} of frames, '
          f'{(len(t) - 1) / (t[-1] - t[0]):.1f} fps average')
    # Webcam frames arrive unevenly; the baselines and deep models assume a constant rate, so their
    # inputs are put on a uniform 30 Hz grid (colour traces interpolated, crops = nearest frame).
    # SonicVitals resamples from the true timestamps itself.
    fs = 30.0
    tu = np.arange(t[0], t[-1], 1 / fs)
    face_u = np.stack([np.interp(tu, t, data['face_rgb'][:, k]) for k in range(3)], 1)
    crops_u = data['crops'][np.clip(np.searchsorted(t, tu), 0, len(t) - 1)]

    device = args.device or ('cuda' if _has('cuda') else 'mps' if _has('mps') else 'cpu')
    preds, dl_ms = {}, {}
    for name in DL_MODELS:
        wf = dl.weights_file(name, 'PURE')
        if not os.path.isfile(wf):
            print(f'  {name}: weights not found ({wf})')
            continue
        model = dl.load_model(name, wf, device)
        pred, t_model = dl.predict(name, model, crops_u, next(model.parameters()).device)
        preds[name] = pred
        dl_ms[name] = 1000 * t_model / max(t[-1] - t[0], 1e-6) * 30

    names = ['SonicVitals', 'SV gate', 'GREEN', 'CHROM', 'POS'] + list(preds)
    rows = []
    for a in np.arange(t[0], t[-1] - args.window + 1e-6, args.step):
        b = a + args.window
        m = (t >= a) & (t < b)
        ok = m & ~np.isnan(data['sv_rgb'][:, 0])
        o = dsp.estimate_optical(t[ok], data['sv_rgb'][ok])
        row = {'window': f'{a - t[0]:4.0f}-{b - t[0]:3.0f} s', 'SonicVitals': o['hr'],
               'SV gate': 'pass' if o['hr_ok'] else f'fail ({o["snr"]:+.1f} dB)' if o['snr'] is not None else 'fail'}
        mu = (tu >= a) & (tu < b)
        x = face_u[mu]
        for nm, fn in methods.BASELINES.items():
            row[nm] = methods.fft_hr(methods.postprocess(fn(x, fs), fs), fs)
        for nm, pred in preds.items():
            mm = mu[:len(pred)]
            row[nm] = methods.fft_hr(methods.postprocess(np.cumsum(pred[mm]), fs), fs) if mm.sum() > 2 * fs else None
        rows.append(row)

    fmt = lambda v: f'{v:6.1f}' if isinstance(v, (float, np.floating)) else f'{str(v):>6}' if v is not None else '    --'
    print('\nHeart rate (BPM) per 30 s window')
    print(f'{"window":>11} | ' + ' | '.join(f'{nm:>13}' for nm in names) + ' | spread')
    for r in rows:
        vals = [r[nm] for nm in names if nm not in ('SV gate', 'GREEN') and isinstance(r.get(nm), (float, np.floating))]
        spread = f'{max(vals) - min(vals):5.1f}' if vals else '   --'
        print(f'{r["window"]:>11} | ' + ' | '.join(f'{fmt(r.get(nm)):>13}' for nm in names) + f' | {spread}')
    print('\nmedian over windows: ' + ', '.join(
        f'{nm} {np.median([r[nm] for r in rows if isinstance(r.get(nm), (float, np.floating))]):.1f}'
        for nm in names if nm != 'SV gate' and any(isinstance(r.get(nm), (float, np.floating)) for r in rows)))
    if args.ref:
        print(f'error vs counted pulse {args.ref:.0f} BPM: ' + ', '.join(
            f'{nm} {np.median([abs(r[nm] - args.ref) for r in rows if isinstance(r.get(nm), (float, np.floating))]):.1f}'
            for nm in names if nm != 'SV gate' and any(isinstance(r.get(nm), (float, np.floating)) for r in rows)))
    print('deep-model forward time per 30 s of video: ' + ', '.join(f'{k} {v:.0f} ms' for k, v in dl_ms.items()))


def _has(dev):
    try:
        import torch
        return torch.cuda.is_available() if dev == 'cuda' else torch.backends.mps.is_available()
    except ImportError:
        return False


if __name__ == '__main__':
    main()
