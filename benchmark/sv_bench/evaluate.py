"""Windowed HR evaluation of every method on one extracted recording.

Ground-truth HR per window: the contact PPG in the same window, post-processed exactly like the
predictions (methods.postprocess + methods.fft_hr). Window = 30 s, step 10 s by default (the
live system analyses up to 30 s); a whole-video window is also reported ("video level", the
rPPG-Toolbox default protocol).

SonicVitals is evaluated three ways:
  SonicVitals (raw)      vitals_dsp.estimate_optical HR in every window, ignoring its quality gate
  SonicVitals (gated)    only windows where hr_ok is True (the gate's coverage is reported)
  SonicVitals (display)  the live dashboard value: estimates every 2 s on a 30 s buffer with peak
                         tracking, 3-in-a-row confirmation (+-5 BPM in 12 s), median-of-3 + EMA and
                         a 15 s hold, sampled at the window end (same rules as usb_streamer.py)
"""
import time

import numpy as np

import vitals_dsp as dsp
from . import methods

DISPLAY = dict(update_s=2.0, buffer_s=30.0, median_n=3, confirm_bpm=5.0, confirm_s=12.0,
               jump_bpm=12.0, hold_s=15.0, ema=0.2, prior_ttl_s=15.0)


def windows(t, win_s, step_s):
    if t[-1] - t[0] < win_s:
        return []
    starts = np.arange(t[0], t[-1] - win_s + 1e-6, step_s)
    return [(s, s + win_s) for s in starts]


def video_fs(t):
    return 1.0 / float(np.median(np.diff(t)))


def gt_hr(data, a, b, fs):
    m = (data['t'] >= a) & (data['t'] < b)
    return methods.fft_hr(methods.postprocess(data['ppg'][m], fs), fs)


def sonicvitals_display(data):
    """Replays the live system over the recording; returns [(t, displayed HR or None)]."""
    t, rgb = data['t'], data['sv_rgb']
    ok = ~np.isnan(rgb[:, 0])
    P = DISPLAY
    shown, recent, disp, fresh_t, prior, prior_t = [], [], None, None, None, None
    for now in np.arange(t[0] + P['update_s'], t[-1] + 1e-6, P['update_s']):
        m = ok & (t <= now) & (t > now - P['buffer_s'])
        if prior_t is not None and now - prior_t > P['prior_ttl_s']:
            prior = None
        o = dsp.estimate_optical(t[m], rgb[m], prior_hr=prior)
        hr = o['hr'] if o['hr_ok'] else None
        if hr is not None:
            prior, prior_t = hr, now
        recent = [(tt, h) for tt, h in recent if now - tt <= P['confirm_s']]
        new = None
        if hr is not None:
            recent = (recent + [(now, hr)])[-P['median_n']:]
            vals = np.array([h for _, h in recent])
            med = float(np.median(vals))
            confirmed = len(vals) == P['median_n'] and np.all(np.abs(vals - med) <= P['confirm_bpm'])
            if disp is None and confirmed:
                new = med
            elif disp is not None and (abs(med - disp) <= P['jump_bpm'] or confirmed):
                new = med
        if new is not None:
            disp = new if disp is None else (1 - P['ema']) * disp + P['ema'] * new
            fresh_t = now
        elif disp is not None and now - fresh_t > P['hold_s']:
            disp = None
        shown.append((now, disp))
    return shown


def sonicvitals_tracked(data):
    """Replays the live ensemble spectrum + HR tracker every 2 s on a 30 s buffer: [(t, hr, conf)]."""
    t = data['t']
    patches = data.get('sv_patches')
    if patches is None:                                   # older caches: one summed region
        patches = data['sv_rgb'][:, None, :]
    ok = np.all(np.isfinite(patches.reshape(len(t), -1)), axis=1)
    bg = data.get('bg_rgb')
    bok = np.all(np.isfinite(bg), axis=1) if bg is not None else None
    trk = dsp.HRTracker()
    out = []
    for now in np.arange(t[0] + DISPLAY['update_s'], t[-1] + 1e-6, DISPLAY['update_s']):
        m = ok & (t <= now) & (t > now - DISPLAY['buffer_s'])
        kw = {}
        if bok is not None:
            mb = bok & (t <= now) & (t > now - DISPLAY['buffer_s'])
            kw = dict(bg_t=t[mb], bg_rgb=bg[mb])
        spec = dsp.ensemble_spectrum(t[m], patches[m], **kw)[0] if m.sum() > 25 else None
        h, c = trk.update(spec, now)
        out.append((now, h, c))
    return out


def evaluate_recording(rec, data, dl_preds=None, win_s=30.0, step_s=10.0, baseline_inputs=('face',)):
    """Returns (rows, latency) where rows are dicts: rec, window, method, hr_gt, hr_pred."""
    fs = video_fs(data['t'])
    t = data['t']
    rows, lat = [], {}

    def add(method, a, b, gt, pred, **extra):
        rows.append(dict(dataset=rec.dataset, rec=rec.rec_id, subject=rec.subject, start=round(a - t[0], 2),
                         end=round(b - t[0], 2), method=method, hr_gt=gt, hr_pred=pred, **extra))

    def timed(key, fn):
        t0 = time.perf_counter()
        r = fn()
        lat.setdefault(key, []).append(time.perf_counter() - t0)
        return r

    display = sonicvitals_display(data)
    tracked = sonicvitals_tracked(data)
    wins = windows(t, win_s, step_s)
    full = [(t[0], t[-1] + 1e-6)]
    for level, ws in (('window', wins), ('video', full)):
        for a, b in ws:
            gt = gt_hr(data, a, b, fs)
            if gt is None:
                continue
            m = (t >= a) & (t < b)
            for src in baseline_inputs:
                x = data['face_rgb'][m] if src == 'face' else data['sv_rgb'][m & ~np.isnan(data['sv_rgb'][:, 0])]
                if len(x) < 2 * fs:
                    continue
                for name, fn in methods.BASELINES.items():
                    label = name if src == 'face' else f'{name} (SV skin boxes)'
                    hr = timed(label, lambda: methods.fft_hr(methods.postprocess(fn(x, fs), fs), fs))
                    add(label, a, b, gt, hr, level=level)
            okm = m & ~np.isnan(data['sv_rgb'][:, 0])
            o = timed('SonicVitals', lambda: dsp.estimate_optical(t[okm], data['sv_rgb'][okm]))
            add('SonicVitals (raw)', a, b, gt, o['hr'], level=level, snr=o['snr'], consensus=o['consensus'])
            add('SonicVitals (gated)', a, b, gt, o['hr'] if o['hr_ok'] else None, level=level, snr=o['snr'])
            if level == 'window':
                shown = [h for tt, h in display if tt <= b + 1e-6]
                add('SonicVitals (display)', a, b, gt, shown[-1] if shown else None, level=level)
                tr = [(h, c) for tt, h, c in tracked if tt <= b + 1e-6]
                h, c = tr[-1] if tr else (None, 0.0)
                add('SonicVitals (tracked)', a, b, gt, h, level=level, conf=c)
                add('SonicVitals (tracked, high conf.)', a, b, gt, h if c >= dsp.TRACKER_HIGH_CONF else None,
                    level=level, conf=c)
            for name, pred in (dl_preds or {}).items():
                n = min(len(pred), len(t))
                mm = m[:n]
                if mm.sum() < 2 * fs:
                    continue
                bvp = np.cumsum(pred[:n][mm])
                add(name, a, b, gt, methods.fft_hr(methods.postprocess(bvp, fs), fs), level=level)
    return rows, lat


def summarize(df):
    """Per method and level: windows, coverage, MAE, RMSE, MAPE, Pearson r, share within 5 BPM."""
    import pandas as pd
    out = []
    for (level, method), g in df.groupby(['level', 'method'], sort=False):
        v = g.dropna(subset=['hr_pred'])
        e = v.hr_pred - v.hr_gt
        r = float(np.corrcoef(v.hr_pred, v.hr_gt)[0, 1]) if len(v) > 2 and v.hr_pred.std() > 0 else np.nan
        out.append(dict(level=level, method=method, windows=len(g), coverage=len(v) / max(len(g), 1),
                        MAE=e.abs().mean(), RMSE=np.sqrt((e ** 2).mean()), MAPE=(e.abs() / v.hr_gt).mean() * 100,
                        r=r, within5=(e.abs() <= 5).mean()))
    return pd.DataFrame(out)
