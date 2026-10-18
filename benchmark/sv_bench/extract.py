"""One pass over a recording's frames, cached to <cache>/<dataset>/<rec_id>.npz.

  t          per-frame timestamps (s)
  sv_rgb     SonicVitals front end: mean RGB of the gated skin boxes from the live RPPGEngine
             (face detection, box smoothing, ROI lock and the five-test face gate); NaN where the
             gate failed, exactly the samples the live system would analyse
  sv_face    1 where the engine found a face
  face_rgb   mean RGB of the toolbox face crop (first-frame Haar box x1.5, 72 x 72) used by the
             GREEN / CHROM / POS baselines, as in rPPG-Toolbox's unsupervised evaluation
  crops      the 72 x 72 crops themselves (uint8), input to the deep models
  ppg        reference PPG interpolated onto t
"""
import dataclasses
import multiprocessing as mp
import os
import shutil
import tempfile
import time

import cv2
import numpy as np

from . import dl


def cache_path(cache_dir, rec):
    return os.path.join(cache_dir, rec.dataset, rec.rec_id + '.npz')


def extract(rec, cache_dir, keep_crops=True, max_seconds=None, log=print):
    path = cache_path(cache_dir, rec)
    if os.path.isfile(path):
        return dict(np.load(path))
    from rppg_engine import RPPGEngine
    engine = RPPGEngine(update_interval_s=1e9)          # estimation is done by the evaluator
    t_all, sv_rgb, sv_face, face_rgb, crops, sv_patches, bg = [], [], [], [], [], [], []
    box = None
    t0 = time.perf_counter()
    for t, rgb in rec.frames():
        if max_seconds is not None and t > max_seconds:
            break
        if len(t_all) and len(t_all) % 500 == 0:
            log(f'    {len(t_all)} frames ({time.perf_counter() - t0:.0f} s)')
        if box is None:
            box = dl.toolbox_face_box(rgb)
        crop = dl.crop_resize(rgb, box)
        face_rgb.append(crop.reshape(-1, 3).mean(axis=0))
        if keep_crops:
            crops.append(crop)
        _, record = engine.process_frame(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), t)
        sv_face.append(1 if record['face_found'] else 0)
        sv_rgb.append(record['rgb'] if record['gated'] and record['rgb'] is not None else (np.nan,) * 3)
        pt = record.get('patches') if record['gated'] else None
        sv_patches.append(pt if pt is not None and len(pt) == 4 else [(np.nan,) * 3] * 4)
        bg.append(engine.bg_rgb[-1] if engine.bg_rgb and engine.bg_t and engine.bg_t[-1] == t else (np.nan,) * 3)
        t_all.append(t)
    if len(t_all) < 2:
        raise RuntimeError(f'no frames decoded from {rec.frames_path}')
    t_all = np.asarray(t_all, float)
    out = dict(t=t_all, sv_rgb=np.asarray(sv_rgb, float), sv_face=np.asarray(sv_face, np.uint8),
               face_rgb=np.asarray(face_rgb, float), ppg=rec.ppg_at(t_all),
               sv_patches=np.asarray(sv_patches, float), bg_rgb=np.asarray(bg, float),
               extract_s=np.float64(time.perf_counter() - t0))
    if keep_crops:
        out['crops'] = np.asarray(crops, np.uint8)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    np.savez_compressed(path, **out)
    log(f'  extracted {rec.rec_id}: {len(t_all)} frames, face gate passed {np.mean(~np.isnan(out["sv_rgb"][:, 0])):.0%}, '
        f'{out["extract_s"]:.0f} s')
    return out


def _child(rec, cache_dir, keep_crops, max_seconds):
    extract(rec, cache_dir, keep_crops, max_seconds, log=lambda m: print(m, flush=True))


def extract_safe(rec, cache_dir, keep_crops=True, max_seconds=None, log=print):
    """extract() in a child process, so a crash inside a native video decoder cannot kill the run.

    Videos on a network mount (Google Drive in Colab) are first copied to local disk. If the
    OpenCV reader crashes, the video is decoded once more through the ffmpeg CLI. Returns the
    extracted data, or None if the recording could not be read (it is then skipped).
    """
    path = cache_path(cache_dir, rec)
    if os.path.isfile(path):
        return dict(np.load(path))
    local = rec
    tmp = None
    if not os.path.isdir(rec.frames_path) and rec.frames_path.startswith('/content/drive'):
        tmp = tempfile.mkdtemp(prefix='sv_video_')
        t0 = time.perf_counter()
        dst = os.path.join(tmp, os.path.basename(rec.frames_path))
        shutil.copyfile(rec.frames_path, dst)
        local = dataclasses.replace(rec, frames_path=dst)
        log(f'  copied video to local disk in {time.perf_counter() - t0:.0f} s')
    try:
        log(f'  video: {local.video_info()}')
        ctx = mp.get_context('spawn')
        for reader in ('opencv', 'ffmpeg'):
            p = ctx.Process(target=_child, args=(dataclasses.replace(local, reader=reader), cache_dir, keep_crops,
                                                 max_seconds))
            p.start()
            p.join()
            if p.exitcode == 0 and os.path.isfile(path):
                return dict(np.load(path))
            log(f'  {reader} reader failed on {rec.rec_id} (exit code {p.exitcode})'
                + ('; retrying with ffmpeg' if reader == 'opencv' else '; recording skipped'))
        return None
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
