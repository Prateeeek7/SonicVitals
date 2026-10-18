"""Readers for rPPG datasets with contact-PPG ground truth.

Every reader yields `Recording`s. Frames are read lazily (one pass, RGB uint8) so a 1-2 GB
uncompressed video never has to fit in memory. The reference PPG is returned at its own
timestamps; `ppg_at(t)` interpolates it onto any time grid (e.g. the video frames).

Layouts (as distributed by the dataset authors):
  UBFC-rPPG DATASET_2 : <root>/subject*/vid.avi + ground_truth.txt (row 1 PPG, row 2 HR, row 3 time s)
  UBFC-rPPG DATASET_1 : <root>/<name>/vid.avi + gtdump.xmp (CSV: time ms, HR, SpO2, PPG)
  PURE                : <root>/XX-YY/XX-YY.json + <root>/XX-YY/XX-YY/Image*.png (timestamps in ns)
  VIPL-HR             : <root>/pN/vN/sourceN/video.avi + wave.csv (+ time.txt); source4 (NIR) is skipped
"""
import glob
import json
import os
import re
from dataclasses import dataclass, field

import cv2
import numpy as np


@dataclass
class Recording:
    dataset: str
    rec_id: str              # unique id, e.g. "subject12" or "03-04" or "p1_v1_source2"
    subject: str             # subject id (for subject-disjoint splits)
    frames_path: str         # video file or PNG directory
    ppg: np.ndarray          # reference PPG samples
    ppg_t: np.ndarray        # reference PPG timestamps (s, same clock as frame_times)
    frame_times: np.ndarray = field(default=None)   # per-frame timestamps (s); None -> index / fps
    fps: float = 30.0
    reader: str = 'opencv'   # 'opencv' or 'ffmpeg' (decode through the ffmpeg CLI; used as a fallback)

    def frames(self):
        """Yields (time_s, rgb_uint8) for every frame."""
        if self.reader == 'ffmpeg' and not os.path.isdir(self.frames_path):
            yield from self._ffmpeg_frames()
            return
        if os.path.isdir(self.frames_path):
            files = sorted(glob.glob(os.path.join(self.frames_path, '*.png')))
            for i, f in enumerate(files):
                img = cv2.imread(f)
                if img is None:
                    continue
                yield self._t(i), cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            return
        cap = cv2.VideoCapture(self.frames_path)
        i = 0
        while True:
            ok, img = cap.read()
            if not ok:
                break
            yield self._t(i), cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            i += 1
        cap.release()

    def _ffmpeg_frames(self):
        import subprocess
        cap = cv2.VideoCapture(self.frames_path)
        w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        if w <= 0 or h <= 0:
            return
        proc = subprocess.Popen(['ffmpeg', '-v', 'quiet', '-i', self.frames_path, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        n = w * h * 3
        i = 0
        try:
            while True:
                buf = proc.stdout.read(n)
                if len(buf) < n:
                    break
                yield self._t(i), np.frombuffer(buf, np.uint8).reshape(h, w, 3)
                i += 1
        finally:                       # also when the consumer stops early
            proc.kill()
            proc.stdout.close()
            proc.wait()

    def video_info(self):
        if os.path.isdir(self.frames_path):
            return f'{len(glob.glob(os.path.join(self.frames_path, "*.png")))} PNG frames'
        cap = cv2.VideoCapture(self.frames_path)
        fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
        info = (f'{int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}, '
                f'{cap.get(cv2.CAP_PROP_FPS):.1f} fps, {int(cap.get(cv2.CAP_PROP_FRAME_COUNT))} frames, '
                f'codec {"".join(chr((fourcc >> 8 * k) & 255) for k in range(4)).strip() or "raw"}, '
                f'{os.path.getsize(self.frames_path) / 1e9:.2f} GB')
        cap.release()
        return info

    def _t(self, i):
        if self.frame_times is not None and i < len(self.frame_times):
            return float(self.frame_times[i])
        return i / self.fps

    def ppg_at(self, t):
        return np.interp(t, self.ppg_t, self.ppg)


def _video_fps(path, default=30.0):
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    return (fps if fps and 1 < fps < 240 else default), n


def ubfc_rppg(root):
    """UBFC-rPPG (Bobbia et al., PRL 2017), DATASET_2 and DATASET_1 layouts."""
    out = []
    for d in sorted(glob.glob(os.path.join(root, '*')), key=lambda p: [int(x) if x.isdigit() else x
                                                                       for x in re.split(r'(\d+)', p)]):
        vid = os.path.join(d, 'vid.avi')
        if not os.path.isfile(vid):
            continue
        fps, n = _video_fps(vid)
        name = os.path.basename(d)
        gt2, gt1 = os.path.join(d, 'ground_truth.txt'), os.path.join(d, 'gtdump.xmp')
        if os.path.isfile(gt2):
            rows = [np.array([float(v) for v in line.split()]) for line in open(gt2) if line.strip()]
            ppg, ts = rows[0], rows[2] if len(rows) > 2 else np.arange(len(rows[0])) / fps
        elif os.path.isfile(gt1):
            a = np.loadtxt(gt1, delimiter=',')
            ppg, ts = a[:, 3], (a[:, 0] - a[0, 0]) / 1000.0
        else:
            continue
        # The PPG is logged once per video frame; when the counts match, use frame time directly.
        if n and abs(len(ppg) - n) <= 2:
            ts = np.arange(len(ppg)) / fps
        out.append(Recording('UBFC-rPPG', name, name, vid, ppg.astype(float), np.asarray(ts, float), fps=fps))
    return out


def pure(root):
    """PURE (Stricker et al., RO-MAN 2014). 30 fps PNG frames, pulse oximeter at 60 Hz, ns timestamps."""
    out = []
    for d in sorted(glob.glob(os.path.join(root, '*-*'))):
        name = os.path.basename(d)
        js = os.path.join(d, name + '.json')
        img_dir = os.path.join(d, name)
        if not (os.path.isfile(js) and os.path.isdir(img_dir)):
            continue
        meta = json.load(open(js))
        pk = meta['/FullPackage']
        t_ppg = np.array([p['Timestamp'] for p in pk], float) * 1e-9
        ppg = np.array([p['Value']['waveform'] for p in pk], float)
        t_img = np.array([im['Timestamp'] for im in meta['/Image']], float) * 1e-9
        t0 = t_img[0]
        out.append(Recording('PURE', name, name.split('-')[0], img_dir, ppg, t_ppg - t0,
                             frame_times=t_img - t0, fps=30.0))
    return out


def vipl_hr(root, sources=('source1', 'source2', 'source3')):
    """VIPL-HR (Niu et al., TIP 2019). BVP in wave.csv; the video and BVP span the same interval."""
    out = []
    for vid in sorted(glob.glob(os.path.join(root, 'p*', 'v*', 'source*', 'video.avi'))):
        d = os.path.dirname(vid)
        src = os.path.basename(d)
        if src not in sources:
            continue
        wave = os.path.join(d, 'wave.csv')
        if not os.path.isfile(wave):
            continue
        ppg = np.loadtxt(wave, delimiter=',', skiprows=1, usecols=0, ndmin=1).astype(float)
        fps, n = _video_fps(vid)
        ft = None
        tt = os.path.join(d, 'time.txt')
        if os.path.isfile(tt):
            ms = np.loadtxt(tt, ndmin=1)
            if len(ms) >= n * 0.9:
                ft = (ms - ms[0]) / 1000.0
        dur = (ft[-1] if ft is not None else n / fps)
        ppg_t = np.linspace(0, dur, len(ppg))
        p, v = d.split(os.sep)[-3], d.split(os.sep)[-2]
        out.append(Recording('VIPL-HR', f'{p}_{v}_{src}', p, vid, ppg, ppg_t, frame_times=ft, fps=fps))
    return out


READERS = {'ubfc': ubfc_rppg, 'pure': pure, 'vipl': vipl_hr}
