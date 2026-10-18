import serial
import time
import base64
import glob
import cv2
import numpy as np
from flask import Flask, Response, jsonify, render_template_string
from flask_cors import CORS
import threading
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from rppg_engine import RPPGEngine

app = Flask(__name__)
CORS(app)

current_frame = None
latest_telemetry = {
    'patient_detected': False,
    'full_face_visible': False,
    'face_alignment_status': 'SEARCHING',
    'face_guidance': 'Aligning camera with patient...',
    'status': 'NO_PATIENT',
    'calibrating': False,
    'calibration_progress': 0,
    'calibration_remaining_sec': 6,
    'hr': None,
    'rr': None,
    'hrv': None,
    'spo2': None,
    'quality': None,
    'confidence': None,
    'stress': None,
    'bvp_sample': 0.0,
    'resp_sample': 0.0,
    'fusion_hr': None,
    'cardiac_peak_freq': 0.0,
    'cardiac_snr': 0.0,
    'psd_freqs': [],
    'psd_power': [],
    'bvp_wave': [],
    'resp_wave': [],
    'wavelet_a3': [],
    'wavelet_d2': [],
    'wavelet_d1': [],
    'wavelet_energy_ratio': 0.0,
    'video_source': 'INITIALIZING',
    'timestamp': time.time(),
    'best_moment_sharpness': 0.0,
    'best_moment_ready': False
}

engine = RPPGEngine(fps=15.0, calib_seconds=6.0)
ser_conn = None
last_esp32_frame_time = 0.0
active_source = 'SEARCHING'

def webcam_worker():
    global current_frame, latest_telemetry, active_source
    cap = None
    while True:
        now = time.time()
        # If ESP32 camera has streamed within the last 3.5s, yield to ESP32!
        if (now - last_esp32_frame_time) < 3.5:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass
                cap = None
            time.sleep(0.5)
            continue
        
        # Engage local camera fallback
        if cap is None or not cap.isOpened():
            try:
                cap = cv2.VideoCapture(0)
                if not cap.isOpened():
                    time.sleep(1.0)
                    continue
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                cap.set(cv2.CAP_PROP_FPS, 15)
            except Exception:
                time.sleep(1.0)
                continue
        
        ret, frame = cap.read()
        if not ret or frame is None:
            time.sleep(0.066)
            continue
        
        # Mirror for clinical workstation self-view
        frame = cv2.flip(frame, 1)
        
        annotated, telem = engine.process_frame(frame)
        telem['timestamp'] = now
        telem['video_source'] = 'LOCAL_CAMERA'
        latest_telemetry = telem
        active_source = 'LOCAL_CAMERA'
        
        _, enc_jpg = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 75])
        current_frame = enc_jpg.tobytes()
        
        time.sleep(0.066)

def serial_reader():
    global current_frame, latest_telemetry, ser_conn, last_esp32_frame_time, active_source
    in_frame = False
    frame_data = []
    last_oled_sync = time.time()

    while True:
        ports = glob.glob('/dev/cu.usbserial*') + glob.glob('/dev/cu.wch*') + glob.glob('/dev/cu.SLAB*') + glob.glob('/dev/cu.usbmodem*')
        if not ports:
            time.sleep(2.0)
            continue
        
        port = ports[0]
        s = None
        try:
            s = serial.Serial(port, 460800, timeout=1)
            s.setDTR(False)
            s.setRTS(False)
            ser_conn = s
            in_frame = False
            frame_data = []
            conn_start_time = time.time()
            got_any_frame = False
        except Exception:
            if s:
                try:
                    s.close()
                except Exception:
                    pass
            ser_conn = None
            time.sleep(2.0)
            continue

        try:
            while True:
                now = time.time()
                # Check for non-camera device (e.g., CP2102 from other projects)
                if not got_any_frame and (now - conn_start_time > 4.0):
                    break
                if got_any_frame and (now - last_esp32_frame_time > 8.0):
                    break

                line = s.readline()
                if not line:
                    continue

                try:
                    text = line.decode('utf-8', errors='ignore').strip()
                except Exception:
                    continue

                if text == '<<FRAME_START>>':
                    in_frame = True
                    frame_data = []
                elif text == '<<FRAME_END>>':
                    in_frame = False
                    try:
                        b64_str = ''.join(frame_data)
                        rem = len(b64_str) % 4
                        if rem == 1:
                            b64_str = b64_str[:-1]
                        elif rem > 1:
                            b64_str += '=' * (4 - rem)
                        
                        jpeg_bytes = base64.b64decode(b64_str)
                        if len(jpeg_bytes) >= 200 and jpeg_bytes.startswith(b'\xff\xd8'):
                            nparr = np.frombuffer(jpeg_bytes, np.uint8)
                            bgr_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                            if bgr_img is not None and bgr_img.size > 0:
                                annotated, telem = engine.process_frame(bgr_img)
                                telem['timestamp'] = now
                                telem['video_source'] = 'ESP32_S3_CAM'
                                latest_telemetry = telem
                                active_source = 'ESP32_S3_CAM'
                                got_any_frame = True
                                last_esp32_frame_time = now
                                
                                _, enc_jpg = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 75])
                                current_frame = enc_jpg.tobytes()
                    except Exception:
                        pass
                elif in_frame:
                    frame_data.append(text)
                    
                # Sync vitals back to ESP32 OLED display (every 1.5s)
                if now - last_oled_sync >= 1.5:
                    last_oled_sync = now
                    if s and s.is_open:
                        st = latest_telemetry.get('status', 'IDLE')
                        hr = int(latest_telemetry['hr']) if latest_telemetry.get('hr') else 0
                        rr = int(latest_telemetry['rr']) if latest_telemetry.get('rr') else 0
                        spo2 = int(latest_telemetry['spo2']) if latest_telemetry.get('spo2') else 0
                        msg = f'<<VITALS:{hr},{rr},{spo2},{st}>>\n'
                        try:
                            s.write(msg.encode())
                        except Exception:
                            pass
        except Exception:
            pass
        finally:
            try:
                if s:
                    s.close()
            except Exception:
                pass
            ser_conn = None
            time.sleep(3.0)

def generate_frames():
    try:
        while True:
            if current_frame is not None:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + current_frame + b'\r\n')
                time.sleep(0.066)
            else:
                time.sleep(0.05)
    except (GeneratorExit, ConnectionResetError, BrokenPipeError):
        pass
    except Exception:
        pass

@app.route('/video_feed')
def video_feed():
    res = Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')
    res.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    res.headers['Pragma'] = 'no-cache'
    res.headers['Expires'] = '0'
    return res

@app.route('/api/vitals')
def api_vitals():
    return jsonify(latest_telemetry)

@app.route('/api/capture_diagnostic', methods=['GET', 'POST'])
def api_capture_diagnostic():
    diag = engine.analyze_diagnostic_snapshot(use_best_moment=True)
    return jsonify(diag)

@app.route('/api/best_moment_status')
def api_best_moment_status():
    bm = engine.best_moment
    return jsonify({
        'has_moment': bm['frame'] is not None and bm.get('full_face_visible', False),
        'sharpness': round(bm['sharpness'], 1),
        'cardiac_phase': bm['cardiac_phase'],
        'timestamp': bm['timestamp'],
        'full_face_visible': engine.full_face_visible,
        'face_alignment_status': engine.face_alignment_status,
        'face_guidance': engine.face_guidance,
        'patient_detected': engine.patient_detected,
        'video_source': active_source
    })

@app.route('/')
def index():
    return render_template_string('''
        <html>
            <head><title>SonicVitals Live Feed</title></head>
            <body style="background-color: #111; text-align: center; color: white; padding-top: 50px; font-family: sans-serif;">
                <h1>SonicVitals Live Physiological Stream</h1>
                <img src="/video_feed" style="border: 2px solid #00f0ff; box-shadow: 0 0 20px #00f0ff; border-radius: 10px; max-width: 640px; width: 100%;" />
                <div style="margin-top: 20px;">
                    <p>API Endpoint: <a href="/api/vitals" style="color: #00f0ff;">/api/vitals</a></p>
                </div>
            </body>
        </html>
    ''')

if __name__ == '__main__':
    t_serial = threading.Thread(target=serial_reader, daemon=True)
    t_serial.start()
    t_webcam = threading.Thread(target=webcam_worker, daemon=True)
    t_webcam.start()
    print('Starting SonicVitals Clinical Video & Vitals server on http://localhost:5001/', flush=True)
    app.run(host='0.0.0.0', port=5001, threaded=True)
