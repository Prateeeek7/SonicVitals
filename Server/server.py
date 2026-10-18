import socket
import struct
import threading
import time
import numpy as np
import cv2
import wave
import os
from collections import deque

class DataReceiver:
    def __init__(self, host="0.0.0.0", port=50005, max_buffer_size=100, video_file_path=None, audio_file_path=None):
        self.host = host
        self.port = port
        self.running = False
        
        # Offline emulation files
        self.video_file_path = video_file_path
        self.audio_file_path = audio_file_path
        
        # Thread-safe storage queues
        self.video_queue = deque(maxlen=max_buffer_size)
        self.audio_queue = deque(maxlen=max_buffer_size * 2)
        
        self.lock = threading.Lock()
        self.socket_thread = None
        
        # Telemetry metrics
        self.fps = 0.0
        self.packet_count = 0
        self.lost_packets = 0
        self.latency_ms = 0.0
        self.connected = False
        
        # Video frame reassembly variables
        self.frame_buffer = {} # Maps timestamp to [bytes, chunks_received, total_len]
        
    def start(self):
        self.running = True
        if self.video_file_path is not None:
            # Start in Offline Clinical Emulation Mode
            self.socket_thread = threading.Thread(target=self._offline_emulator_loop, daemon=True)
            self.socket_thread.start()
            print(f"UDP Receiver running in OFFLINE EMULATION MODE. Video: {self.video_file_path}")
        else:
            # Start in Real-time Live Network Mode
            self.socket_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self.socket_thread.start()
            print(f"UDP Socket Server started on {self.host}:{self.port}")
        
    def stop(self):
        self.running = False
        if self.socket_thread:
            self.socket_thread.join()
        print("UDP Receiver stopped.")

    def _receive_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((self.host, self.port))
        sock.settimeout(1.0) # 1 second timeout to check running flag

        header_format = "=IBIQQ" # magic (4B), type (1B), seq (4B), timestamp (8B), len (4B)
        header_size = struct.calcsize(header_format)
        
        last_frame_count_time = time.time()
        frames_this_second = 0
        last_seq = -1

        while self.running:
            try:
                data, addr = sock.recvfrom(65535)
                self.connected = True
                
                if len(data) < header_size:
                    continue
                
                magic, data_type, seq, timestamp_us, payload_len = struct.unpack(
                    header_format, data[:header_size]
                )
                
                if magic != 0x53564e44:
                    continue
                
                if last_seq != -1 and seq > last_seq + 1:
                    self.lost_packets += (seq - last_seq - 1)
                last_seq = seq
                
                self.packet_count += 1
                
                payload = data[header_size:]
                if len(payload) != payload_len:
                    continue
                
                current_time_us = int(time.time() * 1e6)
                self.latency_ms = (current_time_us - timestamp_us) / 1000.0
                
                if data_type == 1:
                    self._process_video_chunk(timestamp_us, payload, payload_len)
                    frames_this_second += 1
                elif data_type == 2:
                    self._process_audio_packet(timestamp_us, payload)
                
                now = time.time()
                if now - last_frame_count_time >= 1.0:
                    self.fps = (frames_this_second / 10.0) / (now - last_frame_count_time)
                    frames_this_second = 0
                    last_frame_count_time = now
                    
            except socket.timeout:
                self.connected = False
                self.fps = 0.0
            except Exception as e:
                print(f"Error in receiver loop: {e}")
                
        sock.close()

    def _offline_emulator_loop(self):
        """
        Emulates an ESP32-S3 node by reading from standard video and audio files,
        packetizing them at the correct frame rate, and feeding them to queues.
        """
        cap = cv2.VideoCapture(self.video_file_path)
        if not cap.isOpened():
            print(f"Error: Unable to open emulation video file {self.video_file_path}")
            self.running = False
            return

        video_fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
        frame_delay = 1.0 / video_fps
        
        # Audio WAV reader
        wav_file = None
        wav_channels = 1
        wav_sampwidth = 2
        wav_framerate = 16000
        
        if self.audio_file_path and os.path.exists(self.audio_file_path):
            try:
                wav_file = wave.open(self.audio_file_path, 'rb')
                wav_channels = wav_file.getnchannels()
                wav_sampwidth = wav_file.getsampwidth()
                wav_framerate = wav_file.getframerate()
                print(f"Emulating audio file: {self.audio_file_path} | {wav_framerate}Hz | {wav_channels}ch")
            except Exception as e:
                print(f"Error opening wav file: {e}")
                wav_file = None

        self.connected = True
        self.fps = video_fps
        
        audio_chunk_samples = 128 # ESP32 sends 128 samples per packet
        # Calculate how many audio samples correspond to one video frame
        samples_per_frame = int(wav_framerate * frame_delay)
        chunks_per_frame = max(1, int(samples_per_frame / audio_chunk_samples))

        while self.running:
            start_time = time.time()
            
            # 1. Read Video Frame
            ret, frame = cap.read()
            if not ret:
                # Loop video
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                if wav_file:
                    wav_file.setpos(0)
                continue
                
            ts_us = int(time.time() * 1e6)
            
            # Push frame to video queue
            with self.lock:
                self.video_queue.append((ts_us, frame))
                self.packet_count += 1
                
            # 2. Read and push synchronized Audio Chunks for this frame interval
            for _ in range(chunks_per_frame):
                if wav_file:
                    raw_frames = wav_file.readframes(audio_chunk_samples)
                    if len(raw_frames) == 0:
                        break # End of audio
                    
                    # Convert raw bytes based on sample width
                    if wav_sampwidth == 2: # 16-bit PCM
                        samples = np.frombuffer(raw_frames, dtype=np.int16).copy()
                        normalized = samples.astype(np.float32) / 32768.0
                    elif wav_sampwidth == 4: # 32-bit PCM
                        samples = np.frombuffer(raw_frames, dtype=np.int32).copy()
                        normalized = samples.astype(np.float32) / 2147483648.0
                    else: # 8-bit unsigned
                        samples = np.frombuffer(raw_frames, dtype=np.uint8).copy()
                        normalized = (samples.astype(np.float32) - 128.0) / 128.0
                        
                    # If stereo, select left channel
                    if wav_channels > 1 and len(normalized) > 0:
                        normalized = normalized[::wav_channels]
                else:
                    # Synthesize acoustic breathing envelope if no file is provided
                    t_sec = time.time()
                    respFreq = 0.266
                    env = Math_Breath_Envelope(t_sec, respFreq)
                    normalized = (env * np.sin(2 * np.pi * 180 * np.linspace(0, 0.008, audio_chunk_samples)) + 
                                  (np.random.rand(audio_chunk_samples) - 0.5) * 0.1)
                
                with self.lock:
                    self.audio_queue.append((ts_us, normalized.astype(np.float32)))
                    self.packet_count += 1

            # Throttle loop to match actual video frame delay
            elapsed = time.time() - start_time
            sleep_time = frame_delay - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        cap.release()
        if wav_file:
            wav_file.close()

    def _process_video_chunk(self, timestamp, payload, payload_len):
        if len(payload) < 8:
            return
        
        offset, total_len = struct.unpack("=II", payload[:8])
        chunk_data = payload[8:]
        
        with self.lock:
            if timestamp not in self.frame_buffer:
                self.frame_buffer[timestamp] = [bytearray(total_len), 0, total_len, time.time()]
            
            buf_info = self.frame_buffer[timestamp]
            
            if offset + len(chunk_data) <= buf_info[2]:
                buf_info[0][offset : offset + len(chunk_data)] = chunk_data
                buf_info[1] += len(chunk_data)
            
            if buf_info[1] == buf_info[2]:
                frame_bytes = np.frombuffer(buf_info[0], dtype=np.uint8)
                img = cv2.imdecode(frame_bytes, cv2.IMREAD_COLOR)
                if img is not None:
                    self.video_queue.append((timestamp, img))
                del self.frame_buffer[timestamp]
                
            now = time.time()
            stale_keys = [k for k, v in self.frame_buffer.items() if now - v[3] > 2.0]
            for k in stale_keys:
                del self.frame_buffer[k]

    def _process_audio_packet(self, timestamp, payload):
        samples = np.frombuffer(payload, dtype=np.int32).copy()
        normalized_samples = samples.astype(np.float32) / 2147483648.0
        with self.lock:
            self.audio_queue.append((timestamp, normalized_samples))

    def get_latest_video(self):
        with self.lock:
            if len(self.video_queue) > 0:
                return self.video_queue.pop()
        return None, None

    def get_audio_chunk(self):
        with self.lock:
            if len(self.audio_queue) > 0:
                return self.audio_queue.popleft()
        return None, None

    def get_telemetry(self):
        return {
            "fps": round(self.fps, 1),
            "packets_received": self.packet_count,
            "lost_packets": self.lost_packets,
            "latency_ms": round(self.latency_ms, 1),
            "connected": self.connected
        }

def Math_Breath_Envelope(t_sec, respFreq):
    return max(0.0, np.sin(2 * np.pi * respFreq * t_sec))

if __name__ == "__main__":
    receiver = DataReceiver()
    receiver.start()
    try:
        while True:
            time.sleep(1)
            tel = receiver.get_telemetry()
            print(f"Status: Connected={tel['connected']} | FPS={tel['fps']} | Latency={tel['latency_ms']}ms | Lost Packets={tel['lost_packets']}")
    except KeyboardInterrupt:
        receiver.stop()
