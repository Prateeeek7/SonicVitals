import cv2
import numpy as np
import mediapipe as mp
from scipy.signal import butter, filtfilt, welch

class VisualDSP:
    def __init__(self, fps=15.0):
        self.fps = fps
        
        # Initialize MediaPipe Face Mesh
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.6,
            min_tracking_confidence=0.6
        )
        
        # Buffer to store raw RGB average trace values: size (N, 3)
        self.buffer_size = 150 # ~10 seconds at 15 FPS
        self.rgb_trace_buffer = [] # Elements are [R, G, B]
        self.timestamps = []
        
        # Butterworth Filter Parameters (0.7 Hz to 3.0 Hz / 42 to 180 BPM)
        self.b, self.a = butter(4, [0.7 / (self.fps / 2.0), 3.0 / (self.fps / 2.0)], btype='band')
        
    def process_frame(self, frame, timestamp):
        """Processes an image frame, extracts average RGB trace, and tracks face mesh."""
        h, w, _ = frame.shape
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(rgb_frame)
        
        rgb_val = [0.0, 0.0, 0.0]
        landmarks_points = []
        
        if results.multi_face_landmarks:
            landmarks = results.multi_face_landmarks[0].landmark
            
            for lm in landmarks:
                landmarks_points.append((int(lm.x * w), int(lm.y * h)))
                
            # Forensic ROI coordinates mapping:
            # Forehead: Landmarks 10, 338, 9, 109
            # Left Cheek: Landmarks 118, 50, 101, 117
            # Right Cheek: Landmarks 347, 280, 330, 346
            
            forehead_pts = np.array([
                [landmarks[10].x * w, landmarks[10].y * h],
                [landmarks[338].x * w, landmarks[338].y * h],
                [landmarks[9].x * w, landmarks[9].y * h],
                [landmarks[109].x * w, landmarks[109].y * h]
            ], dtype=np.int32)
            
            left_cheek_pts = np.array([
                [landmarks[118].x * w, landmarks[118].y * h],
                [landmarks[50].x * w, landmarks[50].y * h],
                [landmarks[101].x * w, landmarks[101].y * h],
                [landmarks[117].x * w, landmarks[117].y * h]
            ], dtype=np.int32)

            right_cheek_pts = np.array([
                [landmarks[347].x * w, landmarks[347].y * h],
                [landmarks[280].x * w, landmarks[280].y * h],
                [landmarks[330].x * w, landmarks[330].y * h],
                [landmarks[346].x * w, landmarks[346].y * h]
            ], dtype=np.int32)
            
            # Extract RGB channel averages (OpenCV uses BGR)
            fh_bgr = self._get_roi_average_bgr(frame, forehead_pts)
            lc_bgr = self._get_roi_average_bgr(frame, left_cheek_pts)
            rc_bgr = self._get_roi_average_bgr(frame, right_cheek_pts)
            
            # Mean BGR values of skin regions
            mean_b = (fh_bgr[0] + lc_bgr[0] + rc_bgr[0]) / 3.0
            mean_g = (fh_bgr[1] + lc_bgr[1] + rc_bgr[1]) / 3.0
            mean_r = (fh_bgr[2] + lc_bgr[2] + rc_bgr[2]) / 3.0
            
            rgb_val = [mean_r, mean_g, mean_b]
            
            if mean_g > 0:
                self.rgb_trace_buffer.append(rgb_val)
                self.timestamps.append(timestamp)
                if len(self.rgb_trace_buffer) > self.buffer_size:
                    self.rgb_trace_buffer.pop(0)
                    self.timestamps.pop(0)
                    
        return landmarks_points, rgb_val[1] > 0

    def _get_roi_average_bgr(self, frame, points):
        mask = np.zeros(frame.shape[:2], dtype=np.uint8)
        cv2.fillPoly(mask, [points], 255)
        mean_val = cv2.mean(frame, mask=mask)
        return [mean_val[0], mean_val[1], mean_val[2]] # B, G, R

    def get_pos_rppg(self):
        """
        Applies mathematical POS (Plane-Orthogonal-to-Skin) projection (Wang et al. 2017).
        Computes sliding projection windows to isolate blood volume pulses from motion artifacts.
        """
        if len(self.rgb_trace_buffer) < 45:
            return np.array([])
            
        C = np.array(self.rgb_trace_buffer) # Shape (N, 3) where columns are R, G, B
        N = C.shape[0]
        H = np.zeros(N)
        
        # Window size L (typically 30 frames representing ~2 seconds at 15 FPS)
        L = 30
        
        # Sliding overlap projection accumulator
        for i in range(0, N - L + 1):
            C_sub = C[i : i + L, :]
            
            # Mean normalization vector
            mean_color = np.mean(C_sub, axis=0)
            C_n = C_sub / (mean_color + 1e-6) - 1.0
            
            # Compute projection directions orthogonal to average skin tone
            S1 = 3.0 * C_n[:, 0] - 2.0 * C_n[:, 1] # 3R - 2G
            S2 = 1.5 * C_n[:, 0] + C_n[:, 1] - 1.5 * C_n[:, 2] # 1.5R + G - 1.5B
            
            # Combine based on standard deviation ratios
            std1 = np.std(S1)
            std2 = np.std(S2)
            alpha = std1 / (std2 + 1e-6)
            
            h = S1 - alpha * S2
            
            # Overlap add to final signal
            H[i : i + L] += (h - np.mean(h))
            
        return H

    def get_chrom_rppg(self):
        """
        Applies CHROM (Chrominance-based rPPG) algorithm (de Haan et al. 2013).
        Uses standardized skin difference projections to recover cardiac pulses.
        """
        if len(self.rgb_trace_buffer) < 45:
            return np.array([])
            
        C = np.array(self.rgb_trace_buffer)
        
        # Calculate moving averages to detrend channels
        window = 15
        C_smooth = np.zeros_like(C)
        for ch in range(3):
            C_smooth[:, ch] = np.convolve(C[:, ch], np.ones(window)/window, mode='same')
            
        # Normalization
        C_n = C / (C_smooth + 1e-6)
        
        # Chrominance transformations
        X = 3 * C_n[:, 0] - 2 * C_n[:, 1] # 3R - 2G
        Y = 1.5 * C_n[:, 0] + C_n[:, 1] - 1.5 * C_n[:, 2] # 1.5R + G - 1.5B
        
        # Bandpass filter the independent projections
        try:
            X_f = filtfilt(self.b, self.a, X)
            Y_f = filtfilt(self.b, self.a, Y)
            
            alpha = np.std(X_f) / (np.std(Y_f) + 1e-6)
            S = X_f - alpha * Y_f
            return S
        except:
            return X - Y

    def get_filtered_rppg(self, algo="POS"):
        """Returns normalized and bandpass filtered rPPG signal using the selected algorithm."""
        if algo == "POS":
            raw_ppg = self.get_pos_rppg()
        else:
            raw_ppg = self.get_chrom_rppg()
            
        if raw_ppg.size == 0:
            return np.array([])
            
        # Bandpass filter the extracted signal
        try:
            filtered = filtfilt(self.b, self.a, raw_ppg)
            # Normalize for GUI drawing
            normalized = (filtered - np.mean(filtered)) / max(np.std(filtered), 1e-6)
            return normalized
        except:
            return raw_ppg

    def estimate_heart_rate(self, algo="POS"):
        """Computes power spectral density of rPPG using FFT and returns peak HR."""
        rppg = self.get_filtered_rppg(algo)
        if rppg.size == 0:
            return 0.0, 0.0
            
        fs = self.fps
        frequencies, psd = welch(rppg, fs=fs, nperseg=min(len(rppg), 128))
        
        valid_idx = np.where((frequencies >= 0.7) & (frequencies <= 3.0))[0]
        if len(valid_idx) == 0:
            return 0.0, 0.0
            
        peak_idx = valid_idx[np.argmax(psd[valid_idx])]
        peak_freq = frequencies[peak_idx]
        hr_bpm = peak_freq * 60.0
        
        # Calculate Signal-to-Noise Ratio (SNR) of cardiac peak
        signal_power = psd[peak_idx]
        noise_power = np.sum(psd[valid_idx]) - signal_power
        snr = 10 * np.log10(signal_power / max(noise_power, 1e-6))
        
        return hr_bpm, snr


class AcousticDSP:
    def __init__(self, sample_rate=16000):
        self.sample_rate = sample_rate
        
        # Buffer stores 10 seconds of raw normalized audio
        self.buffer_size = self.sample_rate * 10
        self.audio_buffer = deque(maxlen=self.buffer_size)
        
        # Pre-emphasis coefficient
        self.pre_emphasis_coeff = 0.97
        
    def add_samples(self, samples):
        self.audio_buffer.extend(samples)
        
    def get_spectrogram(self):
        """Computes a Short-Time Fourier Transform (STFT) spectrogram for live visualization."""
        if len(self.audio_buffer) < 1024:
            return np.zeros((128, 128))
            
        samples = np.array(self.audio_buffer)
        window_samples = samples[-self.sample_rate:]
        
        # Pre-emphasis high-pass filter
        window_samples = np.append(window_samples[0], window_samples[1:] - self.pre_emphasis_coeff * window_samples[:-1])
        
        nfft = 512
        noverlap = 256
        hop_size = nfft - noverlap
        
        spectrogram_data = []
        for i in range(0, len(window_samples) - nfft, hop_size):
            segment = window_samples[i:i+nfft]
            windowed = segment * np.hanning(nfft)
            spectrum = np.abs(np.fft.rfft(windowed))
            spectrogram_data.append(spectrum[:128])
            
        if len(spectrogram_data) == 0:
            return np.zeros((128, 128))
            
        spec_matrix = np.column_stack(spectrogram_data)
        log_spec = 20 * np.log10(spec_matrix + 1e-6)
        
        return log_spec

    def get_breathing_envelope(self):
        """
        Applies a multi-rate filters sequence (simulating discrete wavelet transform levels D1, D2, A3)
        to isolate sub-vocal lung movements and return the breathing envelope.
        """
        if len(self.audio_buffer) < self.sample_rate * 4:
            return np.array([])
            
        samples = np.array(self.audio_buffer)
        
        # Step 1: Pre-emphasis high-pass
        emphasized = np.append(samples[0], samples[1:] - self.pre_emphasis_coeff * samples[:-1])
        
        # Step 2: Signal Rectification
        rectified = np.abs(emphasized)
        
        # Step 3: Downsampling / Decimation to 100Hz (downsample rate)
        decimation_factor = 160
        downsampled = rectified[::decimation_factor]
        fs_down = self.sample_rate / decimation_factor # 100 Hz
        
        # Step 4: Multi-stage DWT-approximation Filters (0.1 Hz to 0.6 Hz band)
        # Low-pass filter representing DWT Approximation Coefficient (A3)
        b_lp, a_lp = butter(2, 0.6 / (fs_down / 2.0), btype='low')
        # High-pass filter representing DWT Detail Coefficient (D3) to eliminate thermal drift
        b_hp, a_hp = butter(2, 0.1 / (fs_down / 2.0), btype='high')
        
        try:
            # Cascaded forward-backward filtering to prevent phase distortion
            envelope_lp = filtfilt(b_lp, a_lp, downsampled)
            envelope = filtfilt(b_hp, a_hp, envelope_lp)
            
            # Normalize envelope
            normalized_env = (envelope - np.mean(envelope)) / max(np.std(envelope), 1e-6)
            return normalized_env
        except:
            return np.array([])

    def estimate_respiratory_rate(self):
        """Computes respiration rate based on envelope peak detection using Welch PSD."""
        envelope = self.get_breathing_envelope()
        if envelope.size == 0:
            return 0.0, 0.0
            
        fs_down = 100.0 # 100 Hz decimation rate
        frequencies, psd = welch(envelope, fs=fs_down, nperseg=min(len(envelope), 256))
        
        valid_idx = np.where((frequencies >= 0.1) & (frequencies <= 0.6))[0]
        if len(valid_idx) == 0:
            return 0.0, 0.0
            
        peak_idx = valid_idx[np.argmax(psd[valid_idx])]
        peak_freq = frequencies[peak_idx]
        rr_bpm = peak_freq * 60.0
        
        # Calculate Signal-to-Noise Ratio (SNR) of respiratory peak
        signal_power = psd[peak_idx]
        noise_power = np.sum(psd[valid_idx]) - signal_power
        snr = 10 * np.log10(signal_power / max(noise_power, 1e-6))
        
        return rr_bpm, snr
