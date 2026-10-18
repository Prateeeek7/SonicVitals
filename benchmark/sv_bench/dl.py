"""Deep-learning baselines: pretrained rPPG-Toolbox models (PhysNet, TS-CAN, EfficientPhys).

Preprocessing reproduces the toolbox inference configs (configs/infer_configs/*_BASIC.yaml):
Haar-cascade face box on the first frame, enlarged 1.5x, every frame cropped to it and resized
to 72 x 72 (INTER_AREA); DiffNormalized / Standardized over the whole video; non-overlapping
chunks (180 frames; 128 for PhysNet). The models predict the first difference of the PPG, so
the output is integrated (cumsum) before HR estimation, as in the toolbox evaluation.
"""
import os
import sys
import time

import cv2
import numpy as np

from . import TOOLBOX_DIR

SPECS = {
    # name: (weights file pattern, input types, chunk length)
    'TS-CAN': ('{train}_TSCAN.pth', ('DiffNormalized', 'Standardized'), 180),
    'PhysNet': ('{train}_PhysNet_DiffNormalized.pth', ('DiffNormalized',), 128),
    'EfficientPhys': ('{train}_EfficientPhys.pth', ('Standardized',), 180),
}
FRAME_DEPTH = 10
SIZE = 72


def toolbox_face_box(rgb_frame, coef=1.5):
    """BaseLoader.face_detection(backend='HC', use_larger_box=True, larger_box_coef=1.5)."""
    path = os.path.join(TOOLBOX_DIR, 'dataset', 'haarcascade_frontalface_default.xml')
    if not os.path.isfile(path):          # same file ships with OpenCV
        path = os.path.join(cv2.data.haarcascades, 'haarcascade_frontalface_default.xml')
    det = cv2.CascadeClassifier(path)
    faces = det.detectMultiScale(rgb_frame[:, :, :3].astype(np.uint8))
    if len(faces) < 1:
        box = [0, 0, rgb_frame.shape[0], rgb_frame.shape[1]]
    else:
        box = list(faces[int(np.argmax(faces[:, 2]))])
    box = [float(v) for v in box]
    box[0] = max(0, box[0] - (coef - 1.0) / 2 * box[2])
    box[1] = max(0, box[1] - (coef - 1.0) / 2 * box[3])
    box[2], box[3] = coef * box[2], coef * box[3]
    return [int(v) for v in box]


def crop_resize(rgb_frame, box):
    x, y, w, h = box
    f = rgb_frame[max(y, 0):min(y + h, rgb_frame.shape[0]), max(x, 0):min(x + w, rgb_frame.shape[1])]
    return cv2.resize(f, (SIZE, SIZE), interpolation=cv2.INTER_AREA)


def diff_normalize(data):
    data = data.astype(np.float32)
    d = (data[1:] - data[:-1]) / (data[1:] + data[:-1] + 1e-7)
    d = d / np.std(d)
    d = np.concatenate([d, np.zeros_like(d[:1])], axis=0)
    d[np.isnan(d)] = 0
    return d


def standardize(data):
    data = data.astype(np.float32)
    data = (data - np.mean(data)) / np.std(data)
    data[np.isnan(data)] = 0
    return data


def _import_toolbox():
    if TOOLBOX_DIR not in sys.path:
        sys.path.insert(0, TOOLBOX_DIR)


def load_model(name, weights_path, device):
    import torch
    _import_toolbox()
    if name == 'TS-CAN':
        from neural_methods.model.TS_CAN import TSCAN
        model = TSCAN(frame_depth=FRAME_DEPTH, img_size=SIZE)
    elif name == 'EfficientPhys':
        from neural_methods.model.EfficientPhys import EfficientPhys
        model = EfficientPhys(frame_depth=FRAME_DEPTH, img_size=SIZE)
    elif name == 'PhysNet':
        from neural_methods.model.PhysNet import PhysNet_padding_Encoder_Decoder_MAX
        model = PhysNet_padding_Encoder_Decoder_MAX(frames=SPECS['PhysNet'][2])
    else:
        raise ValueError(name)
    if name == 'PhysNet' and str(device).startswith('mps'):
        device = 'cpu'                   # max_pool3d is not implemented on Apple MPS
    sd = torch.load(weights_path, map_location='cpu')
    sd = {k[7:] if k.startswith('module.') else k: v for k, v in sd.items()}   # saved via DataParallel
    model.load_state_dict(sd)
    return model.to(device).eval()


def predict(name, model, crops, device):
    """crops: T x 72 x 72 x 3 uint8 (RGB). Returns (predicted first-difference PPG of length
    n_chunks * chunk, seconds spent in the model forward passes)."""
    import torch
    types, chunk = SPECS[name][1], SPECS[name][2]
    data = np.concatenate([diff_normalize(crops) if t == 'DiffNormalized' else standardize(crops) for t in types],
                          axis=-1)                                     # T x H x W x C
    n_chunks = len(data) // chunk
    out, t_model = [], 0.0
    with torch.no_grad():
        for i in range(n_chunks):
            clip = torch.from_numpy(data[i * chunk:(i + 1) * chunk]).permute(0, 3, 1, 2).float()   # D x C x H x W
            if name == 'PhysNet':
                x = clip.permute(1, 0, 2, 3).unsqueeze(0).contiguous().to(device)    # 1 x C x D x H x W
                t0 = time.perf_counter()
                y = model(x)[0]
                _sync(device)
                t_model += time.perf_counter() - t0
                out.append(y.reshape(-1).cpu().numpy())
            else:
                n = (len(clip) // FRAME_DEPTH) * FRAME_DEPTH
                x = clip[:n]
                if name == 'EfficientPhys':                             # model differentiates internally
                    x = torch.cat([x, x[-1:]], 0)
                x = x.contiguous().to(device)
                t0 = time.perf_counter()
                y = model(x)
                _sync(device)
                t_model += time.perf_counter() - t0
                y = y.reshape(-1).cpu().numpy()
                out.append(np.concatenate([y, np.full(chunk - len(y), y[-1] if len(y) else 0.0)]))
    pred = np.concatenate(out) if out else np.zeros(0)
    return pred, t_model


def _sync(device):
    import torch
    if str(device).startswith('cuda'):
        torch.cuda.synchronize()
    elif str(device).startswith('mps'):
        torch.mps.synchronize()


def weights_file(name, train):
    return os.path.join(TOOLBOX_DIR, 'final_model_release', SPECS[name][0].format(train=train))
