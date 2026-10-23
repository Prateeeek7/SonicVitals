"""SonicVitals host server.

Reads the edge node's serial stream (video frames + audio blocks, protocol v2),
runs the optical and acoustic engines, fuses heart rate, returns vitals to the
node's OLED, records sessions to disk, and serves the browser workstation.

Environment variables
  SONICVITALS_PORT     serial port or tcp://host:port to use (default: auto-detect)
  SONICVITALS_HOSTS    comma-separated Wi-Fi node addresses to try
                       (default: sonicvitals.local,192.168.4.1; port 3333)
  SONICVITALS_LINK     auto (default) | wifi | serial: which links to search. Use wifi while
                       flashing over USB so the server never opens the serial port.
  SONICVITALS_SCAN     1 = also scan the local /24 for a node on port 3333 (default), 0 = off
  SONICVITALS_BAUD     baud rate for UART builds (default 1000000; ignored by native USB)
  SONICVITALS_WEBCAM   0 = hardware only, never use the laptop webcam (default),
                       1 = fall back to the host webcam when no node frames arrive (development)
  SONICVITALS_DATA     directory for recorded sessions (default: <repo>/data/sessions)
"""
import glob
import json
import os
import socket
import sys
import threading
import time
from collections import deque

import cv2
import numpy as np
import serial
from flask import Flask, Response, jsonify, render_template_string, request
from flask_cors import CORS

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import vitals_dsp as dsp                      # noqa: E402
from acoustic_engine import AcousticEngine    # noqa: E402
from display_stabilizer import DisplayStabilizer, robust_consensus  # noqa: E402
from demo_sim import DemoMode, heart_sound_pattern  # noqa: E402
from exposure import ExposureController        # noqa: E402
from live_methods import LiveDeepModels        # noqa: E402
from protocol import StreamParser             # noqa: E402
from recorder import SessionRecorder          # noqa: E402
from rppg_engine import RPPGEngine            # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
BAUD = int(os.environ.get('SONICVITALS_BAUD', '1000000'))
FIXED_PORT = os.environ.get('SONICVITALS_PORT')
WEBCAM_FALLBACK = os.environ.get('SONICVITALS_WEBCAM', '0') == '1'
DATA_DIR = os.environ.get('SONICVITALS_DATA', os.path.join(REPO, 'data', 'sessions'))
CALIBRATION_FILE = os.path.join(HERE, 'spo2_calibration.json')

DISPLAY_INTERVAL_S = 2.0      # vitals panel / OLED update period
EMA_HR_RR = 0.2               # display smoothing weights (paper Sec. V-J)
EMA_SPO2 = 0.1
MEDIAN_N = 3                  # median of the last 3 accepted fused HR values (6 s) before the EMA
CONFIRM_BPM = 5.0             # a new HR is first shown only when MEDIAN_N accepted values within CONFIRM_S
CONFIRM_S = 12.0              # lie within +-CONFIRM_BPM of their median (a lone noise window cannot show)
TRACK_JUMP_BPM = 12.0         # a displayed HR moves by more than this only once the new value is confirmed
HOLD_S = 15.0                 # a displayed value without a fresh accepted estimate expires after this
DISPUTE_BPM = 12.0            # an unverified card reading this far from the other methods' median is flagged
DISPUTE_MAD_BPM = 8.0         # ... when at least 3 other methods agree among themselves (median abs. deviation)
DOWNLINK_INTERVAL_S = 1.5


def load_spo2_calibration():
    """A, B for SpO2 = A - B * ratio, fitted by analysis/evaluate.py. None if absent."""
    try:
        with open(CALIBRATION_FILE) as f:
            cal = json.load(f)
        return cal if 'A' in cal and 'B' in cal else None
    except (OSError, ValueError):
        return None


app = Flask(__name__)
CORS(app)

state_lock = threading.Lock()
engine = RPPGEngine(spo2_calibration=load_spo2_calibration(), face_mesh=True)
engine.async_estimate = True          # estimation in a worker thread: the camera loop never waits
acoustic = AcousticEngine()
demo = DemoMode()      # labelled demo mode (demo_sim.py); off unless switched on from the dashboard
# Live deep-model comparison (rPPG-Toolbox TS-CAN / PhysNet / EfficientPhys); SONICVITALS_DEEP=0 disables it.
deep = LiveDeepModels() if os.environ.get('SONICVITALS_DEEP', '1') != '0' else None
recorder = SessionRecorder(DATA_DIR)

current_frame = None
optical_snapshot = engine.telemetry()
active_source = 'SEARCHING'
last_node_frame_time = 0.0
last_frame_host_time = 0.0    # host time of the last frame from the selected camera
camera_choice = 'node'        # 'node' (ESP32-S3 camera) or 'webcam' (host camera), switched from the dashboard
ser_conn = None
device = {'connected': False, 'port': None, 'transport': None, 'firmware': None,
          'mic_enabled': None, 'stat': {}, 'frames_ok': 0, 'frames_bad': 0,
          'host_fps': None, 'frame_interval_sd_ms': None, 'last_seen': 0.0}
frame_times = []              # recent capture timestamps (s) for measured fps / jitter


class VitalsAggregator:
    """Fuses optical and acoustic HR every DISPLAY_INTERVAL_S and smooths for display."""

    def __init__(self):
        self.display = dict(hr=None, rr=None, spo2=None)
        self.fresh_t = dict(hr=None, rr=None, spo2=None)
        self.recent_hr = []
        self.latest = {}
        self.last_update = 0.0
        # Dashboard cards: one steady value per vital with a status badge (display_stabilizer.py).
        # Heart rate: a reading more than 8 BPM from the shown value is held and flagged until 4 readings
        # in a row agree; breathing: 4 breaths/min.
        self.hr_card = DisplayStabilizer(jump=8.0, agree=5.0, unstable_spread=10.0, lo=40.0, hi=180.0, hold_s=HOLD_S)
        self.rr_card = DisplayStabilizer(jump=4.0, agree=3.0, unstable_spread=6.0, lo=4.0, hi=40.0, hold_s=20.0)
        self.card_seq = None          # optical estimate last fed to the cards

    @staticmethod
    def _method_rows(opt, aco, fused):
        """Every method's heart rate at this moment (the comparison table). The heart-rate card shows
        the robust average of these same rows, so table and card always come from one snapshot."""
        face = bool(opt.get('patient_detected'))
        if face and opt.get('optical_hr_ok') and opt.get('status') == 'STABLE':     # camera only, no microphone
            ours, note = opt['optical_hr'], 'accepted (all checks)'
        elif face and opt.get('tracked_hr') is not None and opt.get('status') == 'STABLE':
            ours, note = opt['tracked_hr'], f"tracked, confidence {100 * (opt.get('tracked_conf') or 0):.0f}%"
        else:
            ours, note = None, 'no estimate'
        rows = [dict(name='SonicVitals', family='Ours (gated + tracked)', hr=ours, note=note)]
        for name, key in (('CHROM', 'optical_hr_chrom'), ('POS', 'optical_hr_pos'), ('GREEN', 'optical_hr_green')):
            rows.append(dict(name=name, family='Signal processing',
                             hr=opt.get(key) if face and opt.get('status') == 'STABLE' else None, note='skin boxes'))
        snap = deep.snapshot() if deep else dict(status='disabled (SONICVITALS_DEEP=0)', results={}, age_s=None)
        # deep models refresh every 12 s and take up to ~10 s to run on this Mac: 30 s keeps them in the table
        fresh = snap['age_s'] is not None and snap['age_s'] < 30 and face
        for name in ('TS-CAN', 'PhysNet', 'EfficientPhys'):
            r = snap['results'].get(name, {})
            rows.append(dict(name=name, family='Deep learning (PURE-trained)', hr=r.get('hr') if fresh else None,
                             note=f"{r['ms']} ms" + (' (CPU)' if name == 'PhysNet' and 'cuda' not in snap['status'] else '')
                             if fresh and r.get('ms') is not None else ''))
        # Shown for comparison only: the heart-rate output is camera-only (the chest mic rarely finds a rhythm).
        rows.append(dict(name='Microphone (PCG)', family='Acoustic', hr=aco.get('hr'), for_hr=False,
                         note='not used for heart rate' if acoustic.connected() else 'node offline'))
        return rows, snap['status']

    @staticmethod
    def _hr_reading(opt, aco, fused):
        """Best camera heart-rate reading this update and its tier (the raw single-window peak and the
        microphone are never used)."""
        face = opt.get('patient_detected')
        if face and opt.get('optical_hr_ok') and opt.get('status') == 'STABLE':
            return opt['optical_hr'], 'accepted'
        trk = opt.get('tracked_hr')
        if face and trk is not None and opt.get('status') == 'STABLE':   # not while the 30 s buffer fills
            return trk, 'tracked_high' if (opt.get('tracked_conf') or 0.0) >= dsp.TRACKER_HIGH_CONF else 'tracked_low'
        return None, None

    def _put(self, key, new, alpha, now):
        """EMA update with a fresh value, or hold the old one for at most HOLD_S."""
        if new is not None:
            self.display[key] = self._ema(self.display[key], new, alpha)
            self.fresh_t[key] = now
        elif self.fresh_t[key] is None or now - self.fresh_t[key] > HOLD_S:
            self.display[key] = None

    def _age(self, key, now):
        return None if self.fresh_t[key] is None or self.display[key] is None else round(now - self.fresh_t[key], 1)

    @staticmethod
    def _ema(prev, new, alpha):
        if new is None:
            return prev
        return new if prev is None else (1 - alpha) * prev + alpha * new

    def update(self, opt, aco):
        now = time.time()
        if now - self.last_update < DISPLAY_INTERVAL_S:
            return False
        self.last_update = now

        stable = opt['status'] == 'STABLE'
        g_o = 1.0 if stable and opt['optical_hr_ok'] else 0.0
        w_o = opt['optical_quality'] * g_o
        w_a = aco['rho'] if aco['hr'] is not None else 0.0
        fused = dsp.fuse_hr(opt['optical_hr'], w_o, aco['hr'], w_a)

        if not opt['patient_detected'] and fused['source'] != 'acoustic':
            self.display = dict(hr=None, rr=None, spo2=None)
            self.fresh_t = dict(hr=None, rr=None, spo2=None)
            self.recent_hr = []
        else:
            hr_med = None
            self.recent_hr = [(t, h) for t, h in self.recent_hr if now - t <= CONFIRM_S]
            if fused['hr'] is not None:
                self.recent_hr = (self.recent_hr + [(now, fused['hr'])])[-MEDIAN_N:]
                vals = np.array([h for _, h in self.recent_hr])
                hr_med = float(np.median(vals))
                confirmed = len(vals) == MEDIAN_N and np.all(np.abs(vals - hr_med) <= CONFIRM_BPM)
                if self.display['hr'] is None and not confirmed:
                    hr_med = None                       # not yet confirmed: keep showing "--"
                elif self.display['hr'] is not None and abs(hr_med - self.display['hr']) > TRACK_JUMP_BPM \
                        and not confirmed:
                    hr_med = None                       # an unconfirmed jump is held, not displayed
            self._put('hr', hr_med, EMA_HR_RR, now)
            self._put('rr', opt['optical_rr'] if stable else None, EMA_HR_RR, now)
            self._put('spo2', opt['spo2_estimate'] if stable else None, EMA_SPO2, now)

        # Each optical estimate is fed to the cards once: a value repeated between estimates is not
        # a second agreeing reading. (The microphone estimate is recomputed on every call.)
        seq = opt.get('estimate_seq')
        fresh = seq != self.card_seq
        self.card_seq = seq
        hr_r, hr_tier = self._hr_reading(opt, aco, fused)
        optical_tier = hr_r is not None                      # every heart-rate reading is now from the camera
        # Card value = robust average of the methods in the comparison table (display_stabilizer.
        # robust_consensus): needs >= 3 methods within 8 BPM of each other and at least half of all.
        rows, deep_status = self._method_rows(opt, aco, fused)
        cons = robust_consensus([(r['name'], r['hr']) for r in rows if r.get('for_hr', True)])
        for r in rows:
            r['in_average'] = bool(cons) and r['name'] in cons['used'] and cons['tier'] is not None
        if cons and cons['tier'] == 'consensus_strong':
            # CHROM, POS, GREEN (and our tracker) all read the same skin-colour trace, so head motion can make
            # them agree on a wrong rate together. Green (confident) needs an independent family to agree too
            # (the deep models see the whole face video), or the strict quality gate to pass.
            fams = {r['family'] for r in rows if r['in_average']}
            independent = any(f.startswith('Deep') for f in fams)
            if not (independent or (opt.get('optical_hr_ok') and opt.get('status') == 'STABLE')):
                cons = dict(cons, tier='consensus_weak')
        dispute = None
        if cons and cons['n'] >= 3:
            if cons['tier'] is not None:
                hr_r, hr_tier = cons['value'], cons['tier']
            else:
                hr_r, hr_tier = cons['median'], 'consensus_weak'
                dispute = ('No majority of methods agree within 8 BPM: ' +
                           ', '.join(f"{r['name']} {r['hr']:.0f}" for r in rows if r['hr'] is not None) + '.')
            optical_tier = True
        hr_card = self.hr_card.update(hr_r, hr_tier, now, dispute) if fresh or not optical_tier or hr_r is None \
            else self.hr_card.snapshot(now)
        # the perfusion map measures each skin cell at the heart rate the dashboard shows
        engine.display_hr = hr_card['value'] if hr_card['value'] is not None and hr_card['level'] in ('ok', 'warn') else None
        if cons and cons['tier'] is not None and hr_card['state'] in ('STABLE', 'LOW_CONFIDENCE'):
            hr_card = dict(hr_card, label=f"{cons['agree']} OF {cons['n']} METHODS AGREE",
                           detail=f"Average of {', '.join(cons['used'])} (now {cons['value']:.1f} BPM, spread "
                                  f"{cons['spread']:.1f} BPM)" + (f"; excluded as outliers: {', '.join(cons['excluded'])}"
                                                                if cons['excluded'] else '') + '. ' +
                                  ('' if hr_card['state'] == 'STABLE' else 'Shown as an estimate: green needs >= 4 methods (60 %) agreeing, '
                                   'including an independent family (deep models) or the strict quality check.'))
        if stable and opt.get('optical_rr') is not None:
            rr_r, rr_tier = opt['optical_rr'], 'accepted'
        elif stable and opt.get('optical_rr_estimate') is not None:
            rr_r, rr_tier = opt['optical_rr_estimate'], 'tracked_low'
        else:
            rr_r, rr_tier = None, None
        rr_card = self.rr_card.update(rr_r, rr_tier, now) if fresh or rr_r is None else self.rr_card.snapshot(now)
        found = {k: v for k, v in (opt.get('rr_sources') or {}).items() if v}
        names = dict(riiv='skin brightness', riav='pulse height', rifv='pulse rate', motion='head motion')
        if found and rr_card['state'] in ('STABLE', 'LOW_CONFIDENCE'):
            agree = opt.get('rr_agree') or 0
            solo = (opt.get('insights') or {}).get('breathing', {}).get('source')
            rr_card = dict(rr_card, label=(f"{agree} OF {len(found)} SIGNALS AGREE" if agree >= 2 else
                                           f"CLEAR {names.get(solo, 'BREATHING').upper()} SIGNAL")
                           if rr_card['state'] == 'STABLE' else rr_card['label'],
                           detail='Breathing signals: ' + ', '.join(f"{names.get(k, k)} {v['bpm']:.0f}/min"
                                                                    for k, v in found.items()) +
                                  ('. They agree within 4 breaths/min.' if rr_card['state'] == 'STABLE' else
                                   '. Fewer than 2 clear signals agree, so this is an estimate.'))

        self.latest = {
            'hr': None if self.display['hr'] is None else round(self.display['hr'], 1),
            'rr': None if self.display['rr'] is None else round(self.display['rr'], 1),
            'spo2': None if self.display['spo2'] is None else round(self.display['spo2'], 1),
            'hr_card': hr_card,
            'rr_card': rr_card,
            'hr_consensus': cons,
            'method_rows': rows,
            'deep_status': deep_status,
            'hr_age_s': self._age('hr', now),
            'rr_age_s': self._age('rr', now),
            'hrv': None if aco['rmssd'] is None else round(aco['rmssd'], 1),
            'quality': None if fused['source'] is None else round(100 * max(fused['w_o'], fused['w_a']), 1),
            'fusion_hr': None if fused['hr'] is None else round(fused['hr'], 1),
            'fusion_source': fused['source'],
            'fusion_w_optical': round(fused['w_o'], 3),
            'fusion_w_acoustic': round(fused['w_a'], 3),
            'fusion_disagreement': fused['disagreement'],
            'acoustic_hr': None if aco['hr'] is None else round(aco['hr'], 1),
            'acoustic_hr_estimate': None if aco.get('hr_estimate') is None else round(aco['hr_estimate'], 1),
            'acoustic_consistency': aco.get('beat_consistency'),
            'acoustic_rho': round(aco['rho'], 3),
            'acoustic_rms': round(aco['rms'], 1),
            'acoustic_connected': acoustic.connected(),
            'display_updated': now,
        }
        recorder.log_estimate({
            'host_time': f'{now:.3f}', 'device_t': frame_times[-1] if frame_times else '',
            'status': opt['status'], 'source': active_source,
            'hr_optical': opt['optical_hr'], 'hr_ok': int(opt['optical_hr_ok']),
            'tracked': int(opt['optical_tracked']), 'coverage': opt['segment_coverage'],
            'q_optical': opt['optical_quality'],
            'snr_db': opt['cardiac_snr'], 'rr_optical': opt['optical_rr'],
            'hr_acoustic': aco['hr'], 'rho_acoustic': aco['rho'], 'rmssd_ms': aco['rmssd'],
            'hr_fused': fused['hr'], 'fusion_source': fused['source'], 'w_o': fused['w_o'],
            'w_a': fused['w_a'], 'disagreement': int(fused['disagreement']),
            'spo2_ratio': opt['spo2_ratio'], 'spo2_estimate': opt['spo2_estimate'],
            'hr_display': self.latest['hr'], 'rr_display': self.latest['rr'],
            'hr_card': hr_card['value'], 'hr_card_state': hr_card['state'],
            'demo_mode': int(demo.enabled),
        })
        return True


aggregator = VitalsAggregator()


# ---------------------------------------------------------------- frame handling
def handle_frame(bgr, t, seq, source, jpeg_bytes=None):
    """Run the optical engine on one frame and publish the results."""
    global current_frame, optical_snapshot, active_source, last_frame_host_time
    last_frame_host_time = time.time()
    with state_lock:
        rebooted = bool(frame_times) and t < frame_times[-1] - 1.0     # node clock restarted
        if source != active_source or rebooted:
            engine.reset()                     # never mix two clocks in one buffer
            frame_times.clear()
            if deep:
                deep.reset()
            active_source = source
            if rebooted:
                device['node_reboots'] = device.get('node_reboots', 0) + 1
                print('[node] clock restarted (node rebooted); buffers reset', flush=True)
        annotated, record = engine.process_frame(bgr, t)
        rois = engine.current_rois
        if deep:
            deep.add_frame(bgr, t, engine.last_face_rect, record.get('gated'))
        frame_times.append(t)
        while frame_times and frame_times[-1] - frame_times[0] > 10.0:
            frame_times.pop(0)
        optical_snapshot = engine.telemetry()
    if source == 'ESP32_S3_CAM':
        send_roi(rois)
    recorder.log_frame(t, seq, source, record, jpeg_bytes)
    _, enc = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 75])
    current_frame = enc.tobytes()


def measured_frame_rate():
    if len(frame_times) < 3:
        return None, None
    d = np.diff(frame_times)
    return float(1.0 / np.mean(d)), float(1000.0 * np.std(d))


# ---------------------------------------------------------------- serial link
WIFI_HOSTS = [h.strip() for h in os.environ.get('SONICVITALS_HOSTS', 'sonicvitals.local,192.168.4.1').split(',') if h.strip()]
TCP_PORT = 3333


class TcpLink:
    """Minimal serial-like wrapper around the node's TCP stream (Wi-Fi firmware)."""

    def __init__(self, host, port, timeout=0.5):
        self.sock = socket.create_connection((host, port), timeout=1.5)
        self.sock.settimeout(timeout)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._buf = b''
        self.is_open = True

    def readline(self):
        while b'\n' not in self._buf:
            try:
                chunk = self.sock.recv(65536)
            except socket.timeout:
                return b''
            if not chunk:
                raise ConnectionError('node closed the connection')
            self._buf += chunk
        line, self._buf = self._buf.split(b'\n', 1)
        return line + b'\n'

    def write(self, data):
        self.sock.sendall(data)

    def close(self):
        self.is_open = False
        self.sock.close()


def local_ipv4():
    """This computer's address on the network used for the default route (no packets sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(('10.255.255.255', 1))
            return s.getsockname()[0]
    except OSError:
        return None


def scan_subnet_for_node(port=TCP_PORT, timeout=0.5):
    """Find Wi-Fi nodes on the local /24 by probing the TCP port. Phone hotspots often
    block mDNS, so `sonicvitals.local` cannot be relied on."""
    import concurrent.futures as cf
    ip = local_ipv4()
    if not ip:
        return []
    base = ip.rsplit('.', 1)[0]

    def probe(h):
        addr = f'{base}.{h}'
        if addr == ip:
            return None
        try:
            socket.create_connection((addr, port), timeout=timeout).close()
            return addr
        except OSError:
            return None

    with cf.ThreadPoolExecutor(64) as ex:
        return [a for a in ex.map(probe, range(1, 255)) if a]


LINK_MODE = os.environ.get('SONICVITALS_LINK', 'auto').lower()


def candidate_ports():
    if FIXED_PORT:
        return [FIXED_PORT]
    hosts = list(WIFI_HOSTS)
    if LINK_MODE != 'serial' and os.environ.get('SONICVITALS_SCAN', '1') != '0':
        hosts += [h for h in scan_subnet_for_node() if h not in hosts]
    tcp = [f'tcp://{h}:{TCP_PORT}' for h in hosts] if LINK_MODE != 'serial' else []
    if LINK_MODE == 'wifi':
        return tcp
    pats = ['/dev/cu.usbmodem*', '/dev/cu.wchusbserial*', '/dev/cu.usbserial*', '/dev/cu.SLAB*',
            '/dev/ttyACM*', '/dev/ttyUSB*']
    return tcp + [p for pat in pats for p in sorted(glob.glob(pat))]


def open_node(port):
    """Open `port` (serial device or tcp://host:port) and return it if a SonicVitals
    node is talking on it within 4 s."""
    if port.startswith('tcp://'):
        host, tport = port[6:].rsplit(':', 1)
        try:
            s = TcpLink(host, int(tport))
        except OSError:
            return None
    else:
        try:
            # Configure DTR/RTS before opening: on boards that wire them to EN/BOOT,
            # asserting them (pyserial's default on open) resets the chip, which
            # also breaks any firmware upload running at the same time.
            s = serial.Serial()
            s.port, s.baudrate, s.timeout = port, BAUD, 0.5
            s.dtr = False
            s.rts = False
            s.open()
        except Exception:
            return None
    try:
        s.setDTR(False)          # avoid resetting boards that wire DTR/RTS to EN/BOOT
        s.setRTS(False)
    except Exception:
        pass                     # not supported by every driver, by virtual ports, or by TCP
    deadline = time.time() + 4.0
    while time.time() < deadline:
        try:
            line = s.readline().decode('utf-8', errors='ignore')
        except Exception:
            break
        if line.startswith('<<HELLO:SonicVitals') or line.startswith('<<FRAME_START') or line.startswith('<<AUDIO:'):
            return s
    s.close()
    return None


def serial_reader():
    global ser_conn, last_node_frame_time
    while True:
        s = None
        for port in candidate_ports():
            s = open_node(port)
            if s:
                device.update(connected=True, port=port)
                break
        if not s:
            device['connected'] = False
            time.sleep(2.0)
            continue

        ser_conn = s
        parser = StreamParser()
        last_rx = time.time()
        try:
            while time.time() - last_rx < 8.0:
                raw = s.readline()
                if not raw:
                    continue
                last_rx = time.time()
                device['last_seen'] = last_rx
                for ev in parser.feed_line(raw.decode('utf-8', errors='ignore')):
                    kind = ev[0]
                    if kind == 'frame':
                        _, seq, t_us, jpeg = ev
                        bgr = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
                        if bgr is None:
                            continue
                        last_node_frame_time = time.time()
                        if camera_choice != 'node':
                            continue                   # the host webcam is the selected camera
                        t = t_us / 1e6 if t_us is not None else time.time()   # v1 firmware: host time
                        handle_frame(bgr, t, seq, 'ESP32_S3_CAM', len(jpeg))
                    elif kind == 'audio':
                        _, seq, t_us, pcm = ev
                        acoustic.add_block(seq, t_us, pcm)
                        recorder.log_audio(seq, t_us, pcm)
                    elif kind == 'rgb':
                        _, seq, t_us, n, rgb, nclip, ndark = ev
                        if camera_choice != 'node':
                            continue
                        used = False
                        if rgb is not None:
                            with state_lock:
                                used = engine.add_node_rgb(t_us / 1e6, rgb)
                        device['rgb_samples'] = device.get('rgb_samples', 0) + 1
                        exposure_ctl.add(n, rgb, nclip, ndark)
                        device['exposure_ctl'] = dict(exposure_ctl.state)
                        recorder.log_node_rgb(t_us / 1e6, seq, n, rgb, used, nclip, ndark, exposure_ctl.exposure)
                    elif kind == 'camexp':
                        exposure_readback(ev[1])
                    elif kind == 'info':
                        device['cam_info'] = ev[1]
                        fields = dict(kv.split('=', 1) for kv in ev[1].split(',') if '=' in kv)
                        if fields.get('exp', '-1').lstrip('-').isdigit() and int(fields['exp']) > 0:
                            exposure_readback(int(fields['exp']))
                    elif kind == 'stat':
                        device['stat'] = ev[1]
                    elif kind == 'hello':
                        device.update(firmware=f"{ev[1]['name']} v{ev[1]['version']}",
                                      transport=ev[1]['transport'], mic_enabled=ev[1]['mic_enabled'])
                        set_audio_rate(ev[1].get('fs', dsp.FS_AUDIO))
                device.update(frames_ok=parser.frames_ok, frames_bad=parser.frames_bad)
        except Exception as exc:
            print(f'[serial] link error on {device["port"]}: {exc}', flush=True)
        finally:
            try:
                s.close()
            except Exception:
                pass
            ser_conn = None
            device['connected'] = False
            time.sleep(1.0)


def set_audio_rate(fs):
    """Rebuild the acoustic engine if the node announces a different audio rate."""
    global acoustic
    fs = int(fs)
    if fs != acoustic.fs:
        acoustic = AcousticEngine(fs=fs)
        print(f'[audio] node streams at {fs} Hz', flush=True)
    device['audio_fs'] = fs


link_write_lock = threading.Lock()
_last_roi = {'msg': None, 't': 0.0}


def link_write(msg):
    s = ser_conn
    if not s or not s.is_open:
        return False
    try:
        with link_write_lock:
            s.write(msg.encode())
        return True
    except Exception:
        return False


def send_exposure(value):
    return link_write(f'<<CAM:EXP,{int(value)}>>\n')


exposure_ctl = ExposureController(send_exposure)


def exposure_readback(value):
    """The node confirmed a camera exposure; a change starts a new pulse segment."""
    if exposure_ctl.readback(value):
        with state_lock:
            engine.restart_signal()
        device['exposure_changes'] = device.get('exposure_changes', 0) + 1
        print(f'[camera] exposure -> {value} rows ({exposure_ctl.state.get("action")}); pulse segment restarted',
              flush=True)
    device['exposure_ctl'] = dict(exposure_ctl.state)


def send_roi(rois):
    """<<ROI:x,y,w,h;...>> tells the node which pixels to average before JPEG; <<ROI:none>> stops it."""
    msg = '<<ROI:none>>\n' if not rois else \
        '<<ROI:' + ';'.join(f'{int(x)},{int(y)},{int(w)},{int(h)}' for x, y, w, h in rois) + '>>\n'
    now = time.time()
    if msg == _last_roi['msg'] and now - _last_roi['t'] < 1.0:
        return
    if link_write(msg):
        _last_roi.update(msg=msg, t=now)


def send_downlink():
    """<<VITALS:HR,RR,SpO2,CONF,STATUS>> for the OLED; 0 means unavailable."""
    s = ser_conn
    if not s or not s.is_open:
        return
    v = aggregator.latest
    status = optical_snapshot.get('status', 'NO_PATIENT')
    if status in ('ALIGNING', 'REACQUIRING'):   # the OLED firmware knows STABLE / CALIBRATING / other
        status = 'CALIBRATING'
    msg = '<<VITALS:{},{},{},{},{}>>\n'.format(
        int(round((v.get('hr_card') or {}).get('value') or 0)),      # same heart rate as the dashboard card
        int(round(v.get('rr') or 0)), int(round(v.get('spo2') or 0)),
        int(round(v.get('quality') or 0)), status)
    link_write(msg)


def aggregator_loop():
    last_downlink = 0.0
    while True:
        aco = acoustic.update()
        with state_lock:
            opt = dict(optical_snapshot)
        aggregator.update(opt, aco)
        fps, sd = measured_frame_rate()
        device.update(host_fps=None if fps is None else round(fps, 2),
                      frame_interval_sd_ms=None if sd is None else round(sd, 1))
        if time.time() - last_downlink >= DOWNLINK_INTERVAL_S:
            last_downlink = time.time()
            send_downlink()
        time.sleep(0.25)


# ---------------------------------------------------------------- webcam fallback
CAMERA_STALL_S = 3.0
_stall_reported = {'value': False}


def check_camera_stalled():
    """No frames from the selected camera: say so on the video and clear the optical results,
    instead of showing the last frame and stale estimates."""
    global optical_snapshot
    stalled = time.time() - last_frame_host_time > CAMERA_STALL_S
    if stalled and not _stall_reported['value']:
        _stall_reported['value'] = True
        with state_lock:
            engine.reset()
            optical_snapshot = engine.telemetry()
        if camera_choice == 'node':
            show_message_frame('ESP32-S3 camera: no frames', 'Power the board / check Wi-Fi, or switch to the Mac webcam')
        else:
            show_message_frame('Mac webcam: no frames', 'Check camera permission, or switch to the ESP32-S3 camera')
    elif not stalled:
        _stall_reported['value'] = False


def show_message_frame(title, detail):
    """Replace the video with a plain message (instead of freezing on the last frame)."""
    global current_frame
    img = np.full((360, 640, 3), 18, np.uint8)
    cv2.putText(img, title, (24, 170), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (235, 235, 235), 2, cv2.LINE_AA)
    cv2.putText(img, detail, (24, 210), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (170, 170, 170), 1, cv2.LINE_AA)
    current_frame = cv2.imencode('.jpg', img)[1].tobytes()


WEBCAM_FPS = 30               # requested webcam rate (rPPG wants >= 20-30 fps; it was 15 before 2026-10-22)


class WebcamReader:
    """Reads the webcam on its own thread and timestamps every frame the moment it arrives.

    Reading and processing in one loop let frames wait in the camera buffer while the previous one was
    processed, so they were stamped late and unevenly (bad for pulse timing). The processing loop now
    takes the newest frame; if processing falls behind, older frames are skipped, never mis-timed."""

    def __init__(self, index=0):
        self.cap = cv2.VideoCapture(index)
        self.ok = self.cap.isOpened()
        self.lock = threading.Condition()
        self.frame = None
        self.t = None
        self.seq = 0
        self.capture_times = deque(maxlen=90)
        self.running = self.ok
        if self.ok:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.cap.set(cv2.CAP_PROP_FPS, WEBCAM_FPS)
            threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while self.running:
            ok, frame = self.cap.read()
            t = time.time()
            if not ok or frame is None:
                time.sleep(0.02)
                continue
            with self.lock:
                self.frame, self.t = frame, t
                self.seq += 1
                self.capture_times.append(t)
                self.lock.notify_all()

    def latest(self, last_seq, timeout=1.0):
        """Newest frame after last_seq: (frame, t, seq) or None on timeout."""
        with self.lock:
            if self.seq == last_seq:
                self.lock.wait(timeout)
            if self.seq == last_seq or self.frame is None:
                return None
            return self.frame, self.t, self.seq

    def capture_fps(self):
        with self.lock:
            c = list(self.capture_times)
        return None if len(c) < 5 else (len(c) - 1) / max(c[-1] - c[0], 1e-6)

    def release(self):
        self.running = False
        time.sleep(0.05)
        self.cap.release()


def webcam_worker():
    """Host webcam: used when chosen on the dashboard, or as a fallback without node frames
    (SONICVITALS_WEBCAM=1). Frames are tagged LOCAL_CAMERA everywhere."""
    reader, last_seq, proc = None, 0, deque(maxlen=60)
    while True:
        wanted = camera_choice == 'webcam' or (WEBCAM_FALLBACK and time.time() - last_node_frame_time >= 3.5)
        check_camera_stalled()
        if not wanted:
            if reader is not None:
                reader.release()
                reader = None
                device['webcam_status'] = 'closed'
            time.sleep(0.5)
            continue
        if reader is None:
            reader = WebcamReader(0)
            if not reader.ok:
                reader = None
                device['webcam_status'] = 'unavailable (no camera or no camera permission)'
                show_message_frame('Mac webcam unavailable', 'Allow camera access for the app running the server')
                time.sleep(1.0)
                continue
            device['webcam_status'] = 'open'
            last_seq = 0
        got = reader.latest(last_seq)
        if got is None:
            continue
        frame, t, seq = got
        device['webcam_skipped'] = device.get('webcam_skipped', 0) + max(0, seq - last_seq - 1)
        last_seq = seq
        t0 = time.perf_counter()
        handle_frame(cv2.flip(frame, 1), t, None, 'LOCAL_CAMERA')
        proc.append(1000 * (time.perf_counter() - t0))
        cfps = reader.capture_fps()
        device.update(webcam_capture_fps=None if cfps is None else round(cfps, 1),
                      process_ms=round(float(np.median(proc)), 1))


# ---------------------------------------------------------------- HTTP API
def generate_frames():
    try:
        while True:
            if current_frame is not None:
                yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + current_frame + b'\r\n'
            time.sleep(0.066)
    except (GeneratorExit, ConnectionResetError, BrokenPipeError):
        pass


@app.route('/video_feed')
def video_feed():
    res = Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')
    res.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return res


@app.route('/api/vitals')
def api_vitals():
    with state_lock:
        out = dict(optical_snapshot)
    out.update(aggregator.latest or {})
    # Demo values travel in their own field and never replace the measured spo2 / hrv fields.
    out['demo'] = dict(enabled=True, **demo.values()) if demo.enabled else dict(enabled=False)
    out.update(video_source=active_source, measured_fps=device['host_fps'],
               recording=recorder.active, timestamp=time.time())
    return jsonify(out)


@app.route('/api/methods')
def api_methods():
    """Every method's current heart rate, side by side: the same snapshot the heart-rate card was
    computed from (VitalsAggregator.update), so the table and the card always match."""
    with state_lock:
        o = dict(optical_snapshot)
    agg = aggregator.latest or {}
    rows = agg.get('method_rows') or []
    vals = [r['hr'] for r in rows if r['hr'] is not None]
    return jsonify(methods=rows, consensus_detail=agg.get('hr_consensus'), card=agg.get('hr_card'),
                   spread=None if len(vals) < 2 else round(max(vals) - min(vals), 1),
                   median=None if not vals else round(float(np.median(vals)), 1),
                   deep_status=agg.get('deep_status', 'starting'), video_source=active_source,
                   snr=o.get('cardiac_snr'), consensus=o.get('optical_consensus'), bg_rejected=o.get('bg_rejected_bpm'))


@app.route('/api/audio')
def api_audio():
    payload = acoustic.display_payload()
    payload.update(acoustic.result)
    payload['simulated'] = False
    if demo.enabled and acoustic.result.get('hr') is None:
        # Demo only, labelled SIMULATED in the UI: a normal heart-sound pattern at the card's heart rate,
        # shown while the real microphone has no rhythm (rho < 0.4). The real result fields are kept.
        card_hr = ((aggregator.latest or {}).get('hr_card') or {}).get('value')
        sim = acoustic.display_payload(x=heart_sound_pattern(card_hr, 4.0, acoustic.fs))
        payload.update(wave=sim['wave'], spec=sim['spec'], spec_freqs=sim['spec_freqs'],
                       wave_seconds=sim['wave_seconds'], spec_seconds=sim['spec_seconds'], simulated=True,
                       simulated_hr=card_hr or 72.0)
    return jsonify(payload)


@app.route('/api/perfusion_map.jpg')
def api_perfusion_map():
    """Face with the blood-flow (perfusion) map over the skin cells that pulse (face_insights.py)."""
    jpeg = engine.insights.map_jpeg()
    if jpeg is None:
        return Response(status=204)
    return Response(jpeg, mimetype='image/jpeg', headers={'Cache-Control': 'no-store'})


@app.route('/api/perfusion/capture', methods=['GET', 'POST'])
def api_perfusion_capture():
    """POST starts a 20 s blood-flow map capture (restarts on movement); GET returns its status."""
    if request.method == 'POST':
        engine.insights.start_capture()
    return jsonify(engine.insights.capture_status())


@app.route('/api/insights_live')
def api_insights_live():
    """Real-time traces: eye openness with blinks, breathing movement with breaths (face_insights.py)."""
    with state_lock:
        return jsonify(engine.live_traces())


@app.route('/api/demo', methods=['GET', 'POST'])
def api_demo():
    """Labelled demo mode switch: {"enabled": true|false}."""
    if request.method == 'POST':
        demo.set((request.get_json(silent=True) or {}).get('enabled', False))
        print(f'[demo] labelled demo mode {"ON" if demo.enabled else "OFF"}', flush=True)
    return jsonify(enabled=demo.enabled)


@app.route('/api/device')
def api_device():
    d = dict(device)
    d['age_s'] = round(time.time() - d['last_seen'], 1) if d['last_seen'] else None
    c = dict(exposure_ctl.state)
    if time.time() - c.get('metered_at', 0) > 3.0:           # no skin boxes metered recently
        c.update(level=None, clip=None, dark=None, action='waiting')
    d['exposure_ctl'] = c
    d['video_source'] = active_source
    d['audio_blocks_received'] = acoustic.blocks_received
    d['audio_blocks_lost'] = acoustic.blocks_lost
    d['webcam_fallback_enabled'] = WEBCAM_FALLBACK
    d['camera_choice'] = camera_choice
    return jsonify(d)


@app.route('/api/camera', methods=['GET', 'POST'])
def api_camera():
    """Select the camera: {"camera": "node"} (ESP32-S3) or {"camera": "webcam"} (host), or toggle with {}."""
    global camera_choice
    if request.method == 'POST':
        body = request.get_json(silent=True) or {}
        new = body.get('camera') or ('webcam' if camera_choice == 'node' else 'node')
        if new not in ('node', 'webcam'):
            return jsonify(error='camera must be "node" or "webcam"'), 400
        if new != camera_choice:
            camera_choice = new
            if new == 'webcam':
                send_roi(None)                 # stop the node summing skin boxes
            print(f'[camera] source -> {"host webcam" if new == "webcam" else "ESP32-S3 camera"}', flush=True)
    return jsonify(camera=camera_choice, video_source=active_source)


@app.route('/api/config')
def api_config():
    return jsonify({
        'optical': {'analysis_fs_hz': dsp.FS_OPT, 'method': 'CHROM (de Haan & Jeanne 2013)',
                    'cardiac_band_hz': dsp.CARDIAC_BAND, 'cardiac_filter': '3rd-order Butterworth, zero-phase',
                    'resp_band_hz': dsp.RESP_BAND, 'resp_filter': '2nd-order Butterworth, zero-phase, green channel',
                    'welch_nperseg_hr': 256, 'nfft': dsp.NFFT, 'min_segment_hr_s': dsp.MIN_SEG_HR_S,
                    'min_segment_rr_s': dsp.MIN_SEG_RR_S, 'max_gap_s': dsp.MAX_GAP_S},
        'acoustic': {'fs_hz': acoustic.fs, 'pcg_band_hz': dsp.PCG_BAND, 'analysis_fs_hz': dsp.FS_PCG,
                     'hr_lag_s': dsp.HR_LAG_S, 'window_s': 10},
        'fusion': {'agreement_delta_bpm': dsp.FUSION_DELTA_BPM},
        'display': {'interval_s': DISPLAY_INTERVAL_S, 'ema_hr_rr': EMA_HR_RR, 'ema_spo2': EMA_SPO2},
        'spo2_calibrated': engine.spo2_calibration is not None,
        'webcam_fallback_enabled': WEBCAM_FALLBACK,
        'serial_baud': BAUD,
        'data_dir': DATA_DIR,
    })


@app.route('/api/capture_diagnostic', methods=['GET', 'POST'])
def api_capture_diagnostic():
    with state_lock:
        diag = engine.analyze_diagnostic_snapshot(use_best_moment=True)
    diag['video_source'] = active_source
    return jsonify(diag)


@app.route('/api/best_moment_status')
def api_best_moment_status():
    with state_lock:
        bm = engine.best_moment
        return jsonify({
            'has_moment': bm['frame'] is not None and bm.get('full_face_visible', False),
            'sharpness': round(bm['sharpness'], 1),
            'cardiac_phase': 'SHARPEST_IN_WINDOW',
            'timestamp': bm['timestamp'],
            'full_face_visible': engine.full_face_visible,
            'face_alignment_status': engine.face_alignment_status,
            'face_guidance': engine.face_guidance,
            'patient_detected': engine.patient_detected,
            'video_source': active_source,
        })


@app.route('/api/session/start', methods=['POST'])
def api_session_start():
    body = request.get_json(silent=True) or {}
    sid = recorder.start(participant=str(body.get('participant', '')), condition=str(body.get('condition', '')),
                         notes=str(body.get('notes', '')), video_source=active_source,
                         audio_fs=acoustic.fs)
    return jsonify({'recording': True, 'session_id': sid, 'dir': recorder.dir})


@app.route('/api/session/stop', methods=['POST'])
def api_session_stop():
    sid = recorder.stop()
    return jsonify({'recording': False, 'session_id': sid})


@app.route('/api/session/status')
def api_session_status():
    return jsonify({'recording': recorder.active, 'session_id': recorder.session_id})


@app.route('/')
def index():
    return render_template_string('''
        <html><head><title>SonicVitals Live Feed</title></head>
        <body style="background:#111;text-align:center;color:white;padding-top:50px;font-family:sans-serif;">
          <h1>SonicVitals live stream</h1>
          <img src="/video_feed" style="border:2px solid #00f0ff;max-width:640px;width:100%;" />
          <p>API: <a href="/api/vitals" style="color:#00f0ff;">/api/vitals</a> |
             <a href="/api/device" style="color:#00f0ff;">/api/device</a> |
             <a href="/api/config" style="color:#00f0ff;">/api/config</a></p>
        </body></html>''')


if __name__ == '__main__':
    threading.Thread(target=serial_reader, daemon=True).start()
    threading.Thread(target=aggregator_loop, daemon=True).start()
    threading.Thread(target=webcam_worker, daemon=True).start()   # idle unless the webcam is chosen / fallback
    print('SonicVitals server on http://localhost:5001/  '
          f'(webcam fallback {"ON" if WEBCAM_FALLBACK else "OFF"}, data -> {DATA_DIR})', flush=True)
    app.run(host='127.0.0.1', port=5001, threaded=True)
