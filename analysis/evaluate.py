"""Offline evaluation of recorded SonicVitals sessions against reference instruments.

Produces the numbers for the paper's Tables VI (agreement), VII (HR MAE by
condition and configuration) and VIII (bench characterization), using exactly
the same DSP code as the live server (backend/vitals_dsp.py).

Reference data
--------------
Put a file `reference.csv` in each session folder, with a `host_time` column
(Unix seconds, same computer clock as the recording) and any of:
    hr_ref     reference heart rate, beats/min (e.g. chest-strap ECG)
    rr_ref     reference respiration rate, breaths/min (metronome rate or annotation)
    spo2_ref   reference SpO2, % (finger oximeter)
Optionally add `rpeaks.csv` with a `host_time` column holding the time of each
ECG R peak; it gives reference RMSSD. If the reference device has its own clock,
pass --ref-offset (seconds added to the reference times).

Usage
-----
    python3 analysis/evaluate.py data/sessions/*  --out analysis/results \
        --dev-participants P01,P02 [--write-calibration]

Participants listed in --dev-participants are used ONLY to fit the SpO2
calibration (A, B) and are excluded from every reported metric.
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'backend'))
import vitals_dsp as dsp   # noqa: E402

WINDOW_S = 30.0
RMSSD_WINDOW_S = 60.0
CONFIGS = ['green', 'chrom_nogate', 'chrom_gate', 'acoustic', 'fused']


# ---------------------------------------------------------------- loading
def load_session(path, allow_webcam=False):
    meta = json.load(open(os.path.join(path, 'meta.json')))
    frames = pd.read_csv(os.path.join(path, 'frames.csv'))
    if not allow_webcam and (frames['source'] != 'ESP32_S3_CAM').any():
        n = int((frames['source'] != 'ESP32_S3_CAM').sum())
        print(f'  {meta["session_id"]}: dropping {n} webcam-fallback frames', file=sys.stderr)
        frames = frames[frames['source'] == 'ESP32_S3_CAM']
    frames = frames.dropna(subset=['device_t'])

    # Map the device clock to the host clock with a least-squares line (absorbs offset and drift).
    a, b = np.polyfit(frames['device_t'], frames['host_time'], 1) if len(frames) > 10 else (1.0, 0.0)
    frames['t'] = a * frames['device_t'] + b

    audio, audio_t0, fs_audio = None, None, dsp.FS_AUDIO
    wav_path = os.path.join(path, 'audio.wav')
    blocks_path = os.path.join(path, 'audio_blocks.csv')
    if os.path.exists(wav_path) and os.path.exists(blocks_path):
        import wave
        with wave.open(wav_path) as w:
            audio = np.frombuffer(w.readframes(w.getnframes()), dtype='<i2')
            fs_audio = w.getframerate()
        blocks = pd.read_csv(blocks_path)
        if len(blocks) and len(audio):
            # host time of sample 0 from the device timestamps of each block
            t_host = a * blocks['device_t_us'] / 1e6 + b
            audio_t0 = float(np.median(t_host - blocks['sample_index'] / fs_audio))
        else:
            audio, blocks = None, None
    ref = pd.read_csv(os.path.join(path, 'reference.csv')) if os.path.exists(os.path.join(path, 'reference.csv')) else None
    rpeaks = pd.read_csv(os.path.join(path, 'rpeaks.csv'))['host_time'].to_numpy() \
        if os.path.exists(os.path.join(path, 'rpeaks.csv')) else None
    return dict(meta=meta, frames=frames, audio=audio, audio_t0=audio_t0, fs=fs_audio, ref=ref, rpeaks=rpeaks,
                blocks=pd.read_csv(blocks_path) if os.path.exists(blocks_path) else None)


# ---------------------------------------------------------------- bench
def bench_metrics(s):
    f = s['frames']
    out = dict(session=s['meta']['session_id'])
    if len(f) > 2:
        d = np.diff(f['device_t'].to_numpy())
        out.update(fps=1.0 / np.mean(d), jitter_sd_ms=1000 * np.std(d))
        seq = f['seq'].dropna().to_numpy()
        if len(seq) > 1:
            out['frame_loss_pct'] = 100 * (np.sum(np.diff(seq) - 1) / (seq[-1] - seq[0] + 1))
        if 'jpeg_bytes' in f and f['jpeg_bytes'].notna().any():
            out['jpeg_kb'] = f['jpeg_bytes'].mean() / 1024
        out['gated_pct'] = 100 * f['gated'].mean()
    b = s['blocks']
    if b is not None and len(b) > 1:
        seq = b['seq'].to_numpy()
        out['audio_loss_pct'] = 100 * (np.sum(np.diff(seq) - 1) / (seq[-1] - seq[0] + 1))
    return out


# ---------------------------------------------------------------- per window
def window_estimates(s, t_end, calibration=None):
    f = s['frames']
    sel = (f['t'] > t_end - WINDOW_S) & (f['t'] <= t_end)
    fw = f[sel]
    res = {}
    gated = fw[fw['gated'] == 1]
    face = fw[fw['face_found'] == 1].dropna(subset=['R'])
    rgb = lambda d: d[['R', 'G', 'B']].to_numpy(float)
    res['green'] = dsp.estimate_optical(gated['t'].to_numpy(), rgb(gated), method='green')
    res['chrom_nogate'] = dsp.estimate_optical(face['t'].to_numpy(), rgb(face))
    res['chrom_gate'] = dsp.estimate_optical(gated['t'].to_numpy(), rgb(gated), spo2_calibration=calibration)
    # The live gate also requires the face to be gated for the whole contiguous segment.
    opt = res['chrom_gate']

    aco = dict(hr=None, rho=0.0, beats=np.array([]))
    if s['audio'] is not None:
        i0 = int((t_end - WINDOW_S - s['audio_t0']) * s['fs'])
        i1 = int((t_end - s['audio_t0']) * s['fs'])
        if i0 >= 0 and i1 <= len(s['audio']):
            aco = dsp.estimate_acoustic(s['audio'][i0:i1], t0=t_end - WINDOW_S, fs=s['fs'])
            if np.std(s['audio'][i0:i1]) < 1 or aco['rho'] < dsp.MIN_RHO_ACOUSTIC:   # silent or arrhythmic
                aco = dict(hr=None, rho=aco.get('rho', 0.0), beats=np.array([]))
    res['acoustic'] = aco
    w_o = opt['quality'] if opt['hr'] is not None else 0.0
    res['fused'] = dsp.fuse_hr(opt['hr'], w_o, aco['hr'], aco['rho'] if aco['hr'] is not None else 0.0)
    return res


def reference_in_window(s, t_end, col, length=WINDOW_S):
    ref = s['ref']
    if ref is None or col not in ref:
        return None
    sel = (ref['host_time'] > t_end - length) & (ref['host_time'] <= t_end)
    v = ref.loc[sel, col].dropna()
    return float(v.mean()) if len(v) else None


def evaluate_session(s, calibration, ref_offset):
    if s['ref'] is not None:
        s['ref'] = s['ref'].assign(host_time=s['ref']['host_time'] + ref_offset)
    if s['rpeaks'] is not None:
        s['rpeaks'] = s['rpeaks'] + ref_offset
    f = s['frames']
    if len(f) < 10:
        return []
    rows = []
    t = f['t'].min() + WINDOW_S
    while t <= f['t'].max():
        est = window_estimates(s, t, calibration)
        row = dict(session=s['meta']['session_id'], participant=s['meta']['participant'],
                   condition=s['meta']['condition'], t_end=t,
                   hr_ref=reference_in_window(s, t, 'hr_ref'), rr_ref=reference_in_window(s, t, 'rr_ref'),
                   spo2_ref=reference_in_window(s, t, 'spo2_ref'))
        for c in ['green', 'chrom_nogate', 'chrom_gate', 'acoustic']:
            row[f'hr_{c}'] = est[c]['hr']
        row['hr_fused'] = est['fused']['hr']
        row['fusion_source'] = est['fused']['source']
        row['rr_est'] = est['chrom_gate']['rr']
        row['spo2_ratio'] = est['chrom_gate']['spo2_ratio']
        row['spo2_est'] = est['chrom_gate']['spo2']
        rows.append(row)
        t += WINDOW_S

    # RMSSD in 60 s windows: acoustic S1 intervals vs ECG R-R intervals
    if s['audio'] is not None and s['rpeaks'] is not None:
        t = f['t'].min() + RMSSD_WINDOW_S
        while t <= f['t'].max():
            i0 = int((t - RMSSD_WINDOW_S - s['audio_t0']) * s['fs'])
            i1 = int((t - s['audio_t0']) * s['fs'])
            if i0 >= 0 and i1 <= len(s['audio']):
                beats = dsp.estimate_acoustic(s['audio'][i0:i1], t0=t - RMSSD_WINDOW_S, fs=s['fs'])['beats']
                rp = s['rpeaks'][(s['rpeaks'] > t - RMSSD_WINDOW_S) & (s['rpeaks'] <= t)]
                rows.append(dict(session=s['meta']['session_id'], participant=s['meta']['participant'],
                                 condition=s['meta']['condition'], t_end=t, kind='rmssd',
                                 rmssd_ref=dsp.rmssd_ms(rp), rmssd_est=dsp.rmssd_ms(beats)))
            t += RMSSD_WINDOW_S
    return rows


# ---------------------------------------------------------------- statistics
def repeated_measures_loa(diff, subject):
    """Bland & Altman (2007) limits of agreement for multiple observations per subject
    when the true value varies. Returns (bias, lower, upper)."""
    df = pd.DataFrame({'d': diff, 's': subject})
    n, k = len(df), df['s'].nunique()
    bias = df['d'].mean()
    if k < 2 or n <= k:
        sd = df['d'].std(ddof=1) if n > 1 else 0.0
        return bias, bias - 1.96 * sd, bias + 1.96 * sd
    g = df.groupby('s')['d']
    m = g.size()
    ss_within = ((df['d'] - g.transform('mean')) ** 2).sum()
    ss_between = (m * (g.mean() - bias) ** 2).sum()
    ms_w = ss_within / (n - k)
    ms_b = ss_between / (k - 1)
    m_h = (n ** 2 - (m ** 2).sum()) / ((k - 1) * n)
    var_total = max(0.0, (ms_b - ms_w) / m_h) + ms_w
    sd = np.sqrt(var_total)
    return bias, bias - 1.96 * sd, bias + 1.96 * sd


def agreement(est, ref, subject, aami=False):
    est, ref, subject = np.asarray(est, dtype=float), np.asarray(ref, dtype=float), np.asarray(subject)
    have_ref = ~np.isnan(ref)
    ok = have_ref & ~np.isnan(est)
    out = dict(windows=int(have_ref.sum()), coverage_pct=100 * ok.sum() / max(1, have_ref.sum()))
    if ok.sum() < 2:
        return out
    e, r, s = est[ok], ref[ok], subject[ok]
    d = e - r
    bias, lo, hi = repeated_measures_loa(d, s)
    out.update(n=int(ok.sum()), mae=np.mean(np.abs(d)), rmse=np.sqrt(np.mean(d ** 2)),
               r=np.corrcoef(e, r)[0, 1] if np.std(e) > 0 and np.std(r) > 0 else np.nan,
               bias=bias, loa_low=lo, loa_high=hi)
    if aami:
        out['aami_ec13_pass_pct'] = 100 * np.mean(np.abs(d) <= np.maximum(5.0, 0.10 * r))
    return out


# ---------------------------------------------------------------- calibration
def fit_spo2(windows):
    w = windows.dropna(subset=['spo2_ratio', 'spo2_ref'])
    if len(w) < 5:
        return None
    B, A = np.polyfit(w['spo2_ratio'], w['spo2_ref'], 1)      # spo2 = A + slope*ratio
    return {'A': float(A), 'B': float(-B), 'n_windows': int(len(w)),
            'participants': sorted(w['participant'].unique().tolist()),
            'note': 'Fitted on development participants only; exploratory, not ISO 80601-2-61 validated.'}


# ---------------------------------------------------------------- output
def fmt(v, d=2):
    return 'n/a' if v is None or (isinstance(v, float) and np.isnan(v)) else f'{v:.{d}f}'


def latex_rows(metrics):
    lines = []
    for name, m in metrics.items():
        if 'mae' not in m:
            lines.append(f'{name} & {fmt(m.get("coverage_pct"), 1)} & \\multicolumn{{5}}{{c}}{{insufficient data}} \\\\')
            continue
        lines.append(f'{name} & {fmt(m["coverage_pct"], 1)} & {fmt(m["mae"])} & {fmt(m["rmse"])} & '
                     f'{fmt(m["r"], 3)} & {fmt(m["bias"])} & [{fmt(m["loa_low"])}, {fmt(m["loa_high"])}] \\\\')
    return '\n'.join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('sessions', nargs='+')
    ap.add_argument('--out', default=os.path.join(HERE, 'results'))
    ap.add_argument('--dev-participants', default='', help='comma-separated IDs used only for calibration')
    ap.add_argument('--ref-offset', type=float, default=0.0)
    ap.add_argument('--allow-webcam', action='store_true')
    ap.add_argument('--write-calibration', action='store_true',
                    help='write backend/spo2_calibration.json from the development participants')
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    dev = {p.strip() for p in args.dev_participants.split(',') if p.strip()}

    sessions = [load_session(p, args.allow_webcam) for p in args.sessions if os.path.exists(os.path.join(p, 'meta.json'))]
    print(f'{len(sessions)} sessions loaded', file=sys.stderr)

    # Pass 1: development participants, uncalibrated, to fit SpO2 (A, B)
    dev_rows = [r for s in sessions if s['meta']['participant'] in dev for r in evaluate_session(dict(s), None, args.ref_offset)]
    calibration = fit_spo2(pd.DataFrame([r for r in dev_rows if r.get('kind') != 'rmssd'])) if dev_rows else None
    if calibration:
        print(f'SpO2 calibration from development set: {calibration}', file=sys.stderr)
        if args.write_calibration:
            path = os.path.join(os.path.dirname(HERE), 'backend', 'spo2_calibration.json')
            json.dump(calibration, open(path, 'w'), indent=2)
            print(f'wrote {path}', file=sys.stderr)

    # Pass 2: test participants only
    test = [s for s in sessions if s['meta']['participant'] not in dev]
    rows = [r for s in test for r in evaluate_session(s, calibration, args.ref_offset)]
    if not rows:
        sys.exit('no evaluable windows (check reference.csv files and participant IDs)')
    allw = pd.DataFrame(rows)
    if 'kind' not in allw.columns:
        allw['kind'] = np.nan
    allw.to_csv(os.path.join(args.out, 'windows.csv'), index=False)
    win = allw[allw['kind'].isna()]
    rms = allw[allw['kind'] == 'rmssd']

    subj = win['participant'].to_numpy()
    table6 = {
        'HR, optical only (ECG), beats/min': agreement(win['hr_chrom_gate'], win['hr_ref'], subj, aami=True),
        'HR, acoustic only (ECG), beats/min': agreement(win['hr_acoustic'], win['hr_ref'], subj, aami=True),
        'HR, fused (ECG), beats/min': agreement(win['hr_fused'], win['hr_ref'], subj, aami=True),
        'RR, optical, breaths/min': agreement(win['rr_est'], win['rr_ref'], subj),
        '$\\mathrm{SpO_2}$, exploratory, \\%': agreement(win['spo2_est'], win['spo2_ref'], subj),
    }
    if len(rms):
        table6['RMSSD, acoustic (ECG R--R), ms'] = agreement(rms['rmssd_est'], rms['rmssd_ref'], rms['participant'].to_numpy())

    table7 = {}
    for cfg in CONFIGS:
        col = f'hr_{cfg}'
        table7[cfg] = {c: agreement(g[col], g['hr_ref'], g['participant'].to_numpy()).get('mae', np.nan)
                       for c, g in win.groupby('condition')}
        table7[cfg]['All'] = agreement(win[col], win['hr_ref'], subj).get('mae', np.nan)

    bench = pd.DataFrame([bench_metrics(s) for s in sessions])
    bench.to_csv(os.path.join(args.out, 'bench.csv'), index=False)

    pd.DataFrame(table6).T.to_csv(os.path.join(args.out, 'table6_agreement.csv'))
    pd.DataFrame(table7).T.to_csv(os.path.join(args.out, 'table7_hr_mae_by_condition.csv'))
    with open(os.path.join(args.out, 'tables.tex'), 'w') as fh:
        fh.write('% Table VI rows (paste into tab:agreement)\n' + latex_rows(table6) + '\n\n')
        fh.write('% Table VII rows (HR MAE, beats/min)\n')
        conds = sorted({c for v in table7.values() for c in v if c != 'All'})
        fh.write('% columns: ' + ' & '.join(conds + ['All']) + '\n')
        names = {'green': 'Green channel only', 'chrom_nogate': 'CHROM, no gate', 'chrom_gate': 'CHROM + face gate',
                 'acoustic': 'Acoustic PCG only', 'fused': 'Fused (Eq.~\\ref{eq:fusion})'}
        for cfg in CONFIGS:
            fh.write(names[cfg] + ' & ' + ' & '.join(fmt(table7[cfg].get(c)) for c in conds + ['All']) + ' \\\\\n')
        b = bench.mean(numeric_only=True)
        fh.write(f'\n% Table VIII (means over sessions): fps {fmt(b.get("fps"))}, jitter SD {fmt(b.get("jitter_sd_ms"),1)} ms, '
                 f'frame loss {fmt(b.get("frame_loss_pct"))} %, JPEG {fmt(b.get("jpeg_kb"))} kB, '
                 f'audio loss {fmt(b.get("audio_loss_pct"))} %\n')
    try:
        bland_altman_plots(win, args.out)
    except Exception as exc:
        print(f'plots skipped: {exc}', file=sys.stderr)

    print(f'N participants (test): {win["participant"].nunique()}, windows: {len(win)}')
    for k, v in table6.items():
        print(f'{k:45s} ' + ', '.join(f'{m}={fmt(x)}' for m, x in v.items()))
    print(f'results written to {args.out}')


def bland_altman_plots(win, out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    pairs = [('hr_fused', 'hr_ref', 'Heart rate (beats/min)'), ('rr_est', 'rr_ref', 'Respiration (breaths/min)')]
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.8))
    for ax, (e, r, label) in zip(axes, pairs):
        d = win[[e, r, 'participant']].dropna()
        if len(d) < 2:
            ax.set_title(f'{label}: insufficient data', fontsize=8)
            continue
        mean, diff = (d[e] + d[r]) / 2, d[e] - d[r]
        bias, lo, hi = repeated_measures_loa(diff.to_numpy(), d['participant'].to_numpy())
        ax.scatter(mean, diff, s=8, color='#0F6A4A')
        for y, ls in [(bias, '-'), (lo, '--'), (hi, '--')]:
            ax.axhline(y, color='#B85430' if ls == '--' else '#3A3A3A', ls=ls, lw=1)
        ax.set_xlabel(f'Mean of system and reference, {label}', fontsize=8)
        ax.set_ylabel('System - reference', fontsize=8)
        ax.tick_params(labelsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(out, 'bland_altman.pdf'))
    fig.savefig(os.path.join(out, 'bland_altman.png'), dpi=200)


if __name__ == '__main__':
    main()
