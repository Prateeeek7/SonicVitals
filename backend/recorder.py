"""Session recorder: writes raw, timestamped data to disk so every reported
number can be recomputed offline (analysis/evaluate.py).

Layout of data/sessions/<session_id>/:
  meta.json        participant, condition, notes, start/stop host time, source
  frames.csv       host_time, device_t, seq, source, jpeg_bytes, face_found, gated, R, G, B
  audio.wav        mono int16 PCM at the node's audio rate (meta.json audio_fs), gaps filled with zeros
  audio_blocks.csv host_time, seq, device_t_us, sample_index
  estimates.csv    one row per 2 s display update (optical, acoustic, fused, displayed)
"""
import csv
import json
import os
import re
import threading
import time
import wave

ESTIMATE_FIELDS = ['host_time', 'device_t', 'status', 'source',
                   'hr_optical', 'hr_ok', 'tracked', 'coverage', 'q_optical', 'snr_db', 'rr_optical',
                   'hr_acoustic', 'rho_acoustic', 'rmssd_ms',
                   'hr_fused', 'fusion_source', 'w_o', 'w_a', 'disagreement',
                   'spo2_ratio', 'spo2_estimate',
                   'hr_display', 'rr_display', 'hr_card', 'hr_card_state', 'demo_mode']


class SessionRecorder:
    def __init__(self, root):
        self.root = root
        self._lock = threading.Lock()
        self.active = False
        self.session_id = None
        self.dir = None
        self._files = {}

    def start(self, participant='', condition='', notes='', video_source='', audio_fs=16000):
        with self._lock:
            if self.active:
                self._close_locked()
            stamp = time.strftime('%Y%m%d_%H%M%S')
            safe = re.sub(r'[^A-Za-z0-9_-]', '', participant)[:32] or 'anon'
            self.session_id = f'{stamp}_{safe}'
            self.dir = os.path.join(self.root, self.session_id)
            os.makedirs(self.dir, exist_ok=True)
            self.meta = {'session_id': self.session_id, 'participant': participant,
                         'condition': condition, 'notes': notes, 'video_source': video_source,
                         'start_host_time': time.time(), 'stop_host_time': None,
                         'protocol': 'SonicVitals v2', 'audio_fs': int(audio_fs),
                         'pulse_roi': 'forehead+cheeks+nose'}
            self._write_meta()

            f = open(os.path.join(self.dir, 'frames.csv'), 'w', newline='')
            self._files['frames'] = (f, csv.writer(f))
            self._files['frames'][1].writerow(['host_time', 'device_t', 'seq', 'source', 'jpeg_bytes', 'face_found', 'gated', 'R', 'G', 'B'])

            f = open(os.path.join(self.dir, 'audio_blocks.csv'), 'w', newline='')
            f2 = open(os.path.join(self.dir, 'node_rgb.csv'), 'w', newline='')
            self._files['node_rgb'] = (f2, csv.writer(f2))
            self._files['node_rgb'][1].writerow(['host_time', 'device_t', 'seq', 'n_pixels', 'R', 'G', 'B', 'used',
                                                 'n_clipped', 'n_dark', 'exposure'])
            self._files['audio_blocks'] = (f, csv.writer(f))
            self._files['audio_blocks'][1].writerow(['host_time', 'seq', 'device_t_us', 'sample_index'])

            f = open(os.path.join(self.dir, 'estimates.csv'), 'w', newline='')
            self._files['estimates'] = (f, csv.DictWriter(f, fieldnames=ESTIMATE_FIELDS))
            self._files['estimates'][1].writeheader()

            self._wav = wave.open(os.path.join(self.dir, 'audio.wav'), 'wb')
            self._wav.setnchannels(1)
            self._wav.setsampwidth(2)
            self._wav.setframerate(int(audio_fs))
            self._samples_written = 0
            self._next_audio_seq = None
            self.active = True
            return self.session_id

    def stop(self):
        with self._lock:
            sid = self.session_id
            if self.active:
                self._close_locked()
            return sid

    def _close_locked(self):
        self.meta['stop_host_time'] = time.time()
        self.meta['audio_samples'] = self._samples_written
        self._write_meta()
        for f, _ in self._files.values():
            f.close()
        self._files = {}
        self._wav.close()
        self.active = False

    def _write_meta(self):
        with open(os.path.join(self.dir, 'meta.json'), 'w') as f:
            json.dump(self.meta, f, indent=2)

    # ------------------------------------------------------------ writers
    def log_frame(self, device_t, seq, source, record, jpeg_bytes=None):
        if not self.active:
            return
        rgb = record['rgb'] or ('', '', '')
        with self._lock:
            if self.active:
                self._files['frames'][1].writerow([f'{time.time():.4f}', '' if device_t is None else f'{device_t:.6f}',
                                                   '' if seq is None else seq, source,
                                                   '' if jpeg_bytes is None else jpeg_bytes, int(record['face_found']),
                                                   int(record['gated']), *[f'{v:.4f}' if v != '' else '' for v in rgb]])

    def log_node_rgb(self, device_t, seq, n, rgb, used, nclip=0, ndark=0, exposure=None):
        if not self.active:
            return
        with self._lock:
            if self.active:
                vals = [f'{v:.4f}' for v in rgb] if rgb is not None else ['', '', '']
                self._files['node_rgb'][1].writerow([f'{time.time():.4f}', f'{device_t:.6f}', seq, n,
                                                     *vals, int(used), nclip, ndark,
                                                     '' if exposure is None else exposure])

    def log_audio(self, seq, t_us, pcm):
        if not self.active:
            return
        with self._lock:
            if not self.active:
                return
            if self._next_audio_seq is not None and seq > self._next_audio_seq:
                gap = (seq - self._next_audio_seq) * len(pcm)
                self._wav.writeframes(b'\x00\x00' * gap)
                self._samples_written += gap
            self._files['audio_blocks'][1].writerow([f'{time.time():.4f}', seq, t_us, self._samples_written])
            self._wav.writeframes(pcm.astype('<i2').tobytes())
            self._samples_written += len(pcm)
            self._next_audio_seq = seq + 1

    def log_estimate(self, row):
        if not self.active:
            return
        with self._lock:
            if self.active:
                self._files['estimates'][1].writerow({k: row.get(k, '') for k in ESTIMATE_FIELDS})
                self._files['estimates'][0].flush()
