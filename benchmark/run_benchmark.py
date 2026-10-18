"""SonicVitals rPPG benchmark runner.

    python benchmark/run_benchmark.py --dataset ubfc --root /path/UBFC-rPPG/DATASET_2 \
        --dl-train PURE --device cuda --out benchmark/results

Cross-dataset protocol: the deep models are only ever tested on a dataset they were not trained
on (--dl-train lists the training sets of the pretrained weights; a weight trained on the test
dataset is skipped unless --allow-intra). The signal-processing methods (GREEN, CHROM, POS,
SonicVitals) have no training data; SonicVitals' gate thresholds were set on synthetic signals
and our own recordings, never on these datasets.

Outputs in <out>/<dataset>/: per_window.csv, summary.csv, summary.md, summary.tex, latency.csv
"""
import argparse
import os
import re
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sv_bench import datasets, dl, evaluate, extract   # noqa: E402

TRAIN_NAME = {'PURE': 'PURE', 'UBFC-rPPG': 'UBFC-rPPG', 'UBFC': 'UBFC-rPPG', 'SCAMPS': 'SCAMPS'}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--dataset', required=True, choices=sorted(datasets.READERS))
    ap.add_argument('--root', required=True, help='dataset root folder')
    ap.add_argument('--cache', default=os.path.join(os.path.dirname(__file__), 'cache'))
    ap.add_argument('--out', default=os.path.join(os.path.dirname(__file__), 'results'))
    ap.add_argument('--dl-models', default='TS-CAN,PhysNet,EfficientPhys', help='comma list, or "none"')
    ap.add_argument('--dl-train', default='PURE', help='training sets of the pretrained weights, e.g. PURE,SCAMPS')
    ap.add_argument('--allow-intra', action='store_true', help='also test weights trained on the test dataset')
    ap.add_argument('--device', default=None, help='cuda / mps / cpu (default: best available)')
    ap.add_argument('--window', type=float, default=30.0)
    ap.add_argument('--step', type=float, default=10.0)
    ap.add_argument('--limit', type=int, default=None, help='only the first N recordings')
    ap.add_argument('--max-seconds', type=float, default=None, help='only the first N seconds of each video')
    ap.add_argument('--allow-no-dl', action='store_true', help='continue if no deep-model weights are found')
    ap.add_argument('--sv-box-baselines', action='store_true',
                    help='also run GREEN/CHROM/POS on the SonicVitals skin boxes (ablation)')
    args = ap.parse_args()

    recs = datasets.READERS[args.dataset](args.root)
    if args.limit:
        recs = recs[:args.limit]
    if not recs:
        sys.exit(f'no recordings found under {args.root}')
    test_name = recs[0].dataset
    print(f'{test_name}: {len(recs)} recordings')

    models = []
    if args.dl_models.lower() != 'none':
        device = args.device or _best_device()
        if device != _best_device() and device in ('cuda', 'mps'):
            print(f'  {device} not available on this machine (e.g. a TPU runtime): deep models run on {_best_device()}')
            device = _best_device()
        for train in [s.strip() for s in args.dl_train.split(',') if s.strip()]:
            train = TRAIN_NAME.get(train, train)
            if train == test_name and not args.allow_intra:
                print(f'  skipping {train}-trained weights (intra-dataset); use --allow-intra to include')
                continue
            for name in [s.strip() for s in args.dl_models.split(',') if s.strip()]:
                path = dl.weights_file(name, train)
                if not os.path.isfile(path):
                    print(f'  no weights {os.path.basename(path)}; skipped')
                    continue
                models.append((f'{name} [{train}->{test_name}]', name, train, dl.load_model(name, path, device)))
        print(f'  deep models on {device}: {[m[0] for m in models] or "none"}')
        if not models and not args.allow_no_dl:
            sys.exit(f'No deep-model weights found in {dl.weights_file("TS-CAN", "PURE").rsplit("/", 1)[0]}. '
                     'Clone rPPG-Toolbox (or set RPPG_TOOLBOX to its folder), or pass --dl-models none.')

    rows, lat, skipped = [], {}, []
    for i, rec in enumerate(recs, 1):
        print(f'[{i}/{len(recs)}] {rec.rec_id}')
        data = extract.extract_safe(rec, args.cache, keep_crops=bool(models), max_seconds=args.max_seconds)
        if data is None:
            skipped.append(rec.rec_id)
            continue
        dur = float(data['t'][-1] - data['t'][0])
        preds = {}
        for label, name, train, model in models:
            pred_path = os.path.join(args.cache, rec.dataset, f'{rec.rec_id}__{name}_{train}.npy')
            if os.path.isfile(pred_path):
                preds[label] = np.load(pred_path)
                continue
            if 'crops' not in data:
                data = extract.extract_safe(rec, os.path.join(args.cache, '_crops'), keep_crops=True,
                                            max_seconds=args.max_seconds)
                if data is None or 'crops' not in data:
                    break
            pred, t_model = dl.predict(name, model, data['crops'], next(model.parameters()).device)
            np.save(pred_path, pred)
            preds[label] = pred
            lat.setdefault(label, []).append(t_model / max(dur, 1e-6) * 30.0)   # model s per 30 s of video
        r, l = evaluate.evaluate_recording(rec, data, preds, args.window, args.step,
                                           baseline_inputs=('face', 'sv') if args.sv_box_baselines else ('face',))
        rows += r
        for k, v in l.items():
            lat.setdefault(k, []).extend(v)

    if skipped:
        print(f'skipped (unreadable): {", ".join(skipped)}')
    if not rows:
        sys.exit('no recording could be processed')
    out = os.path.join(args.out, test_name)
    os.makedirs(out, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(out, 'per_window.csv'), index=False)
    summ = evaluate.summarize(df)
    latency = pd.DataFrame([dict(method=k, ms_per_30s_window=1000 * float(np.median(v)), n=len(v))
                            for k, v in lat.items()])
    latency.to_csv(os.path.join(out, 'latency.csv'), index=False)
    lat_ms = dict(zip(latency.method, latency.ms_per_30s_window))
    summ['ms_per_30s_window'] = summ.method.map(lambda m: lat_ms.get(re.sub(r' \((raw|gated|display)\)$', '', m)))
    summ.to_csv(os.path.join(out, 'summary.csv'), index=False)
    _write_tables(summ, out, test_name, len(recs), args)
    print(open(os.path.join(out, 'summary.md')).read())


def _best_device():
    try:
        import torch
        if torch.cuda.is_available():
            return 'cuda'
        if torch.backends.mps.is_available():
            return 'mps'
    except ImportError:
        pass
    return 'cpu'


def _write_tables(summ, out, test_name, n, args):
    cols = ['method', 'coverage', 'MAE', 'RMSE', 'MAPE', 'r', 'within5', 'ms_per_30s_window']
    fmt = dict(coverage='{:.0%}', MAE='{:.2f}', RMSE='{:.2f}', MAPE='{:.1f}', r='{:.2f}', within5='{:.0%}',
               ms_per_30s_window='{:.1f}')
    md = [f'# {test_name} ({n} recordings), {time.strftime("%Y-%m-%d")}', '']
    tex = []
    for level, title in (('window', f'{args.window:.0f} s windows, step {args.step:.0f} s'), ('video', 'whole video')):
        s = summ[summ.level == level]
        if s.empty:
            continue
        md += [f'## {title}', '', '| ' + ' | '.join(cols) + ' |', '|' + '---|' * len(cols)]
        tex += [f'% {test_name}, {title}', r'\begin{tabular}{lrrrrrrr}', r'\hline',
                r'Method & Cov. & MAE & RMSE & MAPE (\%) & $r$ & $\le$5 BPM & ms/30 s \\', r'\hline']
        for _, row in s.iterrows():
            vals = [row['method']] + [('–' if pd.isna(row.get(c)) else fmt[c].format(row[c])) for c in cols[1:]]
            md.append('| ' + ' | '.join(vals) + ' |')
            tex.append(' & '.join(v.replace('%', r'\%') for v in vals) + r' \\')
        md.append('')
        tex += [r'\hline', r'\end{tabular}', '']
    md += ['Coverage = share of windows with an HR output (SonicVitals gated/display withhold low-quality '
           'windows; errors are over covered windows only). Latency: median processing time per 30 s '
           'window (deep models: forward pass only, per 30 s of video).']
    open(os.path.join(out, 'summary.md'), 'w').write('\n'.join(md) + '\n')
    open(os.path.join(out, 'summary.tex'), 'w').write('\n'.join(tex))


if __name__ == '__main__':
    main()
