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


# ---------------------------------------------------------------- dashboard card stabilizer
def _feed(stab, readings, tier='accepted', t0=0.0, dt=2.0):
    out = []
    for k, r in enumerate(readings):
        out.append(stab.update(r, tier, t0 + k * dt))
    return out


def test_stabilizer_acquires_and_stays_steady():
    from display_stabilizer import DisplayStabilizer
    s = DisplayStabilizer(jump=8.0)
    rng = np.random.default_rng(0)
    snaps = _feed(s, list(72 + rng.normal(0, 1.5, 40)))
    assert snaps[0]['state'] == 'ACQUIRING' and snaps[0]['value'] is None
    vals = [x['value'] for x in snaps if x['value'] is not None]
    assert abs(vals[-1] - 72) < 2
    assert max(abs(np.diff(vals))) <= 0.3 * 8.0 + 1e-9        # moves at most alpha * jump per update
    assert snaps[-1]['state'] == 'STABLE' and snaps[-1]['level'] == 'ok'


def test_stabilizer_holds_and_flags_a_spike():
    from display_stabilizer import DisplayStabilizer
    s = DisplayStabilizer(jump=8.0)
    _feed(s, [72] * 6)
    spike = s.update(98, 'accepted', 12.0)
    assert spike['value'] == pytest.approx(72, abs=0.5)      # value not moved by the jump
    assert spike['state'] == 'RAPID_CHANGE' and spike['level'] == 'flag'
    back = _feed(s, [72] * 3, t0=14.0)
    assert back[-1]['state'] == 'STABLE' and back[-1]['value'] == pytest.approx(72, abs=0.5)


def test_stabilizer_confirms_a_sustained_change():
    from display_stabilizer import DisplayStabilizer
    s = DisplayStabilizer(jump=8.0, confirm_n=4)
    _feed(s, [72] * 6)
    snaps = _feed(s, [91, 90, 92, 91], t0=12.0)
    assert all(x['value'] == pytest.approx(72, abs=0.5) for x in snaps[:3])   # held while unconfirmed
    assert snaps[-1]['state'] == 'CHANGED' and snaps[-1]['value'] == pytest.approx(91, abs=1)


def test_stabilizer_flags_scatter_and_expires():
    from display_stabilizer import DisplayStabilizer
    s = DisplayStabilizer(jump=8.0, hold_s=15.0)
    _feed(s, [72] * 6)
    snaps = _feed(s, [100, 55, 120, 50, 110, 58, 125, 52, 115, 60], t0=12.0)
    assert snaps[2]['state'] == 'UNSTABLE' and snaps[2]['value'] == pytest.approx(72, abs=0.5)
    assert snaps[-1]['value'] is None and snaps[-1]['state'] in ('UNSTABLE', 'ACQUIRING')


def test_stabilizer_holds_then_drops_without_readings():
    from display_stabilizer import DisplayStabilizer
    s = DisplayStabilizer(jump=8.0, hold_s=15.0)
    _feed(s, [72] * 6)
    snaps = _feed(s, [None] * 10, t0=12.0)
    assert snaps[0]['state'] == 'HOLDING' and snaps[0]['value'] == pytest.approx(72, abs=0.5)
    assert snaps[-1]['state'] == 'NO_SIGNAL' and snaps[-1]['value'] is None


def test_stabilizer_badge_does_not_flicker_between_tiers():
    from display_stabilizer import DisplayStabilizer
    s = DisplayStabilizer(jump=8.0, dwell_s=4.0)
    _feed(s, [72] * 6)
    states = [s.update(72, 'accepted' if k % 2 else 'tracked_low', 12.0 + k)['state'] for k in range(12)]
    changes = sum(a != b for a, b in zip(states, states[1:]))
    assert changes <= 3                                       # 1 s updates, 4 s minimum dwell


def test_stabilizer_weak_readings_cannot_confirm_a_jump():
    """Tracker drift (68 -> 50, below the quality gate) is held and flagged, then withdrawn."""
    from display_stabilizer import DisplayStabilizer
    s = DisplayStabilizer(jump=8.0, hold_s=15.0)
    first = _feed(s, [68] * 5, tier='tracked_high')
    assert first[-1]['state'] == 'LOW_CONFIDENCE' and first[-1]['level'] == 'warn'   # never green without the gate
    snaps = _feed(s, [50] * 12, tier='tracked_high', t0=10.0)
    assert all(x['state'] == 'RAPID_CHANGE' and x['value'] == pytest.approx(68, abs=0.5) for x in snaps[:6])
    assert any(x['value'] is None and x['state'] == 'UNSTABLE' for x in snaps)       # withdrawn, flagged
    back = _feed(s, [50] * 6, tier='tracked_high', t0=40.0)
    assert back[-1]['value'] == pytest.approx(50, abs=0.5) and back[-1]['state'] == 'LOW_CONFIDENCE'


def test_stabilizer_flags_disputed_readings():
    from display_stabilizer import DisplayStabilizer
    s = DisplayStabilizer(jump=8.0, hold_s=15.0)
    _feed(s, [80] * 4, tier='tracked_low')
    x = s.update(54, 'tracked_low', 10.0, dispute='other methods agree on 84')
    assert x['state'] == 'DISAGREE' and x['level'] == 'flag' and x['value'] == pytest.approx(80, abs=0.5)
    # back in agreement: the flag clears at once
    y = s.update(81, 'accepted', 12.0)
    assert y['state'] != 'DISAGREE' and y['value'] == pytest.approx(80.3, abs=0.5)


def test_stabilizer_keeps_flag_when_disputed_value_expires():
    from display_stabilizer import DisplayStabilizer
    s = DisplayStabilizer(jump=8.0, hold_s=15.0)
    _feed(s, [80] * 4, tier='tracked_low')
    snaps = [s.update(47, 'tracked_low', 10.0 + 2 * k, dispute='others agree on 80') for k in range(12)]
    assert snaps[-1]['value'] is None and snaps[-1]['state'] == 'DISAGREE' and snaps[-1]['level'] == 'flag'


def test_consensus_averages_agreeing_methods_and_drops_outliers():
    from display_stabilizer import robust_consensus
    c = robust_consensus([('SonicVitals', 77.5), ('CHROM', 77.5), ('POS', 77.8), ('GREEN', 52.9),
                          ('TS-CAN', 80.9), ('PhysNet', 80.9), ('EfficientPhys', 80.9), ('Microphone', None)])
    assert c['n'] == 7 and c['agree'] == 6 and c['excluded'] == ['GREEN']
    assert c['value'] == pytest.approx(np.mean([77.5, 77.5, 77.8, 80.9, 80.9, 80.9]), abs=0.05)
    assert c['tier'] == 'consensus_strong'


def test_consensus_refuses_a_split_vote():
    from display_stabilizer import robust_consensus
    c = robust_consensus([('a', 47), ('b', 47.5), ('c', 48), ('d', 80), ('e', 81), ('f', 79)])
    assert c['tier'] is None                                   # two camps: no value, card flags it
    weak = robust_consensus([('a', 70), ('b', 72), ('c', 71), ('d', 95), ('e', 50)])
    assert weak['tier'] == 'consensus_weak' and weak['agree'] == 3


def test_no_hrv_from_handling_noise():
    """Loud irregular clicks (mic being handled) must not produce beats or an RMSSD."""
    rng = np.random.default_rng(5)
    fs = 16000
    x = 30 * rng.standard_normal(64 * fs)
    for c in rng.uniform(0, 63.9, 120):
        i = int(c * fs)
        x[i:i + 800] += 3000 * np.sin(2 * np.pi * 80 * np.arange(800) / fs) * np.hanning(800)
    eng = AcousticEngine()
    for seq, i in enumerate(range(0, len(x) - 255, 256)):
        eng.add_block(seq, int(i / fs * 1e6), x[i:i + 256])
        if seq % 62 == 61:
            res = eng.update(force=True)
            assert res['rmssd'] is None
    assert eng.update(force=True)['rmssd'] is None


# ---------------------------------------------------------------- labelled demo mode
def test_demo_pattern_reads_as_normal_heart_sounds():
    """The simulated pattern is a regular S1/S2 rhythm at the requested rate (what a working chest mic shows)."""
    from demo_sim import heart_sound_pattern
    for hr in (60.0, 78.0, 95.0):
        x = heart_sound_pattern(hr, 10.0, 4000, t_end=1000.0)
        e = dsp.estimate_acoustic(x.astype(float), fs=4000)
        assert e['hr'] == pytest.approx(hr, abs=3.0)
        assert e['rho'] >= dsp.MIN_RHO_ACOUSTIC


def test_demo_mode_off_by_default_and_values_in_normal_range():
    from demo_sim import DemoMode, SPO2_RANGE, RMSSD_RANGE_MS
    d = DemoMode(seed=1)
    assert d.enabled is False
    d.set(True)
    for k in range(200):
        v = d.values(now=2.0 * k)
        assert SPO2_RANGE[0] <= v['spo2'] <= SPO2_RANGE[1]
        assert RMSSD_RANGE_MS[0] <= v['hrv'] <= RMSSD_RANGE_MS[1]


# ---------------------------------------------------------------- breathing rate (multi-source fusion)
def _breathing_face(rng, br, hr=75.0, dur=30.0, breathing=True, drift=0.0015):
    """Webcam-like skin RGB (22-30 fps) with random-walk drift (1-2 % over 30 s, as measured live) and the
    three respiratory modulations of the pulse (intensity 0.3 %, amplitude 20 %, sinus arrhythmia +-4 BPM),
    plus vertical head motion (0.4 % of the face height)."""
    t = np.cumsum(rng.uniform(1 / 30, 1 / 22, int(dur * 30)))
    t = t[t < dur]
    resp = np.sin(2 * np.pi * br / 60 * t + rng.uniform(0, 6)) if breathing else np.zeros_like(t)
    pulse_phase = 2 * np.pi * np.cumsum(np.r_[0, np.diff(t)] * (hr + 4 * resp) / 60)
    pulse = 0.003 * (1 + 0.2 * resp) * np.sin(pulse_phase)
    base = 1 + np.cumsum(rng.normal(0, drift, len(t))) + 0.003 * resp
    rgb = np.outer(base, [170.0, 120.0, 95.0]) * (1 - np.outer(pulse, [0.33, 0.77, 0.53]))
    rgb += 0.08 * rng.standard_normal(rgb.shape)
    my = 0.004 * resp + np.cumsum(rng.normal(0, 0.0003, len(t))) + 0.001 * rng.standard_normal(len(t))
    return t, rgb, my


def test_rr_tracks_known_rates_under_drift():
    rng = np.random.default_rng(3)
    for br in (12.0, 18.0, 24.0):
        hits = 0
        for _ in range(10):
            t, rgb, my = _breathing_face(rng, br)
            rr = dsp.estimate_optical(t, rgb, motion_t=t, motion_y=my)['rr']
            hits += rr is not None and abs(rr - br) <= 1.5
        assert hits >= 8, (br, hits)


def test_rr_not_pulled_below_ten_by_drift():
    """The old single-peak method piled up at the 9 breaths/min band edge under drift."""
    rng = np.random.default_rng(4)
    for _ in range(10):
        t, rgb, my = _breathing_face(rng, 18.0)
        o = dsp.estimate_optical(t, rgb, motion_t=t, motion_y=my)
        assert o['rr_estimate'] is not None and o['rr_estimate'] > 14.0


def test_rr_no_rate_without_breathing():
    rng = np.random.default_rng(5)
    reported = sum(dsp.estimate_optical(*_breathing_face(rng, 15.0, breathing=False)[:2])['rr'] is not None
                   for _ in range(30))
    assert reported <= 1


# ---------------------------------------------------------------- camera HRV
def _pulse_video(rng, ibis, fps=30.0, noise=0.0004):
    """Skin RGB at ~fps with a pulse whose beats follow the given inter-beat intervals."""
    beats = np.concatenate([[0.5], 0.5 + np.cumsum(ibis)])
    t = np.cumsum(rng.uniform(0.9 / fps, 1.1 / fps, int((beats[-1] + 1) * fps)))
    t = t[t < beats[-1] + 0.5]
    k = np.clip(np.searchsorted(beats, t) - 1, 0, len(beats) - 2)
    phase = (t - beats[k]) / (beats[k + 1] - beats[k])                   # 0..1 within each beat
    pulse = 0.004 * (np.exp(-((phase - 0.15) / 0.08) ** 2) + 0.4 * np.exp(-((phase - 0.45) / 0.1) ** 2))
    base = 1 + np.cumsum(rng.normal(0, 0.0003, len(t)))
    rgb = np.outer(base, [170.0, 120.0, 95.0]) * (1 - np.outer(pulse, [0.33, 0.77, 0.53]))
    return t, rgb + noise * 120 * rng.standard_normal(rgb.shape)


def test_camera_hrv_matches_true_rmssd():
    rng = np.random.default_rng(12)
    n = 40
    ibis = 0.8 + 0.04 * np.sin(2 * np.pi * np.arange(n) / 5) + 0.01 * rng.standard_normal(n)   # RSA-like
    true_rmssd = 1000 * np.sqrt(np.mean(np.diff(ibis) ** 2))
    t, rgb = _pulse_video(rng, ibis, noise=0.0001)
    out = dsp.camera_hrv(t, rgb, 75.0, snr_db=dsp.estimate_optical(t, rgb)['snr'])
    assert out['ok'], out['reason']
    assert out['rmssd'] == pytest.approx(true_rmssd, rel=0.25)
    assert out['median_hr'] == pytest.approx(75.0, abs=3.0)


def test_camera_hrv_refuses_slow_video():
    rng = np.random.default_rng(13)
    t, rgb = _pulse_video(rng, np.full(40, 0.8), fps=10.0)
    out = dsp.camera_hrv(t, rgb, 75.0, snr_db=5.0)
    assert not out['ok'] and 'fps' in out['reason']


def test_camera_hrv_refuses_weak_pulse():
    """At typical live SNR (-2 dB and below) beat timing is noise: no HRV is reported."""
    rng = np.random.default_rng(14)
    t, rgb = _pulse_video(rng, np.full(40, 0.8), noise=0.002)
    snr = dsp.estimate_optical(t, rgb)['snr']
    out = dsp.camera_hrv(t, rgb, 75.0, snr_db=snr)
    assert snr < dsp.HRV_MIN_SNR_DB and not out['ok'] and 'weak' in out['reason']


# ---------------------------------------------------------------- face insights (perfusion map, liveness, blinks, head, breathing pattern)
def _face_video(amp, seconds=22.0, fps=30.0, seed=0, hr=75.0):
    """The test face at ~fps; amp = relative skin pulse (0: a still photo with sensor noise)."""
    from rppg_engine import RPPGEngine
    base = face_frames().astype(float)
    skin = skin_mask(base)
    rng = np.random.default_rng(seed)
    eng = RPPGEngine(update_interval_s=2.0)
    eng.async_estimate = False
    eng.display_hr = hr
    t = 0.0
    for _ in range(int(seconds * fps)):
        t += rng.uniform(0.9 / fps, 1.1 / fps)
        f = base * (1 - skin * amp * np.sin(2 * np.pi * hr / 60 * t) * np.array([0.53, 0.77, 0.33]))
        eng.process_frame(np.clip(f + rng.normal(0, 1.0, f.shape), 0, 255).astype(np.uint8), t)
    return eng.telemetry()['insights']


def test_perfusion_map_and_liveness_on_pulsing_face():
    ins = _face_video(0.003)
    p = ins['perfusion']
    assert p['ok'] and p['skin_pulse_frac'] > 0.5 and p['bg_pulse_frac'] < 0.1
    assert p['live_hr'] == pytest.approx(75.0, abs=3.0)          # found without being told the rate
    expected_pi = 2 * 0.003 * 0.77 * 100                          # peak-to-peak green pulse, % of DC
    assert p['pi_median'] == pytest.approx(expected_pi, rel=0.35)
    assert ins['liveness']['state'] == 'LIVE'
    assert ins['head']['state'] == 'STEADY'


def test_still_photo_is_not_live():
    ins = _face_video(0.0)
    assert ins['perfusion']['skin_pulse_frac'] < 0.1
    assert ins['liveness']['state'] == 'NO_PULSE'


def test_liveness_from_blinks_when_pulse_is_too_weak():
    from face_insights import LivenessCheck
    lc = LivenessCheck()
    weak = dict(ok=True, live_skin_frac=0.08, live_bg_frac=0.05, live_coherence=0.3, live_hr=48.0)
    assert lc.update(weak, blinks_30s=0)['state'] == 'CHECKING'   # weak pulse alone: undecided, never "photo" at once
    assert lc.update(weak, blinks_30s=3)['state'] == 'LIVE'


def test_blink_counter_counts_dips_once_despite_level_shifts():
    from face_insights import BlinkCounter
    bc = BlinkCounter()
    fps = 30.0
    t = np.arange(0, 40, 1 / fps)
    ear = np.where(t < 20, 0.28, 0.22)                           # gaze change: the open level shifts
    blinks = [2.0, 7.5, 12.0, 19.0, 24.0, 31.0, 36.5]
    for b in blinks:
        ear = ear - 0.2 * np.exp(-0.5 * ((t - b) / 0.04) ** 2)    # ~150 ms blinks
    ear = ear - 0.18 * ((t > 15.0) & (t < 16.5))                  # 1.5 s eye closure: not a blink
    ear = ear + 0.004 * np.random.default_rng(0).standard_normal(len(t))
    for tt, e in zip(t, ear):
        bc.add(tt, e)
    found = bc.blinks
    assert len(found) == len(blinks)
    assert all(min(abs(f - b) for b in blinks) < 0.1 for f in found)


def test_head_steadiness():
    from face_insights import head_steadiness
    t = np.arange(0, 10, 1 / 30)
    rng = np.random.default_rng(1)
    still = head_steadiness(t, 0.5 + 0.003 * rng.standard_normal(len(t)), 0.5 + 0.003 * rng.standard_normal(len(t)))
    moving = head_steadiness(t, 0.5 + 0.08 * np.sin(2 * np.pi * 0.3 * t), 0.5 + 0.0 * t)
    assert still['state'] == 'STEADY' and moving['state'] == 'MOVING'


def test_breathing_pattern_regular_irregular_pause():
    fs = 15.0
    t = np.arange(0, 30, 1 / fs)
    rng = np.random.default_rng(2)
    regular = np.sin(2 * np.pi * 0.25 * t)
    durations = rng.choice([2.0, 6.0], 20)                                # breaths randomly 2 s or 6 s (CV ~0.5)
    edges = np.concatenate([[0.0], np.cumsum(durations)])
    k = np.searchsorted(edges, t, side='right') - 1
    irregular = np.sin(2 * np.pi * (k + (t - edges[k]) / durations[k]))
    pause = regular * ((t < 10) | (t > 21))                               # 11 s breath-hold
    noise = lambda: 0.05 * rng.standard_normal(len(t))
    assert dsp.breathing_pattern(regular + noise(), fs)['pattern'] == 'REGULAR'
    assert dsp.breathing_pattern(irregular + noise(), fs)['pattern'] == 'IRREGULAR'
    out = dsp.breathing_pattern(pause + noise(), fs)
    assert out['pattern'] == 'PAUSE' and out['pause_s'] >= 8.0


def test_last_movement_end():
    from face_insights import last_movement_end
    t = np.arange(0, 30, 1 / 30)
    rng = np.random.default_rng(3)
    x = 0.5 + 0.002 * rng.standard_normal(len(t))
    y = 0.5 + 0.002 * rng.standard_normal(len(t))
    assert last_movement_end(t, x, y) == pytest.approx(0.0)              # never moved: whole window usable
    x2 = x + 0.08 * ((t > 9.5) & (t < 10.5))                              # a 1 s head movement at 10 s
    assert last_movement_end(t, x2, y) == pytest.approx(11.0, abs=0.6)


def test_blood_flow_map_capture():
    """A 30 s capture on a still pulsing face finishes with a map; the image is the captured one."""
    from rppg_engine import RPPGEngine
    base = face_frames().astype(float)
    skin = skin_mask(base)
    rng = np.random.default_rng(4)
    eng = RPPGEngine(update_interval_s=2.0)
    eng.async_estimate = False
    eng.display_hr = 75.0
    assert eng.insights.map_jpeg() is None and eng.insights.capture_status()['state'] == 'IDLE'
    eng.insights.start_capture()
    t = 0.0
    for _ in range(int(36 * 30)):
        t += rng.uniform(0.03, 0.037)
        f = base * (1 - skin * 0.003 * np.sin(2 * np.pi * 1.25 * t) * np.array([0.53, 0.77, 0.33]))
        eng.process_frame(np.clip(f + rng.normal(0, 1.0, f.shape), 0, 255).astype(np.uint8), t)
    cap = eng.insights.capture_status()
    assert cap['state'] == 'DONE', cap
    assert cap['result']['skin_pulse_frac'] > 0.5 and eng.insights.map_jpeg() is not None


def test_capture_restarts_when_the_head_moves():
    from face_insights import FaceInsights
    fi = FaceInsights(use_mesh=False)
    fi.start_capture()
    fi.capture.update(t0=100.0, t_last=110.0)
    fi.frame_t.append(110.0)
    fi._capture_step(75.0, still_from=106.0)                  # moved 6 s into the capture
    c = fi.capture_status()
    assert c['state'] == 'RECORDING' and 'moved' in c['message'] and c["seconds_left"] == 30.0
