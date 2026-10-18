"""Emulate a SonicVitals edge node (firmware protocol v2) on a virtual serial port.

Use it to test the host server and browser UI without hardware, or to run a
clearly labelled demonstration. The node announces itself as a simulator
(HELLO name "SonicVitals-SIM", sim=1); the server then labels the source
SIMULATOR and the dashboard shows a "SIMULATED DATA" banner. The simulated
physiology is synthetic and must never be used or presented as measured data.

    python3 tools/node_simulator.py --image Report/images/anatomical_dashboard.png --hr 72
    # then, in another terminal, start the server with the printed port:
    SONICVITALS_LINK=serial SONICVITALS_PORT=/dev/ttys00X SONICVITALS_BAUD=115200 SONICVITALS_WEBCAM=0 python3 backend/usb_streamer.py
    # (a virtual port ignores the baud rate, but macOS rejects non-standard rates on it)
    # or simply: ./tools/demo_simulated.sh
"""
import argparse
import base64
import os
import pty
import sys
import threading
import time
import tty

import cv2
import numpy as np


def face_crop(path):
    img = cv2.imread(path)
    if img is None:
        sys.exit(f'cannot read {path}')
    h, w = img.shape[:2]
    if 'dashboard' in os.path.basename(path):          # crop the camera panel from a UI screenshot
        img = img[int(0.30 * h):int(0.82 * h), 0:int(0.40 * w)]
    return cv2.resize(img, (240, 160))


class Heart:
    """Synthetic beat schedule: mean HR with respiratory sinus arrhythmia and small jitter."""

    def __init__(self, hr, rr, rng):
        self.hr, self.rr, self.rng = hr, rr, rng
        self.beats = [0.0]

    def extend(self, until):
        while self.beats[-1] < until + 2.0:
            t = self.beats[-1]
            rsa = 0.04 * np.sin(2 * np.pi * self.rr / 60.0 * t)          # +-4 % with breathing
            ibi = 60.0 / self.hr * (1 + rsa) + self.rng.normal(0, 0.012)
            self.beats.append(t + ibi)

    def phase(self, t):
        """Cardiac phase in [0, 1) at time t."""
        self.extend(t)
        b = np.asarray(self.beats)
        k = np.searchsorted(b, t, side='right') - 1
        return (t - b[k]) / (b[k + 1] - b[k])

    def pcg(self, t0, n, fs):
        """S1/S2 bursts (S1 louder) at the scheduled beats plus noise, as int16."""
        t = t0 + np.arange(n) / fs
        self.extend(t[-1])
        x = np.zeros(n)
        for b0, b1 in zip(self.beats[:-1], self.beats[1:]):
            if b0 > t[-1] or b1 < t[0] - 1.0:
                continue
            for off, amp, f in [(0.0, 1.0, 60.0), (0.3 * (b1 - b0), 0.6, 90.0)]:
                m = (t >= b0 + off) & (t < b0 + off + 0.08)
                u = t[m] - b0 - off
                x[m] += amp * np.sin(2 * np.pi * f * u) * np.sin(np.pi * u / 0.08)
        x = 3000 * x + 150 * self.rng.standard_normal(n)
        return np.clip(x, -32768, 32767).astype('<i2')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--image', default='Report/images/anatomical_dashboard.png')
    ap.add_argument('--video', help='replay a video file instead of a still image')
    ap.add_argument('--hr', type=float, default=72.0, help='simulated heart rate (BPM)')
    ap.add_argument('--rr', type=float, default=15.0, help='simulated breathing rate (breaths/min)')
    ap.add_argument('--fps', type=float, default=10.0)
    ap.add_argument('--no-audio', action='store_true')
    args = ap.parse_args()

    master, slave = pty.openpty()
    tty.setraw(slave)
    print(f'Simulated node on {os.ttyname(slave)}', flush=True)

    rng = np.random.default_rng(0)
    heart = Heart(args.hr, args.rr, rng)
    base = None if args.video else face_crop(args.image).astype(float)
    cap = cv2.VideoCapture(args.video) if args.video else None
    t0 = time.time()
    frame_seq = audio_seq = 0
    samples_sent = 0
    fs = 4000
    last_stat = t0
    data = b''
    hello = f'<<HELLO:SonicVitals-SIM,2,SIM,{0 if args.no_audio else 1},sim=1,fs={fs}>>\n'

    rois = {'boxes': [], 't': 0.0}

    def reader():
        buf = b''
        while True:
            try:
                buf += os.read(master, 256)
            except OSError:
                return
            while b'\n' in buf:
                line, buf = buf.split(b'\n', 1)
                if line.startswith(b'<<VITALS:'):
                    print('OLED <-', line.decode(errors='ignore'), flush=True)
                elif line.startswith(b'<<ROI:') and line.endswith(b'>>'):
                    body = line[6:-2].decode(errors='ignore')
                    boxes = []
                    if body != 'none':
                        for b in body.split(';'):
                            v = [int(x) for x in b.split(',') if x.strip().lstrip('-').isdigit()]
                            if len(v) == 4 and v[2] > 0 and v[3] > 0:
                                boxes.append(v)
                    rois.update(boxes=boxes, t=time.time())

    threading.Thread(target=reader, daemon=True).start()

    def write(s):
        os.write(master, s.encode() if isinstance(s, str) else s)

    write(hello)
    next_frame = t0
    while True:
        now = time.time()
        t = now - t0
        t_us = int(t * 1e6)

        if now >= next_frame:
            next_frame += 1.0 / args.fps
            if cap is not None:
                ok, img = cap.read()
                if not ok:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                img = cv2.resize(img, (240, 160))
            else:
                ph = heart.phase(t)
                pulse = np.exp(-((ph - 0.15) / 0.08) ** 2) + 0.35 * np.exp(-((ph - 0.45) / 0.1) ** 2)
                breath = np.sin(2 * np.pi * args.rr / 60.0 * t)
                # Blood-volume pulse: absorption rises in all channels, most in green (B, G, R order);
                # breathing modulates the illumination slightly.
                gain_bgr = (1.0 - 0.01 * pulse * np.array([0.53, 0.77, 0.33])) * (1.0 + 0.006 * breath)
                img = np.clip(base * gain_bgr + rng.normal(0, 0.6, base.shape), 0, 255).astype(np.uint8)
            # Like the firmware: skin sums from the uncompressed frame inside the host's boxes.
            if rois['boxes'] and time.time() - rois['t'] < 3.0:
                n = sr = sg = sb = 0
                for x, y, w, h in rois['boxes']:
                    patch = img[max(0, y):y + h, max(0, x):x + w].reshape(-1, 3).astype(np.int64)
                    n += len(patch)
                    sb, sg, sr = sb + patch[:, 0].sum(), sg + patch[:, 1].sum(), sr + patch[:, 2].sum()
                if n:
                    write(f'<<RGB:{frame_seq},{t_us},{n},{sr},{sg},{sb}>>\n')
            if frame_seq % 2 == 0:                       # video at half the capture rate, as on the node
                ok, jpg = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 85])
                data = jpg.tobytes()
                write(f'<<FRAME_START:{frame_seq},{t_us},{len(data)}>>\n')
                write(base64.b64encode(data) + b'\n<<FRAME_END>>\n')
            frame_seq += 1

        if not args.no_audio:
            due = int(t * fs)
            while samples_sent + 256 <= due:
                pcm = heart.pcg(samples_sent / fs, 256, fs)
                bt = int(samples_sent / fs * 1e6)
                write(f'<<AUDIO:{audio_seq},{bt},256,'.encode() + base64.b64encode(pcm.tobytes()) + b'>>\n')
                audio_seq += 1
                samples_sent += 256

        if now - last_stat >= 1.0:
            last_stat = now
            write(f'<<STAT:{int(args.fps * 10)},{frame_seq},{audio_seq},0,{0 if args.no_audio else 1},1,'
                  f'{len(data)},1,1,1,0>>\n')
            write(hello)
        time.sleep(0.004)


if __name__ == '__main__':
    main()
