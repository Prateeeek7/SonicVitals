"""Small synthetic dataset in the UBFC-rPPG DATASET_2 layout, for testing the benchmark code.

A face image is animated with a known pulse on its skin pixels (blood-volume colour change, green
strongest), slow illumination drift, sensor noise and small head translations; the pulse waveform
is written as the ground truth. It only checks that the pipeline runs and recovers a clean pulse.
It is NOT evidence of accuracy on real faces: use the real datasets for that.

    python benchmark/make_synthetic.py --out /tmp/sv_synth --subjects 3 --seconds 40
"""
import argparse
import os

import cv2
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FACE = os.path.join(REPO, 'Report', 'images', 'anatomical_dashboard.png')


def face_image():
    img = cv2.imread(FACE)
    h, w = img.shape[:2]
    img = img[int(0.30 * h):int(0.82 * h), 0:int(0.40 * w)]
    return cv2.resize(img, (640, 480), interpolation=cv2.INTER_CUBIC)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--subjects', type=int, default=3)
    ap.add_argument('--seconds', type=float, default=40.0)
    ap.add_argument('--fps', type=float, default=30.0)
    args = ap.parse_args()
    rng = np.random.default_rng(1)
    base = face_image().astype(np.float32)
    ycc = cv2.cvtColor(base.astype(np.uint8), cv2.COLOR_BGR2YCrCb)
    skin = ((ycc[..., 1] > 135) & (ycc[..., 1] < 175) & (ycc[..., 2] > 80) & (ycc[..., 2] < 125)).astype(np.float32)
    skin = cv2.GaussianBlur(skin, (15, 15), 0)[..., None]
    n = int(args.seconds * args.fps)
    for s in range(1, args.subjects + 1):
        hr = rng.uniform(58, 105)
        t = np.arange(n) / args.fps
        inst = hr / 60 * (1 + 0.04 * np.sin(2 * np.pi * 0.25 * t))          # respiratory sinus arrhythmia
        phase = 2 * np.pi * np.cumsum(inst) / args.fps
        ppg = np.sin(phase) + 0.35 * np.sin(2 * phase - 0.8)                   # dicrotic shape
        d = os.path.join(args.out, f'subject{s}')
        os.makedirs(d, exist_ok=True)
        vw = cv2.VideoWriter(os.path.join(d, 'vid.avi'), cv2.VideoWriter_fourcc(*'FFV1'), args.fps, (640, 480))
        for i in range(n):
            gain = 1 - 0.006 * ppg[i] * np.array([0.53, 0.77, 0.33], np.float32)   # B, G, R
            illum = 1 + 0.01 * np.sin(2 * np.pi * 0.05 * t[i])
            frame = base * (1 - skin + skin * gain) * illum
            dx, dy = 2 * np.sin(2 * np.pi * 0.1 * t[i]), 1.5 * np.sin(2 * np.pi * 0.07 * t[i])
            frame = cv2.warpAffine(frame, np.float32([[1, 0, dx], [0, 1, dy]]), (640, 480), borderMode=cv2.BORDER_REFLECT)
            frame += rng.normal(0, 2.0, frame.shape).astype(np.float32)
            vw.write(np.clip(frame, 0, 255).astype(np.uint8))
        vw.release()
        with open(os.path.join(d, 'ground_truth.txt'), 'w') as f:
            f.write(' '.join(f'{v:.6e}' for v in ppg) + '\n')
            f.write(' '.join(f'{hr:.6e}' for _ in ppg) + '\n')
            f.write(' '.join(f'{v:.6e}' for v in t) + '\n')
        print(f'subject{s}: {hr:.1f} BPM, {n} frames')


if __name__ == '__main__':
    main()
