"""Optical (camera) engine: face detection, five-test validity gate, forehead ROI
traces with timestamps, and the on-demand colorimetric snapshot.

Signal processing itself lives in `vitals_dsp.py` so it can be re-run offline.
"""
import base64
import threading
import time

import cv2
import numpy as np

import vitals_dsp as dsp

# Diagnostic snapshot status codes (kept for the UI's CSS classes):
#   NORMAL = inside the software reference range, WARN = borderline, ALERT = outside.
# These thresholds are software settings, NOT clinically validated cut-offs.
RANGE_LABEL = {'NORMAL': 'IN RANGE', 'WARN': 'BORDERLINE', 'ALERT': 'OUT OF RANGE'}

PRIOR_TTL_S = 15.0        # an accepted HR guides peak tracking for this long
NODE_RGB_TTL_S = 2.0      # node raw-pixel samples count as active if one arrived this recently
GATE_HOLD_S = 4.0         # node samples are accepted while the last face-gate result is this recent
DETECT_MAX_W = 320        # face detection runs on a copy at most this wide (speed; the gate needs faces >= 20 % of width)
FACE_DEADBAND = 0.06      # detections within 6 % of the face size are treated as box jitter
TRACK_MAX_MISSES = 8       # consecutive unreliable tracker frames before the boxes re-lock
ROI_RELOCK_TRACKED = 0.15  # same, while the phase-correlation tracker follows the face
ROI_RELOCK = 0.05         # skin regions stay fixed until the face moves by more than 5 % of its width;
                          # a one-pixel box shift across the hairline or brows changes the mean by more than the pulse


class RPPGEngine:
    def __init__(self, fs=dsp.FS_OPT, warmup_s=dsp.MIN_SEG_HR_S, buffer_s=30.0,
                 update_interval_s=0.5, spo2_calibration=None):
        self.fs = fs
        self.warmup_s = warmup_s
        self.buffer_s = buffer_s
        self.update_interval_s = update_interval_s
        self.spo2_calibration = spo2_calibration

        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        self.face_cascade = cv2.CascadeClassifier(cascade_path)

        # Gated forehead traces: (t, R, G, B) for frames that passed the face gate
        self.t_hist = []
        self.rgb_hist = []
        self.patch_hist = []          # per skin patch mean RGB (P x 3) for each entry of t_hist
        self.tracker = dsp.HRTracker()
        self.async_estimate = False   # True in the live server: estimation runs off the camera thread
        self._estimating = False
        self.tracked = (None, 0.0)    # (HR, confidence) from the ensemble tracker
        self.ensemble_n = 0
        self.camera_rmssd = None
        # Background (wall beside / above the face) mean RGB, for rejecting lighting flicker
        self.bg_t = []
        self.bg_rgb = []

        self.frame_count = 0
        self.patient_detected = False
        self.last_face_time = None
        self.last_face_rect = None
        self.full_face_visible = False
        self.face_alignment_status = 'NO_PATIENT'
        self.face_guidance = 'Searching for patient face...'
        self.status = 'NO_PATIENT'

        self.optical = dsp.estimate_optical([], np.empty((0, 3)))
        self._last_update = 0.0
        self.segment_alive = False
        self.current_rois = None      # skin boxes of the last gated frame (sent to the node)
        self._mask_key = None         # boxes the skin masks were computed for
        self._tmpl = None             # face template for motion compensation (phase correlation)
        self._tmpl_rect = None
        self._tmpl_win = None
        self._shift = (0.0, 0.0)
        self._track_misses = 0
        self._masks = None
        self.locked_rect = None       # face box the skin regions are frozen to
        self.last_gate_t = None       # device time and result of the last face-gate check
        self.last_gate_ok = False
        self.node_rgb_t = None        # device time of the last raw-pixel sample from the node
        self.node_mode = False        # True while the buffer holds node samples instead of JPEG means
        self.node_samples_used = 0
        self.prior_hr = None          # last accepted HR, used for peak tracking
        self.prior_t = None
        self.last_ok_t = None         # time of the last accepted HR (for REACQUIRING)

        # Sharpest gated frame within a rolling window, used for the colorimetric snapshot
        self.best_moment = {'frame': None, 'sharpness': 0.0, 'face_rect': None,
                            'timestamp': 0.0, 'frame_index': None, 'full_face_visible': False}
        self.best_moment_window_start = time.time()
        self.best_moment_window_duration = 8.0
        self.latest_raw_frame = None

    # ------------------------------------------------------------ geometry
    @staticmethod
    def roi_boxes(fx, fy, fw, fh):
        """Five anatomical regions relative to the face box (paper Table V)."""
        return {
            'Forehead': (int(fx + 0.20 * fw), int(fy + 0.08 * fh), int(0.60 * fw), int(0.18 * fh)),
            'Left Cheek': (int(fx + 0.12 * fw), int(fy + 0.44 * fh), int(0.26 * fw), int(0.24 * fh)),
            'Right Cheek': (int(fx + 0.62 * fw), int(fy + 0.44 * fh), int(0.26 * fw), int(0.24 * fh)),
            'Sclera': (int(fx + 0.20 * fw), int(fy + 0.28 * fh), int(0.60 * fw), int(0.14 * fh)),
            'Lips': (int(fx + 0.28 * fw), int(fy + 0.74 * fh), int(0.44 * fw), int(0.18 * fh)),
        }

    @staticmethod
    def rppg_rois(fx, fy, fw, fh, w, h):
        """Skin boxes for the pulse signal: forehead (below the hairline, above the brows), both
        cheeks (below the eyes, above a moustache/beard line) and the nose. Checked on a real
        ESP32 frame: 84-96 % skin in every box, 2580 px at a 109 px face (old 3-box layout: 1790 px)."""
        boxes = []
        for (ax, ay, aw, ah) in [(0.20, 0.11, 0.60, 0.15),    # forehead
                                 (0.10, 0.50, 0.27, 0.18),    # left cheek
                                 (0.63, 0.50, 0.27, 0.18),    # right cheek
                                 (0.41, 0.44, 0.18, 0.22)]:   # nose
            x = max(0, int(fx + ax * fw))
            y = max(0, int(fy + ay * fh))
            boxes.append((x, y, max(2, min(w - x, int(aw * fw))), max(2, min(h - y, int(ah * fh)))))
        return boxes

    @staticmethod
    def roi_mean_rgb(bgr_img, boxes, masks=None):
        """Pixel-weighted mean (R, G, B) over all boxes (only the masked skin pixels when a mask is
        given for a box), or None if they are empty."""
        total = np.zeros(3)
        n = 0
        for k, (x, y, bw, bh) in enumerate(boxes):
            patch = bgr_img[y:y + bh, x:x + bw]
            if not patch.size:
                continue
            m = masks[k] if masks is not None and k < len(masks) else None
            if m is not None and m.shape == patch.shape[:2]:
                px = patch[m]
                total += px.sum(axis=0)
                n += len(px)
            else:
                total += patch.reshape(-1, 3).sum(axis=0)
                n += patch.shape[0] * patch.shape[1]
        if n == 0:
            return None
        b, g, r = total / n
        return float(r), float(g), float(b)

    @staticmethod
    def skin_masks(bgr_img, boxes):
        """Per-box skin masks (YCrCb skin colour, eroded) computed once per ROI lock, so eyebrows,
        hair, beard and shadow inside a box are left out without the pixel set changing every
        frame. A box with under 30 % skin falls back to all its pixels (mask None)."""
        out = []
        for (x, y, bw, bh) in boxes:
            patch = bgr_img[y:y + bh, x:x + bw]
            if patch.size == 0:
                out.append(None)
                continue
            ycc = cv2.cvtColor(patch, cv2.COLOR_BGR2YCrCb)
            m = ((ycc[..., 1] >= 133) & (ycc[..., 1] <= 175) & (ycc[..., 2] >= 77) & (ycc[..., 2] <= 127)
                 & (ycc[..., 0] > 35) & (ycc[..., 0] < 240)).astype(np.uint8)
            m = cv2.erode(m, np.ones((3, 3), np.uint8)).astype(bool)
            out.append(m if m.mean() >= 0.30 else None)
        return out

    TMPL = 96                             # template size (px) for the phase-correlation face tracker

    def _set_template(self, gray, rect):
        x, y, fw, fh = [int(v) for v in rect]
        h, w = gray.shape[:2]
        crop = gray[max(0, y):min(h, y + fh), max(0, x):min(w, x + fw)]
        if crop.size < 400:
            self._tmpl, self._tmpl_rect = None, rect
            return
        self._tmpl = cv2.resize(crop, (self.TMPL, self.TMPL), interpolation=cv2.INTER_AREA).astype(np.float32)
        self._tmpl_rect = rect
        self._tmpl_win = cv2.createHanningWindow((self.TMPL, self.TMPL), cv2.CV_32F)
        self._shift = (0.0, 0.0)
        self._track_misses = 0

    def _face_shift(self, gray, w, h):
        """Sub-pixel (dx, dy) of the face relative to the template, in image pixels.

        The comparison window follows the last estimate (rounded), so phase correlation only has
        to measure the small step since the previous frame and keeps a sharp peak; the template
        itself never changes, so the estimate does not drift. Implausible or low-confidence
        results keep the previous shift; after TRACK_MAX_MISSES of them the boxes re-lock.
        """
        if self._tmpl is None or self._tmpl_rect is None:
            return self._shift
        x, y, fw, fh = [int(v) for v in self._tmpl_rect]
        ox, oy = int(round(self._shift[0])), int(round(self._shift[1]))
        if x + ox < 0 or y + oy < 0 or x + ox + fw > w or y + oy + fh > h:
            self._track_misses += 1
            return self._shift
        cur = cv2.resize(gray[y + oy:y + oy + fh, x + ox:x + ox + fw], (self.TMPL, self.TMPL),
                         interpolation=cv2.INTER_AREA).astype(np.float32)
        # copies: cv2.phaseCorrelate (OpenCV 4.13) applies the window to its inputs in place
        (sx, sy), resp = cv2.phaseCorrelate(self._tmpl.copy(), cur, self._tmpl_win)
        nx, ny = ox + float(sx) * fw / self.TMPL, oy + float(sy) * fh / self.TMPL
        if resp >= 0.15 and max(abs(nx - self._shift[0]), abs(ny - self._shift[1])) <= 0.12 * fw:
            self._shift, self._track_misses = (nx, ny), 0
        else:
            self._track_misses += 1
        return self._shift

    @staticmethod
    def _sample_patches(bgr, rois, dx, dy, masks):
        """Mean RGB and pixel count of each box sampled at (box + shift) with sub-pixel accuracy;
        the per-box skin mask moves with the box. None if a box is empty."""
        out = []
        h, w = bgr.shape[:2]
        for k, (x, y, bw, bh) in enumerate(rois):
            cx, cy = x + dx + (bw - 1) / 2.0, y + dy + (bh - 1) / 2.0
            if bw < 2 or bh < 2 or cx < 0 or cy < 0 or cx >= w or cy >= h:
                return None
            patch = cv2.getRectSubPix(bgr, (int(bw), int(bh)), (cx, cy))
            m = masks[k] if masks is not None and k < len(masks) else None
            px = patch[m] if m is not None and m.shape == patch.shape[:2] else patch.reshape(-1, 3)
            if len(px) == 0:
                return None
            b, g, r = px.reshape(-1, 3).mean(axis=0)
            out.append(((float(r), float(g), float(b)), len(px)))
        return out

    def _locked_face(self, rect, tol=ROI_RELOCK):
        """Face box used for the skin regions: frozen until the face moves by more than tol."""
        if self.locked_rect is not None:
            lx, ly, lw, lh = self.locked_rect
            move = max(abs(rect[0] + rect[2] / 2 - lx - lw / 2), abs(rect[1] + rect[3] / 2 - ly - lh / 2),
                       abs(rect[2] - lw), abs(rect[3] - lh)) / max(lw, 1)
            if move <= tol:
                return self.locked_rect
        self.locked_rect = tuple(int(v) for v in rect)
        return self.locked_rect

    def _detect_faces(self, gray_eq):
        """Haar detection on a copy at most DETECT_MAX_W wide (boxes scaled back to full size).

        The face gate needs a face at least 20 % of the frame width, i.e. >= 64 px at 320 px, so
        the smaller copy finds the same faces at about a quarter of the cost of a 640 x 480 frame.
        """
        h, w = gray_eq.shape[:2]
        scale = min(1.0, DETECT_MAX_W / float(w))
        small = gray_eq if scale >= 1.0 else cv2.resize(gray_eq, (int(round(w * scale)), int(round(h * scale))),
                                                        interpolation=cv2.INTER_AREA)
        faces = self.face_cascade.detectMultiScale(small, scaleFactor=1.08, minNeighbors=3, minSize=(28, 28))
        if scale >= 1.0 or len(faces) == 0:
            return faces
        return np.round(np.asarray(faces, float) / scale).astype(int)

    def _smooth_face(self, rect):
        """Smooth the Haar box: heavy smoothing for jitter, faster tracking for real movement."""
        if self.last_face_rect is None:
            self.last_face_rect = [float(v) for v in rect]
            return
        fx, fy, fw, fh = self.last_face_rect
        shift = max(abs(rect[0] + rect[2] / 2 - fx - fw / 2), abs(rect[1] + rect[3] / 2 - fy - fh / 2),
                    abs(rect[2] - fw), abs(rect[3] - fh)) / max(fw, 1.0)
        a = 0.05 if shift < FACE_DEADBAND else 0.4
        for i, target in enumerate(rect):
            self.last_face_rect[i] = (1 - a) * self.last_face_rect[i] + a * float(target)

    def validate_full_face(self, bgr_img, face_rect):
        """Five-test gate (paper Sec. V-A). Returns (passed, status_code, guidance)."""
        if bgr_img is None or face_rect is None:
            return False, 'NO_IMAGE', 'No sensor image available'

        h, w = bgr_img.shape[:2]
        fx, fy, fw, fh = [int(v) for v in face_rect]

        # 1. Edge clearance
        margin_x = max(6, int(0.035 * w))
        margin_y = max(6, int(0.035 * h))
        if fx < margin_x:
            return False, 'CLIPPED_LEFT', 'Left side of face is cut off. Shift right into frame.'
        if (fx + fw) > (w - margin_x):
            return False, 'CLIPPED_RIGHT', 'Right side of face is cut off. Shift left into frame.'
        if fy < margin_y:
            return False, 'CLIPPED_TOP', 'Forehead is cut off at top. Lower camera or move down.'
        if (fy + fh) > (h - margin_y):
            return False, 'CLIPPED_BOTTOM', 'Chin is cut off at bottom. Raise camera or move up.'

        # 2. Scale
        if fw < int(0.20 * w) or fh < int(0.22 * h):
            return False, 'TOO_FAR', 'Face is too far away. Move closer to camera.'
        if fw > int(0.88 * w) or fh > int(0.90 * h):
            return False, 'TOO_CLOSE', 'Face is too close to camera. Move slightly back.'

        # 3. Aspect ratio
        aspect = float(fw) / float(max(1, fh))
        if aspect < 0.65:
            return False, 'NARROW_ASPECT', 'Face tilted or turned sideways. Look directly at camera.'
        if aspect > 1.30:
            return False, 'WIDE_ASPECT', 'Face aspect distorted. Look directly at camera.'

        # 4. ROI containment
        rois = self.roi_boxes(fx, fy, fw, fh)
        for name, (rx, ry, rw, rh) in rois.items():
            if rx < 2 or ry < 2 or (rx + rw) > (w - 2) or (ry + rh) > (h - 2):
                return False, 'ROI_TRUNCATED', f'{name} zone cut off by frame edge. Center face.'

        # 5. Illumination
        lc, rc = rois['Left Cheek'], rois['Right Cheek']
        lc_patch = bgr_img[lc[1]:lc[1] + lc[3], lc[0]:lc[0] + lc[2]]
        rc_patch = bgr_img[rc[1]:rc[1] + rc[3], rc[0]:rc[0] + rc[2]]
        if lc_patch.size > 0 and rc_patch.size > 0:
            lc_lum = float(np.mean(lc_patch))
            rc_lum = float(np.mean(rc_patch))
            if lc_lum < 15.0 or rc_lum < 15.0:
                return False, 'LOW_LIGHT', 'Lighting insufficient on face. Ensure direct light.'
            if abs(lc_lum - rc_lum) / (lc_lum + rc_lum + 1e-5) > 0.45:
                return False, 'OCCLUSION_OR_TURN', 'Face partially shaded or turned. Look straight ahead.'

        return True, 'FULL_FACE_OPTIMAL', 'Full face fully visible and centered'

    # ------------------------------------------------------------ per frame
    def reset(self):
        self.t_hist.clear()
        self.rgb_hist.clear()
        self.patch_hist.clear()
        self.tracker.reset()
        self.tracked = (None, 0.0)
        self.camera_rmssd = None
        self.patient_detected = False
        self.last_face_rect = None
        self.locked_rect = None
        self._tmpl, self._tmpl_rect, self._shift = None, None, (0.0, 0.0)
        self.optical = dsp.estimate_optical([], np.empty((0, 3)))
        self.status = 'NO_PATIENT'

    def _estimate(self, t, t_hist, rgb_hist, patches, bg_t, bg_rgb, prior_hr, face):
        """Optical estimate + ensemble tracker on a snapshot of the buffers (may run in a thread)."""
        try:
            optical = dsp.estimate_optical(t_hist, rgb_hist, fs=self.fs, spo2_calibration=self.spo2_calibration,
                                           prior_hr=prior_hr, bg_t=bg_t, bg_rgb=bg_rgb)
            if patches is None:
                patches = rgb_hist.reshape(-1, 1, 3)
            spec, n, _ = dsp.ensemble_spectrum(t_hist, patches, fs=self.fs, bg_t=bg_t, bg_rgb=bg_rgb)
            tracked = self.tracker.update(spec, t) if face else (None, 0.0)
            rmssd = dsp.camera_rmssd(optical['bvp'], self.fs, tracked[0]) \
                if tracked[0] is not None and tracked[1] >= dsp.TRACKER_HIGH_CONF else None
            self.optical, self.ensemble_n, self.tracked, self.camera_rmssd = optical, n, tracked, rmssd
            if optical['hr_ok'] and self._segment_alive(t):
                self.prior_hr, self.prior_t, self.last_ok_t = optical['hr'], t, t
        finally:
            self._estimating = False

    def _clear_buffer(self):
        self.t_hist.clear()
        self.rgb_hist.clear()
        self.patch_hist.clear()
        self.bg_t.clear()
        self.bg_rgb.clear()

    def _record_background(self, bgr_img, face, t):
        """Mean RGB of the regions left / right of the face and above the head (no skin)."""
        h, w = bgr_img.shape[:2]
        x, y, fw, fh = face
        m = int(0.15 * fw)
        y0, y1 = max(0, y), min(h, y + fh)
        parts = [bgr_img[y0:y1, :max(0, x - m)], bgr_img[y0:y1, min(w, x + fw + m):], bgr_img[:max(0, y - m), :]]
        px = np.concatenate([p.reshape(-1, 3) for p in parts if p.size]) if any(p.size for p in parts) else None
        if px is None:
            return
        # Skin-coloured pixels (ears, neck, hands) pulse too: keep only non-skin pixels.
        ycc = cv2.cvtColor(px.reshape(-1, 1, 3), cv2.COLOR_BGR2YCrCb).reshape(-1, 3)
        non_skin = ~((ycc[:, 1] > 133) & (ycc[:, 1] < 180) & (ycc[:, 2] > 77) & (ycc[:, 2] < 135))
        px = px[non_skin]
        if len(px) < 0.02 * w * h:           # face fills the frame: no usable background
            return
        b, g, r = px.mean(axis=0)
        if self.bg_t and t <= self.bg_t[-1]:
            return
        self.bg_t.append(t)
        self.bg_rgb.append((float(r), float(g), float(b)))
        while self.bg_t and self.bg_t[-1] - self.bg_t[0] > self.buffer_s + 2.0:
            self.bg_t.pop(0)
            self.bg_rgb.pop(0)

    def restart_signal(self):
        """Start a new analysis segment (e.g. after a camera exposure change) but keep the face lock."""
        self._clear_buffer()
        self.optical = dsp.estimate_optical([], np.empty((0, 3)))

    def _append(self, t, rgb, patches=None):
        if self.t_hist and t <= self.t_hist[-1]:
            return False
        self.t_hist.append(t)
        self.rgb_hist.append(rgb)
        # per-patch means for the ensemble (the node sends one summed region: a single patch)
        self.patch_hist.append(np.asarray(patches if patches is not None else [rgb], float))
        while self.t_hist and self.t_hist[-1] - self.t_hist[0] > self.buffer_s:
            self.t_hist.pop(0)
            self.rgb_hist.pop(0)
            self.patch_hist.pop(0)
        return True

    def add_node_rgb(self, t, rgb):
        """Raw-pixel skin mean computed on the node before JPEG compression (preferred source).

        Accepted only while the host's face gate recently passed, because the node sums the
        boxes the host sent from that gated frame. Returns True if the sample was used.
        """
        if not self.node_mode:
            self._clear_buffer()          # never mix JPEG-derived and raw-pixel means in one segment
            self.node_mode = True
        self.node_rgb_t = t
        if not (self.last_gate_ok and self.last_gate_t is not None and abs(t - self.last_gate_t) <= GATE_HOLD_S):
            return False
        used = self._append(t, rgb)
        self.node_samples_used += int(used)
        return used

    def _segment_alive(self, t):
        """The current segment is broken once no gated frame arrived for MAX_GAP_S."""
        return bool(self.t_hist) and t - self.t_hist[-1] <= dsp.MAX_GAP_S

    def process_frame(self, bgr_img, t=None):
        """Process one frame captured at time `t` (seconds; device clock if available).

        Returns (annotated_image, frame_record). frame_record holds the forehead
        ROI mean whenever a face is found, plus the gate result, so that the
        recorder can log ungated frames for the ablation study. Only gated frames
        enter the analysis buffer.
        """
        now = time.time()
        t = now if t is None else float(t)
        self.frame_count += 1
        self.latest_raw_frame = bgr_img
        h, w = bgr_img.shape[:2]

        gray = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2GRAY)
        gray_eq = cv2.equalizeHist(gray)
        faces = self._detect_faces(gray_eq)
        sharpness = float(cv2.Laplacian(gray_eq, cv2.CV_64F).var())
        annotated = bgr_img.copy()
        record = {'t': t, 'face_found': len(faces) > 0, 'gated': False, 'rgb': None}

        if len(faces) > 0:
            self._smooth_face(max(faces, key=lambda r: r[2] * r[3]))
            sfx, sfy, sfw, sfh = [int(round(v)) for v in self.last_face_rect]

            is_full, code, msg = self.validate_full_face(bgr_img, [sfx, sfy, sfw, sfh])
            self.full_face_visible = is_full
            self.face_alignment_status = code
            self.face_guidance = msg
            self.patient_detected = True
            self.last_face_time = t

            self._record_background(bgr_img, (sfx, sfy, sfw, sfh), t)
            # Motion compensation: shift of the face since the boxes were locked (sub-pixel phase
            # correlation). Re-locking is judged against the compensated position, so detector jitter
            # does not move the boxes; the boxes are sampled at the shifted position below.
            dx, dy = self._face_shift(gray, w, h)
            forced = False
            if self._tmpl_rect is not None and (max(abs(dx), abs(dy)) > 0.25 * self._tmpl_rect[2]
                                                or self._track_misses >= TRACK_MAX_MISSES):
                self.locked_rect = None               # moved too far / tracker lost: re-lock on the detection
                dx, dy, forced = 0.0, 0.0, True
            # the smoothed detection lags real motion, so with a live template the tolerance is wider
            locked = self._locked_face((sfx - dx, sfy - dy, sfw, sfh),
                                       ROI_RELOCK_TRACKED if self._tmpl is not None else ROI_RELOCK)
            if locked != self._tmpl_rect or forced:
                self._set_template(gray, locked)
                dx, dy = 0.0, 0.0
            rois = self.rppg_rois(*locked, w, h)
            shifted = [(int(round(x + dx)), int(round(y + dy)), bw, bh) for x, y, bw, bh in rois]
            self.current_rois = shifted if is_full else None
            self.last_gate_t, self.last_gate_ok = t, is_full
            if self.node_mode and (self.node_rgb_t is None or abs(t - self.node_rgb_t) > NODE_RGB_TTL_S):
                self.node_mode = False    # node stopped sending raw-pixel sums: fall back to JPEG means
                self._clear_buffer()
            key = tuple(rois)
            if key != self._mask_key:                 # boxes re-locked: recompute the skin masks once
                self._mask_key, self._masks = key, self.skin_masks(bgr_img, rois)
            patches = self._sample_patches(bgr_img, rois, dx, dy, self._masks)
            rgb = None
            if patches is not None:
                n = np.array([c for _, c in patches], float)
                rgb = tuple(float(v) for v in (np.array([m for m, _ in patches]) * n[:, None]).sum(0) / n.sum())
                patches = [m for m, _ in patches]
            if rgb is not None:
                record['rgb'] = rgb
                record['gated'] = is_full
                record['patches'] = patches
                if is_full and not self.node_mode:
                    self._append(t, rgb, patches)

            self._draw_face_overlay(annotated, is_full, code, (sfx, sfy, sfw, sfh), shifted, w, h)
            if is_full:
                self._update_best_moment(bgr_img, sharpness, [sfx, sfy, sfw, sfh], now)
        else:
            self.current_rois = None
            self.last_gate_t, self.last_gate_ok = t, False
            self.full_face_visible = False
            self.face_alignment_status = 'NO_PATIENT'
            self.face_guidance = 'Searching for patient face...'
            if self.last_face_time is None or t - self.last_face_time > dsp.MAX_GAP_S:
                self.reset()
            cv2.drawMarker(annotated, (w // 2, h // 2), (0, 140, 255), cv2.MARKER_CROSS, 20, 1)

        if now - self._last_update >= self.update_interval_s and not self._estimating:
            self._last_update = now
            if self.prior_t is not None and t - self.prior_t > PRIOR_TTL_S:
                self.prior_hr = None
            shapes = {p.shape for p in self.patch_hist}
            snap = (t, np.array(self.t_hist), np.array(self.rgb_hist).reshape(-1, 3),
                    np.stack(self.patch_hist) if len(shapes) == 1 and self.patch_hist else None,
                    list(self.bg_t), list(self.bg_rgb), self.prior_hr, self.patient_detected)
            if self.async_estimate:            # live server: never make the camera thread wait
                self._estimating = True
                threading.Thread(target=self._estimate, args=snap, daemon=True).start()
            else:
                self._estimate(*snap)

        alive = self.segment_alive = self._segment_alive(t)
        recent_ok = self.last_ok_t is not None and t - self.last_ok_t <= PRIOR_TTL_S
        if not self.patient_detected:
            self.status = 'NO_PATIENT'
        elif alive and self.optical['segment_s'] >= self.warmup_s:
            self.status = 'STABLE'       # brief gate failures (< MAX_GAP_S) are bridged
        elif recent_ok:
            self.status = 'REACQUIRING'  # a new segment is building; the last value is held for display
        else:
            self.status = 'CALIBRATING' if self.full_face_visible else 'ALIGNING'
        return annotated, record

    def _draw_face_overlay(self, img, is_full, code, face, roi, w, h):
        sfx, sfy, sfw, sfh = face
        if is_full:
            green = (0, 230, 100)
            cv2.rectangle(img, (sfx, sfy), (sfx + sfw, sfy + sfh), (0, 220, 100), 1)
            c = max(5, min(12, sfw // 5, sfh // 5))
            for (x0, y0, dx, dy) in [(sfx, sfy, 1, 1), (sfx + sfw, sfy, -1, 1),
                                     (sfx, sfy + sfh, 1, -1), (sfx + sfw, sfy + sfh, -1, -1)]:
                cv2.line(img, (x0, y0), (x0 + dx * c, y0), green, 2)
                cv2.line(img, (x0, y0), (x0, y0 + dy * c), green, 2)
            for (rx, ry, rw, rh) in roi:
                cv2.rectangle(img, (rx, ry), (rx + rw, ry + rh), (0, 230, 230), 1)
        else:
            amber = (0, 140, 255)
            cv2.rectangle(img, (sfx, sfy), (sfx + sfw, sfy + sfh), amber, 1)
            mid_y = max(10, min(h - 10, sfy + sfh // 2))
            mid_x = max(10, min(w - 10, sfx + sfw // 2))
            arrows = {
                'CLIPPED_LEFT': ((4, mid_y), (26, mid_y)),
                'CLIPPED_RIGHT': ((w - 4, mid_y), (w - 26, mid_y)),
                'CLIPPED_TOP': ((mid_x, 4), (mid_x, 26)),
                'CLIPPED_BOTTOM': ((mid_x, h - 4), (mid_x, h - 26)),
            }
            if code in arrows:
                cv2.arrowedLine(img, arrows[code][0], arrows[code][1], amber, 2, tipLength=0.4)

    def _update_best_moment(self, frame, sharpness, rect, now):
        window_expired = now - self.best_moment_window_start > self.best_moment_window_duration
        if window_expired or self.best_moment['frame'] is None or sharpness > self.best_moment['sharpness']:
            if window_expired:
                self.best_moment_window_start = now
            self.best_moment = {'frame': frame.copy(), 'sharpness': sharpness, 'face_rect': rect,
                                'timestamp': now, 'frame_index': self.frame_count, 'full_face_visible': True}

    # ------------------------------------------------------------ telemetry
    def telemetry(self):
        o = self.optical
        n_disp = int(10 * self.fs)          # last 10 s of each waveform

        def tail(x):
            x = np.asarray(x)
            return [round(float(v), 4) for v in x[-n_disp:]]

        disp = (o['freqs'] >= 0.5) & (o['freqs'] <= 3.5) if len(o['freqs']) else np.array([], bool)
        psd_db = 10 * np.log10(np.maximum(o['psd'][disp], 1e-12)) if np.any(disp) else np.array([])
        if len(psd_db):
            psd_db = psd_db - np.max(psd_db)
        seg = o['segment_s'] if self.segment_alive else 0.0
        progress = int(min(100, 100 * seg / self.warmup_s)) if self.patient_detected else 0
        return {
            'patient_detected': self.patient_detected,
            'full_face_visible': self.full_face_visible,
            'face_alignment_status': self.face_alignment_status,
            'face_guidance': self.face_guidance,
            'status': self.status,
            'calibrating': self.status in ('CALIBRATING', 'ALIGNING', 'REACQUIRING'),
            'calibration_progress': progress,
            'calibration_remaining_sec': max(0, int(round(self.warmup_s - seg))),
            'optical_hr': None if o['hr'] is None else round(o['hr'], 1),
            'optical_hr_ok': bool(o['hr_ok']),
            'optical_tracked': bool(o['tracked']),
            'segment_coverage': round(o['coverage'], 3),
            'pulse_source': 'node raw pixels' if self.node_mode else 'JPEG frames',
            'optical_quality': round(o['quality'], 3),
            'cardiac_peak_freq': None if o['f0'] is None else round(o['f0'], 3),
            'cardiac_snr': None if o['snr'] is None or np.isnan(o['snr']) else round(o['snr'], 1),
            'optical_rr': None if o['rr'] is None else round(o['rr'], 1),
            'optical_rr_estimate': None if o.get('rr_estimate') is None else round(o['rr_estimate'], 1),
            'rr_quality': round(o.get('rr_quality', 0.0), 3),
            'spo2_ratio': None if o['spo2_ratio'] is None else round(o['spo2_ratio'], 4),
            'spo2_estimate': None if o['spo2'] is None else round(o['spo2'], 1),
            'segment_seconds': round(o['segment_s'], 1),
            'analysis_fs': self.fs,
            'psd_freqs': [round(float(f), 3) for f in o['freqs'][disp]] if np.any(disp) else [],
            'psd_power': [round(float(p), 1) for p in psd_db],
            'bvp_wave': tail(o['bvp']),
            'resp_wave': tail(o['resp']),
            'trend_wave': tail(o['trend']),
            'pulsatile_wave': tail(o['pulsatile']),
            'diff_wave': tail(o['diff']),
            'motion_ratio': None if o['motion_ratio'] is None else round(o['motion_ratio'], 2),
            # quality-control evidence behind hr_ok (shown on the dashboard)
            'snr_gate_db': dsp.MIN_SNR_HR_DB,
            'optical_method': o.get('method', 'chrom').upper(),
            'tracked_hr': None if self.tracked[0] is None else round(self.tracked[0], 1),
            'tracked_conf': round(float(self.tracked[1]), 3),
            'tracked_high_conf': dsp.TRACKER_HIGH_CONF,
            'ensemble_spectra': int(self.ensemble_n),
            'camera_rmssd': None if self.camera_rmssd is None else round(self.camera_rmssd, 1),
            'optical_hr_chrom': None if o.get('hr_chrom') is None else round(o['hr_chrom'], 1),
            'bg_rejected_bpm': list(o.get('bg_rejected', [])),
            'optical_hr_pos': None if o.get('hr_pos') is None else round(o['hr_pos'], 1),
            'optical_hr_green': None if o.get('hr_green') is None else round(o['hr_green'], 1),
            'optical_consensus': int(o.get('consensus', 0)),
            'artifact_frac': round(float(o.get('artifact_frac', 0.0)), 3),
            'still_trimmed_s': round(float(o.get('still_trimmed_s', 0.0)), 1),
            'rgb_norm': [[round(100 * float(v), 3) for v in col] for col in
                         np.asarray(o.get('rgb_norm', np.empty((0, 3))))[-int(20 * self.fs):].T]
            if len(o.get('rgb_norm', [])) else [[], [], []],          # % change, last 20 s
            'best_moment_sharpness': round(self.best_moment['sharpness'], 1),
            'best_moment_ready': self.best_moment['frame'] is not None and self.best_moment.get('full_face_visible', False),
        }

    # ------------------------------------------------------------ snapshot
    def analyze_diagnostic_snapshot(self, use_best_moment=True):
        """Exploratory colorimetric indices on the sharpest gated frame (paper Sec. VI).

        The thresholds are software settings that have not been validated against
        any clinical reference; outputs are research data, not diagnoses.
        """
        target_frame = target_rect = None
        target_sharpness = 0.0
        frame_index = None
        source = 'LIVE'

        if use_best_moment and self.best_moment['frame'] is not None and self.best_moment['face_rect'] is not None:
            if self.validate_full_face(self.best_moment['frame'], self.best_moment['face_rect'])[0]:
                target_frame = self.best_moment['frame'].copy()
                target_rect = [int(v) for v in self.best_moment['face_rect']]
                target_sharpness = self.best_moment['sharpness']
                frame_index = self.best_moment['frame_index']
                source = 'SHARPEST_IN_WINDOW'

        if target_frame is None and self.latest_raw_frame is not None:
            gray = cv2.cvtColor(self.latest_raw_frame, cv2.COLOR_BGR2GRAY)
            rect = self.last_face_rect
            if rect is None:
                faces = self.face_cascade.detectMultiScale(cv2.equalizeHist(gray), scaleFactor=1.08,
                                                           minNeighbors=3, minSize=(28, 28))
                rect = max(faces, key=lambda r: r[2] * r[3]) if len(faces) else None
            if rect is not None and self.validate_full_face(self.latest_raw_frame, rect)[0]:
                target_frame = self.latest_raw_frame.copy()
                target_rect = [int(v) for v in rect]
                target_sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
                frame_index = self.frame_count

        if target_frame is None:
            guidance = self.face_guidance if self.patient_detected else \
                "No patient detected in camera view. Please position subject in front of camera."
            return {
                'success': False,
                'error_code': 'FULL_FACE_REQUIRED',
                'error': f"Capture inhibited: full face must be visible. {guidance}",
                'guidance': guidance,
                'alignment_status': self.face_alignment_status if self.patient_detected else 'NO_SUBJECT',
                'full_face_visible': False,
            }

        frame = target_frame
        h, w = frame.shape[:2]
        fx, fy, fw, fh = target_rect
        boxes = {}
        for name, (x, y, bw, bh) in self.roi_boxes(fx, fy, fw, fh).items():
            x, y = max(0, x), max(0, y)
            boxes[name] = (x, y, max(4, min(w - x, bw)), max(4, min(h - y, bh)))

        def means(name):
            x, y, bw, bh = boxes[name]
            roi = frame[y:y + bh, x:x + bw]
            if roi.size == 0:
                return 100.0, 100.0, 100.0
            return float(np.mean(roi[:, :, 2])), float(np.mean(roi[:, :, 1])), float(np.mean(roi[:, :, 0]))

        r_fh, g_fh, _ = means('Forehead')
        r_lc, g_lc, b_lc = means('Left Cheek')
        r_rc, g_rc, b_rc = means('Right Cheek')
        r_lp, _, b_lp = means('Lips')
        r_sc, g_sc, b_sc = means('Sclera')

        ei = float(100.0 * (np.log10(max(1.0, r_fh)) - np.log10(max(1.0, g_fh))))
        pi = float((g_lc + b_lc + g_rc + b_rc) / (2.0 * (r_lc + r_rc) + 1e-5))
        yi = float(((r_sc + g_sc - 2.0 * b_sc) / (r_sc + g_sc + b_sc + 1e-5)) * 100.0)
        cr = float((b_lp + 1e-5) / (r_lp + 1e-5))
        hfi = float((abs(g_lc - g_rc) / (g_lc + g_rc + 1e-5)) * 100.0)

        def classify(v, normal, warn):
            """normal/warn are predicates; anything else is ALERT."""
            return 'NORMAL' if normal(v) else ('WARN' if warn(v) else 'ALERT')

        ei_s = classify(ei, lambda v: 8.0 <= v <= 23.0, lambda v: v > 23.0)
        pi_s = classify(pi, lambda v: v < 0.72, lambda v: v <= 0.84)
        yi_s = classify(yi, lambda v: v < 12.0, lambda v: v <= 18.0)
        cr_s = classify(cr, lambda v: v < 0.76, lambda v: v <= 0.86)
        hfi_s = classify(hfi, lambda v: v < 5.0, lambda v: v <= 10.0)
        clarity_s = 'NORMAL' if target_sharpness > 100.0 else 'WARN'

        findings = {
            'erythema': {'NORMAL': 'Within software range', 'WARN': 'Above range: increased redness',
                         'ALERT': 'Below range: reduced redness'}[ei_s],
            'pallor': {'NORMAL': 'Within software range', 'WARN': 'Borderline pale-color ratio',
                       'ALERT': 'Above range: pale-color ratio'}[pi_s],
            'yellowness': {'NORMAL': 'Within software range', 'WARN': 'Borderline yellowness',
                           'ALERT': 'Above range: yellowness in eye band'}[yi_s],
            'lip_ratio': {'NORMAL': 'Within software range', 'WARN': 'Borderline blue/red ratio',
                          'ALERT': 'Above range: blue/red ratio'}[cr_s],
            'symmetry': {'NORMAL': 'Within software range', 'WARN': 'Mild left-right difference',
                         'ALERT': 'Above range: left-right difference'}[hfi_s],
        }

        annotated = frame.copy()
        cv2.rectangle(annotated, (fx, fy), (fx + fw, fy + fh), (90, 160, 90), 1)
        labels = {'Forehead': ('FOREHEAD', (0, 215, 255)), 'Sclera': ('EYE BAND', (80, 230, 255)),
                  'Left Cheek': ('L. CHEEK', (50, 255, 140)), 'Right Cheek': ('R. CHEEK', (50, 255, 140)),
                  'Lips': ('LIPS', (255, 90, 190))}
        for name, (label, color) in labels.items():
            self._draw_labeled_roi(annotated, *boxes[name], label, color)

        face = frame[fy:fy + fh, fx:fx + fw].astype(np.float32)
        maps = {}
        if face.size > 0:
            def overlay(values, cmap):
                v = values - np.min(values)
                v = np.clip(v / (np.ptp(values) + 1e-5) * 255.0, 0, 255).astype(np.uint8)
                out = frame.copy()
                out[fy:fy + fh, fx:fx + fw] = cv2.addWeighted(frame[fy:fy + fh, fx:fx + fw], 0.45,
                                                              cv2.applyColorMap(v, cmap), 0.55, 0)
                return out
            maps['erythema_map'] = overlay(face[:, :, 2] - face[:, :, 1], cv2.COLORMAP_JET)
            lab_b = cv2.cvtColor(frame[fy:fy + fh, fx:fx + fw], cv2.COLOR_BGR2LAB)[:, :, 2].astype(np.float32)
            maps['jaundice_map'] = overlay(lab_b, cv2.COLORMAP_INFERNO)
            maps['cyanosis_map'] = overlay(face[:, :, 0] / (face[:, :, 2] + 1e-5), cv2.COLORMAP_COOL)
        else:
            maps = {k: frame.copy() for k in ('erythema_map', 'jaundice_map', 'cyanosis_map')}

        def to_b64(im):
            _, buf = cv2.imencode('.jpg', im, [cv2.IMWRITE_JPEG_QUALITY, 80])
            return 'data:image/jpeg;base64,' + base64.b64encode(buf).decode('utf-8')

        observations = [
            {'id': 'perfusion', 'name': 'Erythema index', 'metric': f'{ei:.2f}', 'status': ei_s, 'detail': findings['erythema']},
            {'id': 'pallor', 'name': 'Pallor index', 'metric': f'{pi:.3f}', 'status': pi_s, 'detail': findings['pallor']},
            {'id': 'icterus', 'name': 'Eye-band yellowness', 'metric': f'{yi:.2f}', 'status': yi_s, 'detail': findings['yellowness']},
            {'id': 'oxygenation', 'name': 'Lip blue/red ratio', 'metric': f'{cr:.3f}', 'status': cr_s, 'detail': findings['lip_ratio']},
            {'id': 'symmetry', 'name': 'Hemifacial asymmetry', 'metric': f'{hfi:.2f}%', 'status': hfi_s, 'detail': findings['symmetry']},
        ]
        statuses = [o['status'] for o in observations]
        flags = sum(1 for s in statuses if s != 'NORMAL')
        overall = 'NORMAL' if flags == 0 else ('ALERT' if 'ALERT' in statuses else 'WARN')

        caveat = ("These are exploratory, uncalibrated color indices; the ranges are software settings that "
                  "have not been validated against any clinical measurement. They depend on camera settings, "
                  "illumination and skin tone and must not be used for diagnosis.")
        if flags == 0:
            interpretation = "All five indices are within the software reference ranges."
        else:
            outside = "; ".join(f"{o['name'].lower()} ({o['detail'].lower()})" for o in observations if o['status'] != 'NORMAL')
            interpretation = f"{flags} of 5 indices outside the software reference ranges: {outside}."
        frame_label = f"FRAME #{frame_index:05d}" if frame_index is not None else "FRAME #-----"

        return {
            'success': True,
            'timestamp': time.time(),
            'frame_id': frame_label,
            'frame_source': source,
            'cardiac_phase': source,          # kept for UI compatibility; no cardiac timing is implied
            'sharpness': round(target_sharpness, 1),
            'full_face_verified': True,
            'meta_strip': {
                'frame_id': frame_label,
                'roi_status': 'FULL FACE VERIFIED (5 ZONES)',
                'motion': 'CLARITY: OK' if target_sharpness > 100.0 else 'CLARITY: LOW',
                'quality': f'LAPLACIAN VAR {target_sharpness:.0f}',
                'cardiac': 'SHARPEST IN 8 S' if source == 'SHARPEST_IN_WINDOW' else 'LIVE FRAME',
            },
            'images': {'raw': to_b64(frame), 'annotated_roi': to_b64(annotated),
                       **{k: to_b64(v) for k, v in maps.items()}},
            'biomarkers': [
                {'id': 'erythema', 'name': 'Erythema index (EI)', 'value': round(ei, 2), 'unit': 'EI',
                 'reference': '8.0 - 23.0', 'status': ei_s, 'finding': findings['erythema']},
                {'id': 'pallor', 'name': 'Pallor index (PI)', 'value': round(pi, 3), 'unit': '(G+B)/2R',
                 'reference': '< 0.720', 'status': pi_s, 'finding': findings['pallor']},
                {'id': 'bilirubin', 'name': 'Eye-band yellowness (YI)', 'value': round(yi, 2), 'unit': 'YI',
                 'reference': '< 12.0', 'status': yi_s, 'finding': findings['yellowness']},
                {'id': 'cyanosis', 'name': 'Lip blue/red ratio (CR)', 'value': round(cr, 3), 'unit': 'B/R',
                 'reference': '< 0.760', 'status': cr_s, 'finding': findings['lip_ratio']},
                {'id': 'symmetry', 'name': 'Hemifacial asymmetry (HFI)', 'value': round(hfi, 2), 'unit': '%',
                 'reference': '< 5.0%', 'status': hfi_s, 'finding': findings['symmetry']},
                {'id': 'sharpness', 'name': 'Frame clarity', 'value': round(target_sharpness, 1),
                 'unit': 'Laplacian var', 'reference': '> 100.0', 'status': clarity_s,
                 'finding': 'Adequate focus' if clarity_s == 'NORMAL' else 'Blur or motion; recapture'},
            ],
            'clinical_summary': f"{interpretation} {caveat}",
            'structured_triage': {
                'overall_status': overall,
                'flags_count': flags,
                'observations': observations,
                'interpretation': interpretation,
                'recommendation': caveat,
            },
            'metrics_overview': {
                'clarity': round(target_sharpness, 1),
                'symmetry': round(hfi, 2),
                'perfusion': round(ei, 2),
                'perfusion_status': ei_s,
                'flags_count': flags,
                'total_count': 5,
            },
        }

    @staticmethod
    def _draw_labeled_roi(img, rx, ry, rw, rh, label, color):
        cv2.rectangle(img, (rx, ry), (rx + rw, ry + rh), color, 1)
        font, scale = cv2.FONT_HERSHEY_SIMPLEX, 0.24
        (tw, th), _ = cv2.getTextSize(label, font, scale, 1)
        ty = ry - 3 if ry - th - 4 >= 2 else ry + rh + th + 2
        tx = max(2, min(img.shape[1] - tw - 4, rx))
        cv2.rectangle(img, (tx - 2, ty - th - 2), (tx + tw + 2, ty + 2), (18, 18, 18), -1)
        cv2.putText(img, label, (tx, ty), font, scale, color, 1, cv2.LINE_AA)
