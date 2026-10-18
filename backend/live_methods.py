"""Live comparison of rPPG methods for the dashboard.

Runs the pretrained deep models from rPPG-Toolbox (TS-CAN, PhysNet, EfficientPhys; PURE-trained
weights, so cross-dataset for any user) on the last 30 s of face crops, every UPDATE_S seconds,
in a background thread. Preprocessing and HR post-processing are those of the benchmark
(benchmark/sv_bench), so live numbers are computed exactly as in the reported evaluation.

The deep models need full face video (trained at 30 fps; frames are interpolated onto a 30 Hz grid
from >= 12 fps): they run on the host webcam; the ESP32-S3 stream (5 fps video) is too slow for them.
If PyTorch or the weights are missing, the panel says so and the rest of the system is unaffected.
"""
import os
import sys
import threading
import time
from collections import deque

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.join(os.path.dirname(HERE), 'benchmark')
MODELS = ('TS-CAN', 'PhysNet', 'EfficientPhys')
WINDOW_S = 30.0
MIN_S = 20.0
MIN_FPS = 12.0          # below this the 30 Hz input the models were trained on cannot be interpolated well
UPDATE_S = 12.0         # deep models are slow on a laptop: refresh every 12 s
FS = 30.0


class LiveDeepModels:
    def __init__(self, train='PURE'):
        self.lock = threading.Lock()
        self.frames = deque()                 # (t, 72x72 RGB crop) of gated frames
        self.results = {}                     # name -> dict(hr, ms)
        self.status = 'loading'
        self.updated_at = None
        self.models = []
        self.train = train
        threading.Thread(target=self._load_and_run, daemon=True).start()

    # ------------------------------------------------------------ input
    def add_frame(self, bgr, t, face_rect, gated):
        """Called for every processed frame. Keeps 72x72 crops of the face box enlarged 1.5x
        (rPPG-Toolbox preprocessing) while the face gate passes."""
        if not gated or face_rect is None or not self.models:
            return
        h, w = bgr.shape[:2]
        x, y, fw, fh = [float(v) for v in face_rect]
        x0, y0 = max(0, int(x - 0.25 * fw)), max(0, int(y - 0.25 * fh))
        x1, y1 = min(w, int(x + 1.25 * fw)), min(h, int(y + 1.25 * fh))
        if x1 - x0 < 20 or y1 - y0 < 20:
            return
        crop = cv2.resize(cv2.cvtColor(bgr[y0:y1, x0:x1], cv2.COLOR_BGR2RGB), (72, 72), interpolation=cv2.INTER_AREA)
        with self.lock:
            if self.frames and t <= self.frames[-1][0]:
                return
            self.frames.append((t, crop))
            while self.frames and self.frames[-1][0] - self.frames[0][0] > WINDOW_S + 1.0:
                self.frames.popleft()

    def reset(self):
        with self.lock:
            self.frames.clear()
            self.results = {}
            self.updated_at = None

    # ------------------------------------------------------------ worker
    def _load_and_run(self):
        try:
            if BENCH not in sys.path:
                sys.path.insert(0, BENCH)
            import torch
            torch.set_num_threads(2)               # leave the CPU to frame capture and face detection
            from sv_bench import dl, methods
            self._dl, self._methods = dl, methods
            device = 'cuda' if torch.cuda.is_available() else 'mps' if torch.backends.mps.is_available() else 'cpu'
            for name in MODELS:
                # PhysNet's 3-D pooling / transposed convolutions are missing on Apple MPS: dl.load_model
                # puts it on the CPU (about 2 s per 30 s window, fine at one update every UPDATE_S).
                wf = dl.weights_file(name, self.train)
                if os.path.isfile(wf):
                    self.models.append((name, dl.load_model(name, wf, device)))
            if not self.models:
                self.status = f'no pretrained weights found (clone rPPG-Toolbox into {os.path.join(BENCH, "third_party")})'
                return
            self.status = f'ready ({len(self.models)} models, {self.train}-trained, {device})'
        except Exception as exc:                       # torch missing etc.: panel shows why
            self.status = f'unavailable: {exc.__class__.__name__}: {exc}'
            return
        while True:
            time.sleep(UPDATE_S)
            try:
                self._update()
            except Exception as exc:
                self.status = f'error: {exc}'

    def _update(self):
        with self.lock:
            frames = list(self.frames)
        if len(frames) < 2:
            self.status = 'waiting for a gated face'
            return
        t = np.array([f[0] for f in frames])
        span = t[-1] - t[0]
        fps = (len(t) - 1) / max(span, 1e-6)
        if span < MIN_S:
            self.status = f'buffering {span:.0f}/{MIN_S:.0f} s'
            return
        if fps < MIN_FPS:
            self.status = f'needs >= {MIN_FPS:.0f} fps video (have {fps:.0f}); use the Mac webcam'
            return
        # 30 Hz grid: each grid frame is a linear blend of the two captured frames around it
        tu = np.arange(t[0], t[-1], 1.0 / FS)
        stack = np.stack([f[1] for f in frames]).astype(np.float32)
        j = np.clip(np.searchsorted(t, tu, side='right') - 1, 0, len(t) - 2)
        w = np.clip((tu - t[j]) / np.maximum(t[j + 1] - t[j], 1e-6), 0, 1)[:, None, None, None]
        crops = ((1 - w) * stack[j] + w * stack[j + 1]).astype(np.uint8)
        out = {}
        for name, model in self.models:
            t0 = time.perf_counter()
            pred, _ = self._dl.predict(name, model, crops, next(model.parameters()).device)
            hr = self._methods.fft_hr(self._methods.postprocess(np.cumsum(pred), FS), FS) if len(pred) > 2 * FS else None
            out[name] = dict(hr=None if hr is None else round(hr, 1), ms=round(1000 * (time.perf_counter() - t0)))
        with self.lock:
            self.results = out
            self.updated_at = time.time()
        self.status = f'live ({len(self.models)} models, {self.train}-trained), {span:.0f} s window at {fps:.0f} fps'

    def snapshot(self):
        with self.lock:
            age = None if self.updated_at is None else round(time.time() - self.updated_at, 1)
            return dict(status=self.status, results=dict(self.results), age_s=age)
