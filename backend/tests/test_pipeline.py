"""Tests for the SonicVitals host pipeline. Run from the repo root:

    python3 -m pytest backend/tests -q
"""
import base64
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
REPO = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

import vitals_dsp as dsp                     # noqa: E402
from acoustic_engine import AcousticEngine   # noqa: E402
from protocol import StreamParser            # noqa: E402

RNG = np.random.default_rng(42)
FACE_IMAGE = os.path.join(REPO, 'Report', 'images', 'anatomical_dashboard.png')


# ---------------------------------------------------------------- synthetic data
def synthetic_rgb(hr_bpm=78.0, rr_bpm=15.0, duration=30.0, fps=(6.0, 11.0)):
    """Irregularly sampled forehead RGB with a pulse and an illumination-borne breathing component."""
    dt = RNG.uniform(1 / fps[1], 1 / fps[0], int(duration * fps[1]) + 10)
    t = np.cumsum(dt)
    t = t[t < duration]
    pulse = 0.004 * np.sin(2 * np.pi * hr_bpm / 60 * t)
    illum = 1 + 0.01 * np.sin(2 * np.pi * rr_bpm / 60 * t) + 0.002 * RNG.standard_normal(len(t))
    rgb = np.outer(illum, [180.0, 120.0, 100.0]) * (1 + np.outer(pulse, [0.33, 0.77, 0.53]))
    # Per-frame noise of the ROI *mean* (about 1000 pixels at HQVGA), in 8-bit levels.
    return t, rgb + 0.1 * RNG.standard_normal(rgb.shape)


def synthetic_pcg(ibis, fs=16000, noise=200.0, t_start=0.3):
    """S1/S2 tone bursts at the given inter-beat intervals; returns int16 audio and S1 times."""
    beats = t_start + np.concatenate([[0.0], np.cumsum(ibis)])
    n = np.arange(int((beats[-1] + 1.0) * fs)) / fs
    x = np.zeros_like(n)
    for b in beats:
        for off, amp, f in [(0.0, 1.0, 60.0), (0.30, 0.6, 90.0)]:
            m = (n >= b + off) & (n < b + off + 0.08)
            x[m] += amp * np.sin(2 * np.pi * f * (n[m] - b - off)) * np.hanning(m.sum())
    x = 3000 * x + noise * RNG.standard_normal(len(x))
    return np.clip(x, -32768, 32767).astype(np.int16), beats


# ---------------------------------------------------------------- optical
def test_resample_uses_last_contiguous_segment():
    t = np.array([0.0, 0.1, 0.2, 3.5, 3.6, 3.7, 3.8])       # 3.3 s dropout > MAX_GAP_S: restart
    tu, xu = dsp.resample_uniform(t, t * 2, fs=10)
    assert tu[0] == pytest.approx(3.5)
    assert np.allclose(xu, tu * 2)


def test_short_dropout_is_bridged_and_counted():
    t = np.array([0.0, 0.1, 0.2, 1.5, 1.6, 1.7, 1.8])       # 1.3 s dropout <= MAX_GAP_S: bridged
    tu, _ = dsp.resample_uniform(t, t * 2, fs=10)
    assert tu[0] == pytest.approx(0.0)
    assert dsp.segment_coverage(t) == pytest.approx(1 - (1.3 - 0.25) / 1.8)


def test_hr_gate_rejects_noise_only_input():
    """MIN_SNR_HR_DB accepts noise-only 10-30 s segments rarely (target <= 5 %)."""
    rng = np.random.default_rng(7)
    accepted = 0
    trials = 200
    for i in range(trials):
        n = int(rng.choice([10, 20, 30]) * 8) + 2
        t = np.arange(n) / 8.0
        out = dsp.estimate_optical(t, 150 + rng.standard_normal((n, 3)))
        accepted += out['hr_ok']
    assert accepted / trials <= 0.06


def test_hr_gate_accepts_clean_pulse():
    t, rgb = synthetic_rgb(hr_bpm=72.0)
    out = dsp.estimate_optical(t, rgb)
    assert out['hr_ok'] and out['hr'] == pytest.approx(72.0, abs=2.0)


def test_peak_tracking_prefers_peak_near_prior():
    freqs = np.linspace(0, 7.5, 2049)
    psd = (np.exp(-0.5 * ((freqs - 1.2) / 0.03) ** 2)          # 72 beats/min
           + 0.8 * np.exp(-0.5 * ((freqs - 0.8) / 0.03) ** 2))  # 48 beats/min, 80 % of the global peak
    f, tracked = dsp.tracked_peak(freqs, psd, dsp.CARDIAC_BAND, prior_hz=0.82)
    assert tracked and f == pytest.approx(0.8, abs=0.01)
    f, tracked = dsp.tracked_peak(freqs, psd, dsp.CARDIAC_BAND, prior_hz=None)
    assert not tracked and f == pytest.approx(1.2, abs=0.01)
    psd_weak = psd.copy()
    psd_weak[np.abs(freqs - 0.8) < 0.15] *= 0.3                 # local peak < 50 % of global: no tracking
    f, tracked = dsp.tracked_peak(freqs, psd_weak, dsp.CARDIAC_BAND, prior_hz=0.82)
    assert not tracked and f == pytest.approx(1.2, abs=0.01)


@pytest.mark.parametrize('hr', [52.0, 78.0, 128.0])
def test_optical_hr_irregular_frames(hr):
    t, rgb = synthetic_rgb(hr_bpm=hr)
    out = dsp.estimate_optical(t, rgb)
    assert out['hr'] == pytest.approx(hr, abs=2.0)
    assert 0 < out['quality'] <= 1


def test_optical_rr():
    t, rgb = synthetic_rgb(rr_bpm=15.0)
    assert dsp.estimate_optical(t, rgb)['rr'] == pytest.approx(15.0, abs=1.0)


def test_rr_not_reported_without_breathing():
    t, rgb = synthetic_rgb(rr_bpm=15.0)
    flat = rgb / (1 + 0.01 * np.sin(2 * np.pi * 0.25 * t))[:, None]     # remove the breathing component
    out = dsp.estimate_optical(t, flat)
    assert out['rr'] is None and out['hr'] is not None


def test_green_only_method_runs():
    t, rgb = synthetic_rgb(hr_bpm=72.0)
    assert dsp.estimate_optical(t, rgb, method='green')['hr'] == pytest.approx(72.0, abs=3.0)


def test_short_segment_gives_no_estimate():
    t, rgb = synthetic_rgb(duration=6.0)
    out = dsp.estimate_optical(t, rgb)
    assert out['hr'] is None and out['rr'] is None


def test_spo2_only_with_calibration():
    t, rgb = synthetic_rgb()
    assert dsp.estimate_optical(t, rgb)['spo2'] is None
    cal = dsp.estimate_optical(t, rgb, spo2_calibration={'A': 100.0, 'B': 2.0})
    assert cal['spo2'] == pytest.approx(100.0 - 2.0 * cal['spo2_ratio'])


def test_parabolic_peak_refines():
    y = np.array([0.0, 1.0, 3.0, 2.0, 0.0])
    assert 2.0 < dsp.parabolic_peak(y, 2) < 2.5


def test_parabolic_peak_stays_within_half_bin():
    # flat-topped or edge peaks once moved the estimate far outside the search band
    for y in ([1.0, 1.0, 1.0], [0.2, 1.0, 1.0], [1.0, 1.0, 0.999999], [0.5, 1.0, 2.0]):
        assert abs(dsp.parabolic_peak(np.array(y), 1) - 1) <= 0.5


# ---------------------------------------------------------------- acoustic
def test_acoustic_hr_and_beats():
    x, beats = synthetic_pcg(np.full(12, 60 / 72))
    out = dsp.estimate_acoustic(x, t0=100.0)
    assert out['hr'] == pytest.approx(72.0, abs=1.5)
    assert out['rho'] > 0.5
    detected = out['beats'] - 100.0
    s1_centres = beats[1:-1] + 0.04          # fiducial = envelope peak = centre of the 80 ms S1 burst
    errs = [np.min(np.abs(detected - c)) for c in s1_centres]
    assert np.max(errs) < 0.015              # every S1 found within 15 ms (not S2, 300 ms later)


def test_rmssd_known_value():
    ibis = np.tile([0.80, 0.86], 20)        # successive differences of 60 ms
    beats = np.concatenate([[0.0], np.cumsum(ibis)])
    assert dsp.rmssd_ms(beats) == pytest.approx(60.0, abs=0.5)


def test_rmssd_needs_enough_beats():
    assert dsp.rmssd_ms(np.arange(0, 5, 0.8)) is None


def test_acoustic_engine_blocks_and_gaps():
    eng = AcousticEngine()
    x, _ = synthetic_pcg(np.full(14, 60 / 66))
    blocks = [x[i:i + 256] for i in range(0, len(x) - 255, 256)]
    for seq, b in enumerate(blocks):
        if seq == 10:                       # simulate one lost block
            continue
        eng.add_block(seq, int(seq * 256 / 16000 * 1e6), b)
    assert eng.blocks_lost == 1
    res = eng.update(force=True)
    assert res['hr'] == pytest.approx(66.0, abs=2.0)
    payload = eng.display_payload()
    assert payload['wave'] and payload['spec']


def test_rmssd_from_overlapping_windows_on_regular_beats():
    eng = AcousticEngine()
    x, _ = synthetic_pcg(np.full(80, 0.8))            # 64 s of perfectly regular beats
    for seq, i in enumerate(range(0, len(x) - 255, 256)):
        eng.add_block(seq, int(i / 16000 * 1e6), x[i:i + 256])
        if seq % 62 == 61:                             # analysis once per second of audio
            eng.update(force=True)
    res = eng.update(force=True)
    assert res['rmssd'] is not None and res['rmssd'] < 3.0


def test_silent_microphone_reports_nothing():
    eng = AcousticEngine()
    for seq in range(700):
        eng.add_block(seq, seq * 16000, np.zeros(256, np.int16))
    assert eng.update(force=True)['hr'] is None


# ---------------------------------------------------------------- fusion
def test_fusion_rules():
    agree = dsp.fuse_hr(78.0, 0.5, 80.0, 0.5)
    assert agree['source'] == 'fused' and agree['hr'] == pytest.approx(79.0)
    conflict = dsp.fuse_hr(78.0, 0.3, 110.0, 0.6)
    assert conflict['source'] == 'acoustic' and conflict['disagreement']
    assert dsp.fuse_hr(None, 0.0, 70.0, 0.4)['source'] == 'acoustic'
    assert dsp.fuse_hr(70.0, 0.0, None, 0.0)['hr'] is None


# ---------------------------------------------------------------- protocol
def test_protocol_v2_roundtrip():
    p = StreamParser()
    jpeg = b'\xff\xd8' + bytes(300)
    b64 = base64.b64encode(jpeg).decode()
    assert p.feed_line(f'<<FRAME_START:7,123456,{len(jpeg)}>>') == []
    p.feed_line(b64)
    ev = p.feed_line('<<FRAME_END>>')[0]
    assert ev == ('frame', 7, 123456, jpeg)

    pcm = np.arange(256, dtype='<i2')
    ev = p.feed_line(f'<<AUDIO:3,999,256,{base64.b64encode(pcm.tobytes()).decode()}>>')[0]
    assert ev[0] == 'audio' and ev[1] == 3 and np.array_equal(ev[3], pcm)

    ev = p.feed_line('<<STAT:142,10,20,0,1,1,6100>>')[0]
    assert ev[1]['fps'] == pytest.approx(14.2) and ev[1]['jpeg_avg_bytes'] == 6100


def test_protocol_rejects_truncated_frame():
    p = StreamParser()
    jpeg = b'\xff\xd8' + bytes(300)
    p.feed_line(f'<<FRAME_START:1,0,{len(jpeg)}>>')
    p.feed_line(base64.b64encode(jpeg[:150]).decode())
    assert p.feed_line('<<FRAME_END>>')[0][0] == 'error'


def test_protocol_v1_frames_still_parse():
    p = StreamParser()
    jpeg = b'\xff\xd8' + bytes(300)
    p.feed_line('<<FRAME_START>>')
    p.feed_line(base64.b64encode(jpeg).decode())
    assert p.feed_line('<<FRAME_END>>')[0] == ('frame', None, None, jpeg)


# ---------------------------------------------------------------- engine + server
def face_frames():
    cv2 = pytest.importorskip('cv2')
    if not os.path.exists(FACE_IMAGE):
        pytest.skip('face test image not available')
    img = cv2.imread(FACE_IMAGE)
    h, w = img.shape[:2]
    return cv2.resize(img[int(0.30 * h):int(0.82 * h), 0:int(0.40 * w)], (240, 160))


def skin_mask(bgr):
    """Soft YCrCb skin mask (H x W x 1): only skin carries the pulse; the background does not."""
    import cv2
    ycc = cv2.cvtColor(bgr.astype(np.uint8), cv2.COLOR_BGR2YCrCb)
    m = ((ycc[..., 1] > 135) & (ycc[..., 1] < 175) & (ycc[..., 2] > 80) & (ycc[..., 2] < 125)).astype(float)
    return cv2.GaussianBlur(m, (7, 7), 0)[..., None]


def test_engine_end_to_end_with_real_face_image():
    from rppg_engine import RPPGEngine
    base = face_frames().astype(float)
    skin = skin_mask(base)
    eng = RPPGEngine(update_interval_s=0.0)
    t = 0.0
    for _ in range(170):                     # ~20 s at ~8.5 fps
        t += RNG.uniform(0.09, 0.15)
        pulse = np.sin(2 * np.pi * 1.25 * t)                  # 75 beats/min
        # blood-volume absorption in all channels, strongest in green (B, G, R order)
        frame = np.clip(base * (1 - skin * 0.01 * pulse * np.array([0.53, 0.77, 0.33])), 0, 255).astype(np.uint8)
        eng.process_frame(frame, t)
    tel = eng.telemetry()
    assert tel['full_face_visible'], tel['face_guidance']
    assert tel['status'] == 'STABLE'
    assert tel['optical_hr'] == pytest.approx(75.0, abs=2.0)
    snap = eng.analyze_diagnostic_snapshot()
    assert snap['success'] and len(snap['biomarkers']) == 6


def test_engine_compensates_head_sway():
    """Head sway in the heart-rate band (0.9 Hz = 54/min, 5 px, as measured live) slides the skin
    under fixed boxes; the phase-correlation tracker moves the boxes with the face, so the skin
    trace stays clean and the 75/min pulse wins."""
    import cv2
    from rppg_engine import RPPGEngine
    base = face_frames().astype(float)
    skin = skin_mask(base)
    eng = RPPGEngine(update_interval_s=0.0)
    t = 0.0
    for _ in range(170):
        t += RNG.uniform(0.09, 0.15)
        pulse = np.sin(2 * np.pi * 1.25 * t)
        frame = np.clip(base * (1 - skin * 0.01 * pulse * np.array([0.53, 0.77, 0.33])), 0, 255).astype(np.uint8)
        dx, dy = 5.0 * np.sin(2 * np.pi * 0.9 * t), 3.5 * np.cos(2 * np.pi * 0.9 * t + 0.5)
        frame = cv2.warpAffine(frame, np.float32([[1, 0, dx], [0, 1, dy]]), (frame.shape[1], frame.shape[0]),
                               flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        eng.process_frame(frame, t)
    tel = eng.telemetry()
    assert tel['full_face_visible'], tel['face_guidance']
    assert tel['optical_hr'] == pytest.approx(75.0, abs=2.0)
    assert tel['tracked_hr'] == pytest.approx(75.0, abs=2.0)


def test_engine_bridges_brief_disturbance_and_reacquires():
    from rppg_engine import RPPGEngine
    base = face_frames().astype(float)
    skin = skin_mask(base)
    blank = np.full_like(base, 128).astype(np.uint8)          # no face: e.g. head turned away
    eng = RPPGEngine(update_interval_s=0.0)
    t = 0.0

    def run(seconds, face=True):
        nonlocal t
        end = t + seconds
        while t < end:
            t += 0.125                                         # 8 frames/s
            pulse = np.sin(2 * np.pi * 1.25 * t)              # 75 beats/min, physiological channel weights
            frame = np.clip(base * (1 - skin * 0.01 * pulse * np.array([0.53, 0.77, 0.33])), 0, 255)
            eng.process_frame(frame.astype(np.uint8) if face else blank, t)

    run(14)
    assert eng.status == 'STABLE'
    run(1.0, face=False)                                       # 1 s disturbance: bridged
    run(1)
    assert eng.status == 'STABLE'
    assert eng.telemetry()['optical_hr'] == pytest.approx(75.0, abs=2.0)
    run(3.0, face=False)                                       # 3 s: segment restarts
    run(2)
    assert eng.status == 'REACQUIRING'
    run(10)
    assert eng.status == 'STABLE'


def test_server_api_and_recording(tmp_path, monkeypatch):
    monkeypatch.setenv('SONICVITALS_DATA', str(tmp_path))
    monkeypatch.setenv('SONICVITALS_WEBCAM', '0')
    import importlib
    import usb_streamer as srv
    srv = importlib.reload(srv)
    client = srv.app.test_client()

    sid = client.post('/api/session/start', json={'participant': 'P01', 'condition': 'C1'}).get_json()['session_id']
    base = face_frames()
    t = 0.0
    for seq in range(60):
        t += 0.1
        srv.handle_frame(base, t, seq, 'ESP32_S3_CAM')
    x, _ = synthetic_pcg(np.full(8, 0.8))
    for seq, i in enumerate(range(0, len(x) - 255, 256)):
        srv.acoustic.add_block(seq, int(i / 16000 * 1e6), x[i:i + 256])
        srv.recorder.log_audio(seq, int(i / 16000 * 1e6), x[i:i + 256])
    srv.aggregator.last_update = 0
    srv.aggregator.update(dict(srv.optical_snapshot), srv.acoustic.update(force=True))
    client.post('/api/session/stop')

    vit = client.get('/api/vitals').get_json()
    assert vit['video_source'] == 'ESP32_S3_CAM'
    assert vit['acoustic_hr'] == pytest.approx(75.0, abs=2.0)
    assert vit['fusion_source'] == 'acoustic'          # optical still warming up
    assert client.get('/api/config').get_json()['spo2_calibrated'] is False
    assert client.get('/api/audio').status_code == 200
    assert client.get('/api/device').get_json()['webcam_fallback_enabled'] is False

    sdir = tmp_path / sid
    for name in ['meta.json', 'frames.csv', 'audio.wav', 'audio_blocks.csv', 'estimates.csv']:
        assert (sdir / name).exists(), name
    assert len((sdir / 'frames.csv').read_text().splitlines()) == 61


def test_tcp_link_discovers_wifi_node():
    import socket
    import threading
    import usb_streamer as srv
    server = socket.socket()
    server.bind(('127.0.0.1', 0))
    server.listen(1)
    port = server.getsockname()[1]
    received = []

    def node():
        conn, _ = server.accept()
        conn.sendall(b'<<HELLO:SonicVitals,2,WIFI,1,i2c=3c>>\n<<STAT:75,1,2,0,1,1,5000,1,1,0>>\n')
        received.append(conn.recv(100))
        conn.close()

    th = threading.Thread(target=node, daemon=True)
    th.start()
    link = srv.open_node(f'tcp://127.0.0.1:{port}')
    assert link is not None
    assert link.readline().startswith(b'<<STAT:75')
    link.write(b'<<VITALS:72,15,0,80,STABLE>>\n')
    th.join(timeout=2)
    link.close()
    server.close()
    assert received and received[0].startswith(b'<<VITALS:72')
    assert srv.open_node('tcp://127.0.0.1:1') is None      # nothing listening


def test_acoustic_at_4khz_decimated_rate():
    x, beats = synthetic_pcg(np.full(12, 60 / 75), fs=4000)
    out = dsp.estimate_acoustic(x, t0=0.0, fs=4000)
    assert out['hr'] == pytest.approx(75.0, abs=1.0)
    errs = [np.min(np.abs(out['beats'] - (b + 0.04))) for b in beats[1:-1]]
    assert np.max(errs) < 0.015
    eng = AcousticEngine(fs=4000)
    for seq, i in enumerate(range(0, len(x) - 255, 256)):
        eng.add_block(seq, int(i / 4000 * 1e6), x[i:i + 256])
    assert eng.update(force=True)['hr'] == pytest.approx(75.0, abs=1.5)
    assert eng.display_payload()['spec']


def test_hello_key_value_fields():
    ev = StreamParser().feed_line('<<HELLO:SonicVitals,2,WIFI,1,i2c=3c,fs=4000>>')[0]
    assert ev[0] == 'hello' and ev[1]['fs'] == 4000 and ev[1]['i2c'] == '3c' and ev[1]['transport'] == 'WIFI'


# ---------------------------------------------------------------- node raw-pixel ROI stream
def test_protocol_rgb_line():
    p = StreamParser()
    ev = p.feed_line('<<RGB:7,1234567,1000,180000,120000,100000>>')
    assert ev == [('rgb', 7, 1234567, 1000, (180.0, 120.0, 100.0), 0, 0)]
    assert p.feed_line('<<RGB:7,1,x,1,1,1>>')[0][0] == 'error'
    ev = p.feed_line('<<RGB:8,1234667,900,162000,108000,90000,80,20>>')
    assert ev == [('rgb', 8, 1234667, 900, (180.0, 120.0, 100.0), 80, 20)]
    assert p.feed_line('<<RGB:9,1,0,0,0,0,1000,0>>') == [('rgb', 9, 1, 0, None, 1000, 0)]   # all clipped
    assert p.feed_line('<<CAMEXP:812,3>>') == [('camexp', 812, 3)]


def test_engine_prefers_node_rgb_while_gate_passes():
    from rppg_engine import RPPGEngine
    base = face_frames()
    eng = RPPGEngine(update_interval_s=0.0)
    t = 0.0
    for _ in range(20):                         # gated JPEG frames at 5 fps give the gate state and ROIs
        t += 0.2
        eng.process_frame(base, t)
    assert eng.current_rois is not None and eng.full_face_visible
    tn = t
    for i in range(160):                        # 16 s of node samples at 10 Hz with a 72 BPM pulse
        tn += 0.1
        if i % 2 == 0:
            eng.process_frame(base, tn)         # JPEG frames keep the gate fresh; their means are not buffered
        p = 1 + 0.004 * np.sin(2 * np.pi * 1.2 * tn)
        eng.add_node_rgb(tn, (180 * (1 + 0.33 * (p - 1)), 120 * (1 + 0.77 * (p - 1)), 100 * (1 + 0.53 * (p - 1))))
    tel = eng.telemetry()
    assert tel['pulse_source'] == 'node raw pixels'
    assert eng.node_samples_used >= 150
    assert tel['optical_hr'] == pytest.approx(72.0, abs=2.0) and tel['optical_hr_ok']
    # node goes silent: the engine falls back to JPEG means
    for _ in range(15):
        tn += 0.2
        eng.process_frame(base, tn)
    assert eng.telemetry()['pulse_source'] == 'JPEG frames'


def test_engine_rejects_node_rgb_without_gate():
    from rppg_engine import RPPGEngine
    eng = RPPGEngine(update_interval_s=0.0)
    assert not eng.add_node_rgb(1.0, (180.0, 120.0, 100.0))


def test_artifact_suppression_removes_step_and_keeps_pulse():
    t, rgb = synthetic_rgb(hr_bpm=72.0, duration=20.0, fps=(10.0, 10.0))
    rgb[len(rgb) // 2:] *= 1.04                       # head movement / ROI re-lock: 4 % step
    tu, xu = dsp.resample_uniform(t, rgb)
    clean, frac = dsp.suppress_artifacts(xu)
    assert 0 < frac < 0.05
    assert np.max(np.abs(np.diff(np.log(clean[:, 1])))) < 0.01
    out = dsp.estimate_optical(t, rgb)
    assert out['hr_ok'] and out['hr'] == pytest.approx(72.0, abs=2.0)


def test_hr_needs_method_consensus():
    """A peak that only the CHROM projection sees (red-only modulation) is not accepted."""
    t = np.arange(0, 20, 0.1)
    rgb = np.tile([180.0, 120.0, 100.0], (len(t), 1)) + 0.05 * RNG.standard_normal((len(t), 3))
    rgb[:, 0] *= 1 + 0.004 * np.sin(2 * np.pi * 1.3 * t)   # colour change unlike blood volume
    out = dsp.estimate_optical(t, rgb)
    assert out['consensus'] < dsp.CONSENSUS_MIN and not out['hr_ok']


def test_display_hr_needs_confirmation(monkeypatch):
    monkeypatch.setenv('SONICVITALS_WEBCAM', '0')
    import importlib
    import usb_streamer as srv
    srv = importlib.reload(srv)
    agg = srv.VitalsAggregator()
    opt = dict(srv.engine.telemetry(), status='STABLE', patient_detected=True, optical_hr_ok=True,
               optical_quality=0.5, optical_rr=None, spo2_estimate=None)
    aco = dict(hr=None, rho=0.0, rmssd=None, rms=0.0)
    shown = []
    for hr in [70.0, 71.0, 70.5, 71.5]:
        agg.last_update = 0
        agg.update(dict(opt, optical_hr=hr), aco)
        shown.append(agg.latest['hr'])
    assert shown[:2] == [None, None] and shown[2] == pytest.approx(70.5, abs=0.6) and shown[3] is not None
    agg2 = srv.VitalsAggregator()
    for hr in [70.0, 110.0, 52.0]:                     # inconsistent windows never reach the display
        agg2.last_update = 0
        agg2.update(dict(opt, optical_hr=hr), aco)
        assert agg2.latest['hr'] is None


def test_acoustic_rejects_irregular_clicks():
    """Random clicks (door, keyboard, speech onsets) must not produce a PCG heart rate."""
    rng = np.random.default_rng(11)
    fs = 4000
    accepted = 0
    for _ in range(20):
        x = 20 * rng.standard_normal(10 * fs)
        for c in rng.uniform(0, 9.9, rng.integers(5, 20)):
            i = int(c * fs)
            x[i:i + 200] += 2000 * np.sin(2 * np.pi * 80 * np.arange(200) / fs) * np.hanning(200)
        e = dsp.estimate_acoustic(x, fs=fs)
        accepted += e['rho'] >= dsp.MIN_RHO_ACOUSTIC and e['beat_consistency'] >= dsp.MIN_BEAT_CONSISTENCY
    assert accepted <= 1


class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def _run_exposure(ctl, clock, scene, seconds, fps=10):
    """scene(exposure) -> (n, rgb, nclip, ndark) for one frame; the node applies requests instantly."""
    for _ in range(int(seconds * fps)):
        clock.t += 1.0 / fps
        ctl.add(*scene(ctl.exposure))
        if ctl.pending is not None:
            ctl.readback(ctl.pending)


def _skin_scene(gain):
    """Skin brightness proportional to exposure * gain, clipping above the sensor maximum."""
    def scene(exposure):
        level = 13.0 * (exposure * gain) ** 0.45       # brightest channel (R); gamma as measured on the node
        clipped = min(1.0, max(0.0, (level - 200) / 100))   # share of pixels above full scale
        dark = min(1.0, max(0.0, (40 - level) / 40))
        n = int(2000 * (1 - clipped - dark))
        rgb = None if n == 0 else (min(level, 236.0), 0.75 * min(level, 236.0), 0.6 * min(level, 236.0))
        return n, rgb, int(2000 * clipped), int(2000 * dark)
    return scene


@pytest.mark.parametrize('gain', [0.3, 0.6, 1.0, 3.0, 10.0, 30.0])   # dim room ... lamp on the face
def test_exposure_controller_converges_from_any_light(gain):
    from exposure import ExposureController, LEVEL_BAND
    clock = _Clock()
    sent = []
    ctl = ExposureController(lambda e: sent.append(e) or True, now=clock)
    ctl.readback(600)
    _run_exposure(ctl, clock, _skin_scene(gain), 40)
    level = 13.0 * (ctl.exposure * gain) ** 0.45
    if 13.0 * (880 * gain) ** 0.45 >= LEVEL_BAND[0]:         # reachable within the exposure range
        assert LEVEL_BAND[0] <= level <= LEVEL_BAND[1], (gain, ctl.exposure, ctl.state)
        assert ctl.state['clip'] <= 0.02
    assert len(sent) <= 4                                  # converges in a few steps, no hunting
    n_before = len(sent)
    _run_exposure(ctl, clock, _skin_scene(gain), 20)
    assert len(sent) == n_before                           # stays put once settled


def test_exposure_change_restarts_pulse_segment(monkeypatch):
    monkeypatch.setenv('SONICVITALS_WEBCAM', '0')
    import importlib
    import usb_streamer as srv
    srv = importlib.reload(srv)
    srv.exposure_readback(500)                             # first value: no restart
    srv.engine.t_hist.extend([1.0, 2.0])
    srv.engine.rgb_hist.extend([(1, 1, 1), (1, 1, 1)])
    srv.exposure_readback(500)
    assert len(srv.engine.t_hist) == 2
    srv.exposure_readback(300)
    assert len(srv.engine.t_hist) == 0 and srv.device['exposure_changes'] == 1


def test_still_stretch_after_movement_is_analysed_alone():
    """Movement early in the buffer must not spoil the pulse measured after it."""
    rng = np.random.default_rng(5)
    t = np.arange(0, 30, 1 / 15)
    pulse = 0.004 * np.sin(2 * np.pi * 1.4 * t)                      # 84 beats/min
    rgb = np.array([180.0, 120.0, 100.0]) * (1 + np.outer(pulse, [0.33, 0.77, 0.53]))
    moving = t < 12
    rgb[moving] *= (1 + 0.03 * np.cumsum(rng.standard_normal(moving.sum())))[:, None]  # head movement
    rgb += 0.05 * rng.standard_normal(rgb.shape)
    out = dsp.estimate_optical(t, rgb)
    assert out['still_trimmed_s'] >= 10
    assert out['hr_ok'] and out['hr'] == pytest.approx(84.0, abs=2.0)


def test_lighting_flicker_on_background_is_rejected():
    """A coloured lighting wave (lamp / white-balance hunting) that is on the wall as well as on
    the skin must not decide the HR or veto a real pulse in the method-consensus check."""
    rng = np.random.default_rng(3)
    t = np.arange(0, 30, 1 / 15)
    pulse = 0.003 * np.sin(2 * np.pi * 1.2 * t)                          # 72 beats/min, skin only
    tint = np.outer(np.sin(2 * np.pi * 0.9 * t), [0.010, 0.006, 0.002])  # 54 beats/min, warm tint, everywhere
    skin = np.array([180.0, 120.0, 100.0]) * (1 + tint) * (1 - np.outer(pulse, [0.33, 0.77, 0.53]))
    wall = np.array([200.0, 200.0, 190.0]) * (1 + tint)
    skin += 0.05 * rng.standard_normal(skin.shape)
    wall += 0.05 * rng.standard_normal(wall.shape)
    plain = dsp.estimate_optical(t, skin)
    with_bg = dsp.estimate_optical(t, skin, bg_t=t, bg_rgb=wall)
    assert plain['hr_green'] == pytest.approx(54.0, abs=2.0) and not plain['hr_ok']   # green fooled -> vetoed
    assert with_bg['hr'] == pytest.approx(72.0, abs=2.0)
    assert with_bg['hr_green'] == pytest.approx(72.0, abs=2.0)                        # lighting peak skipped
    assert with_bg['hr_ok'] and with_bg['consensus'] == 2
    # the flicker is cancelled by background regression before peak picking (or, failing that, rejected)
    assert with_bg['illum_beta'] is not None and max(with_bg['illum_beta']) > 0.5


def test_tracker_follows_drifting_hr_and_stays_unsure_on_noise():
    rng = np.random.default_rng(4)
    fs, T = 15.0, 90
    t = np.arange(0, T, 1 / fs)
    hr = 70 + 8 * t / T
    p = np.sin(2 * np.pi * np.cumsum(hr / 60) / fs)
    base = np.array([180.0, 125.0, 105.0])
    patches = np.stack([base * (1 - 0.004 * np.outer(p, [0.33, 0.77, 0.53])) + rng.normal(0, 0.4, (len(t), 3))
                        for _ in range(4)], 1)
    noise = np.stack([base + rng.normal(0, 0.4, (len(t), 3)) for _ in range(4)], 1)
    trk, trk_n = dsp.HRTracker(), dsp.HRTracker()
    errs, confs, confs_n = [], [], []
    for te in np.arange(20, T, 2.0):
        m = (t <= te) & (t > te - 30)
        h, c = trk.update(dsp.ensemble_spectrum(t[m], patches[m])[0], te)
        errs.append(abs(h - hr[m].mean()))
        confs.append(c)
        confs_n.append(trk_n.update(dsp.ensemble_spectrum(t[m], noise[m])[0], te)[1])
    assert np.mean(errs) < 2.5 and max(errs) < 5
    assert np.median(confs) >= dsp.TRACKER_HIGH_CONF
    assert max(confs_n) < dsp.TRACKER_HIGH_CONF


def test_camera_exposure_wave_is_cancelled_by_background_regression():
    """A whole-scene brightness wave (auto exposure hunting at 47 BPM, stronger than the pulse)
    must not become the HR when the background is available."""
    rng = np.random.default_rng(9)
    t = np.arange(0, 30, 1 / 15)
    pulse = 0.003 * np.sin(2 * np.pi * 1.25 * t)                       # 75 BPM, skin only
    wave = np.outer(np.sin(2 * np.pi * (47 / 60) * t), [0.012, 0.010, 0.008])   # 47 BPM, everywhere
    skin = np.array([180.0, 125.0, 105.0]) * (1 + wave) * (1 - np.outer(pulse, [0.33, 0.77, 0.53]))
    wall = np.array([200.0, 198.0, 190.0]) * (1 + wave)
    skin += 0.05 * rng.standard_normal(skin.shape)
    wall += 0.05 * rng.standard_normal(wall.shape)
    assert dsp.estimate_optical(t, skin)['hr_green'] == pytest.approx(47.0, abs=2.0)       # fooled without it
    o = dsp.estimate_optical(t, skin, bg_t=t, bg_rgb=wall)
    assert o['hr'] == pytest.approx(75.0, abs=2.0) and o['hr_green'] == pytest.approx(75.0, abs=2.0)
    trk = dsp.HRTracker()
    spec = dsp.ensemble_spectrum(t, skin[:, None, :], bg_t=t, bg_rgb=wall)[0]
    assert trk.update(spec, 30.0)[0] == pytest.approx(75.0, abs=2.0)
