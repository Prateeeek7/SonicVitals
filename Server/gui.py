import sys
import time
import numpy as np
import cv2
from PySide6.QtCore import Qt, QTimer, QPointF, QRectF
from PySide6.QtGui import QFont, QColor, QImage, QPixmap, QPainter, QPen, QBrush
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QStackedWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QFormLayout, QLineEdit, QComboBox, QPlainTextEdit, QFrame,
    QSplitter
)

# Import local backend modules
from server import DataReceiver
from dsp import VisualDSP, AcousticDSP
from ml_model import AdaptiveFusionEngine

# Color Palette (Medical Instrument Theme)
BG_COLOR = QColor("#FAFAF8")      # Crisp off-white
SECTION_COLOR = QColor("#F2F2EE") # Light grey section
TEXT_COLOR = QColor("#3A3A3A")    # Charcoal grey
EMERALD_GREEN = QColor("#0F6A4A") # Stable
OLIVE_GREEN = QColor("#6B8E23")   # Secondary
WARM_AMBER = QColor("#D98C00")    # Warning
TERRACOTTA = QColor("#B85430")    # Alert
BORDER_COLOR = QColor("#D3D3CB")   # Outline border

class RealtimePlot(QWidget):
    """Custom high-performance drawing widget for physiological waveforms."""
    def __init__(self, title, y_min=-3.0, y_max=3.0, grid_lines=5, parent=None):
        super().__init__(parent)
        self.title = title
        self.y_min = y_min
        self.y_max = y_max
        self.grid_lines = grid_lines
        self.data = np.zeros(150)
        self.setMinimumHeight(130)
        
    def update_data(self, new_data):
        if len(new_data) == 0:
            return
        # Resample or fit new data to 150 points for display
        if len(new_data) > 150:
            self.data = new_data[-150:]
        else:
            self.data = np.zeros(150)
            self.data[-len(new_data):] = new_data
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        w = self.width()
        h = self.height()
        
        # Draw background card (no shadow, sharp edges)
        painter.setBrush(QBrush(SECTION_COLOR))
        painter.setPen(QPen(BORDER_COLOR, 1))
        painter.drawRect(0, 0, w - 1, h - 1)
        
        # Plot area margins
        margin_l = 45
        margin_r = 15
        margin_t = 25
        margin_b = 15
        
        plot_w = w - margin_l - margin_r
        plot_h = h - margin_t - margin_b
        
        # Draw Title
        painter.setPen(QPen(TEXT_COLOR))
        painter.setFont(QFont("Inter", 8, QFont.Bold))
        painter.drawText(margin_l, 18, self.title)
        
        # Draw Grid Lines
        painter.setFont(QFont("Inter", 7))
        for i in range(self.grid_lines):
            y_val = self.y_min + (self.y_max - self.y_min) * i / (self.grid_lines - 1)
            y_pos = margin_t + plot_h - (i * plot_h / (self.grid_lines - 1))
            
            # Grid line
            painter.setPen(QPen(QColor("#E2E2DC"), 1, Qt.DashLine))
            painter.drawLine(margin_l, y_pos, w - margin_r, y_pos)
            
            # Y-axis label
            painter.setPen(QPen(TEXT_COLOR))
            painter.drawText(5, y_pos + 3, f"{y_val:.1f}")
            
        # Draw Waveform line
        if len(self.data) > 1:
            painter.setPen(QPen(EMERALD_GREEN, 1.5))
            points = []
            for idx, val in enumerate(self.data):
                x = margin_l + (idx * plot_w / (len(self.data) - 1))
                # Clamp value to y_min and y_max
                clamped_val = max(self.y_min, min(self.y_max, val))
                # Calculate normalized Y coordinate
                y = margin_t + plot_h - ((clamped_val - self.y_min) * plot_h / (self.y_max - self.y_min))
                points.append(QPointF(x, y))
                
            for k in range(len(points) - 1):
                painter.drawLine(points[k], points[k+1])

class HeatmapSpectrogram(QWidget):
    """Custom high-performance spectrogram rendering widget using QImage."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(130)
        self.spectrogram = np.zeros((128, 128))
        
    def update_spectrogram(self, spec):
        self.spectrogram = spec
        self.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        w = self.width()
        h = self.height()
        
        # Draw background card
        painter.setBrush(QBrush(SECTION_COLOR))
        painter.setPen(QPen(BORDER_COLOR, 1))
        painter.drawRect(0, 0, w - 1, h - 1)
        
        margin_l = 45
        margin_r = 15
        margin_t = 25
        margin_b = 15
        
        plot_w = w - margin_l - margin_r
        plot_h = h - margin_t - margin_b
        
        # Draw Title
        painter.setPen(QPen(TEXT_COLOR))
        painter.setFont(QFont("Inter", 8, QFont.Bold))
        painter.drawText(margin_l, 18, "Acoustic STFT Spectrogram (dB)")
        
        if self.spectrogram.size > 0:
            # Map values to color heatmap (Green representation)
            norm = (self.spectrogram - np.min(self.spectrogram)) / max((np.max(self.spectrogram) - np.min(self.spectrogram)), 1e-6)
            spec_img = np.zeros((self.spectrogram.shape[0], self.spectrogram.shape[1], 3), dtype=np.uint8)
            # Emerald green gradient mapping
            spec_img[:, :, 1] = (norm * 200).astype(np.uint8) # Green intensity
            spec_img[:, :, 0] = (norm * 15).astype(np.uint8)  # Blue intensity
            spec_img[:, :, 2] = (norm * 15).astype(np.uint8)  # Red intensity
            
            # Flip image upside down for frequency display (low freqs on bottom)
            flipped_img = cv2.flip(spec_img, 0)
            
            q_img = QImage(
                flipped_img.data,
                flipped_img.shape[1],
                flipped_img.shape[0],
                flipped_img.strides[0],
                QImage.Format_RGB888
            )
            
            painter.drawImage(QRectF(margin_l, margin_t, plot_w, plot_h), q_img)

class SonicVitalsWindow(QMainWindow):
    def __init__(self, video_file_path=None, audio_file_path=None):
        super().__init__()
        self.setWindowTitle("SonicVitals - Physiological Sensing Platform")
        self.resize(1100, 700)
        self.setStyleSheet(f"background-color: {BG_COLOR.name()}; color: {TEXT_COLOR.name()};")
        
        # Initialize Backend Pipelines
        self.receiver = DataReceiver(video_file_path=video_file_path, audio_file_path=audio_file_path)
        self.visual_dsp = VisualDSP()
        self.acoustic_dsp = AcousticDSP()
        self.fusion_engine = AdaptiveFusionEngine()
        
        # Start receiver thread
        self.receiver.start()
        
        self._init_ui()
        
        # UI Refresh timer (30 Hz / 33 ms)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_loop)
        self.timer.start(33)
        
    def _init_ui(self):
        # Main Central Widget
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 1. Full-Width Top Horizontal Navigation Bar
        nav_bar = QWidget()
        nav_bar.setStyleSheet(f"background-color: {SECTION_COLOR.name()}; border-bottom: 1px solid {BORDER_COLOR.name()};")
        nav_bar.setFixedHeight(50)
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(15, 0, 15, 0)
        
        # Logo (Left-aligned)
        logo = QLabel("SonicVitals")
        logo.setFont(QFont("Inter", 12, QFont.Bold))
        logo.setStyleSheet(f"color: {EMERALD_GREEN.name()}; margin-right: 20px;")
        nav_layout.addWidget(logo)
        
        # Navigation Links
        self.nav_buttons = []
        buttons_info = [
            ("Dashboard", 0),
            ("Live Monitoring", 0), # Dashboard incorporates both
            ("Signal Analysis", 1),
            ("Device Management", 2),
            ("Experiments", 3),
            ("Reports", 4),
            ("Settings", 5)
        ]
        
        for name, idx in buttons_info:
            if name == "Live Monitoring":
                continue # Merged to keep layout clean
            btn = QPushButton(name)
            btn.setFont(QFont("Inter", 9, QFont.Bold))
            btn.setFlat(True)
            # Sharp edges, minimal style
            btn.setStyleSheet(f"border: none; padding: 5px 10px; color: {TEXT_COLOR.name()};")
            btn.clicked.connect(lambda checked=False, i=idx: self._change_page(i))
            self.nav_buttons.append(btn)
            nav_layout.addWidget(btn)
            
        nav_layout.addStretch()
        
        # Status / Logged-in Profile (Right-aligned)
        self.conn_label = QLabel("DISCONNECTED")
        self.conn_label.setFont(QFont("Inter", 8, QFont.Bold))
        self.conn_label.setStyleSheet(f"color: {TERRACOTTA.name()}; margin-right: 15px;")
        nav_layout.addWidget(self.conn_label)
        
        profile = QLabel("SENSE Researcher | VIT")
        profile.setFont(QFont("Inter", 8))
        profile.setStyleSheet(f"color: {TEXT_COLOR.name()};")
        nav_layout.addWidget(profile)
        
        main_layout.addWidget(nav_bar)
        
        # 2. Central Workspace Stack
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)
        
        # Create Stack Pages
        self._create_dashboard_page()     # Page 0
        self._create_analysis_page()      # Page 1
        self._create_device_page()        # Page 2
        self._create_experiments_page()   # Page 3
        self._create_reports_page()       # Page 4
        self._create_settings_page()      # Page 5
        
        self._change_page(0) # Start on dashboard

    def _change_page(self, index):
        self.stack.setCurrentIndex(index)
        # Highlight active nav link
        for idx, btn in enumerate(self.nav_buttons):
            if idx == index:
                btn.setStyleSheet(f"border-bottom: 2px solid {EMERALD_GREEN.name()}; padding: 5px 10px; color: {EMERALD_GREEN.name()};")
            else:
                btn.setStyleSheet(f"border: none; padding: 5px 10px; color: {TEXT_COLOR.name()};")

    # ================= UI Page Creators =================

    def _create_dashboard_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Top Row Splitter (Video feed on left, Audio stream & acquisition logs on right)
        top_splitter = QSplitter(Qt.Horizontal)
        
        # Left Panel: Video Feed Area
        video_panel = QFrame()
        video_panel.setStyleSheet(f"background-color: {SECTION_COLOR.name()}; border: 1px solid {BORDER_COLOR.name()};")
        video_layout = QVBoxLayout(video_panel)
        video_layout.setContentsMargins(5, 5, 5, 5)
        
        video_title = QLabel("PRIMARY VISION STREAM (rPPG FACIAL CAPTURE)")
        video_title.setFont(QFont("Inter", 8, QFont.Bold))
        video_layout.addWidget(video_title)
        
        self.cam_feed_label = QLabel()
        self.cam_feed_label.setAlignment(Qt.AlignCenter)
        self.cam_feed_label.setStyleSheet("background-color: #000000;")
        self.cam_feed_label.setMinimumSize(400, 300)
        video_layout.addWidget(self.cam_feed_label)
        top_splitter.addWidget(video_panel)
        
        # Right Panel: Live audio waveform and status boxes
        right_panel = QFrame()
        right_panel.setStyleSheet(f"border: 1px solid {BORDER_COLOR.name()};")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 10, 10, 10)
        
        # Physiological status readouts (HR, RR, Quality, Confidence)
        stats_layout = QHBoxLayout()
        self.stat_hr = self._create_stat_box("HEART RATE", "0.0 BPM", EMERALD_GREEN)
        self.stat_rr = self._create_stat_box("RESPIRATION RATE", "0.0 Breaths/M", EMERALD_GREEN)
        self.stat_qual = self._create_stat_box("SIGNAL QUALITY", "0.0%", EMERALD_GREEN)
        self.stat_conf = self._create_stat_box("CONFIDENCE", "0.0%", EMERALD_GREEN)
        
        stats_layout.addWidget(self.stat_hr)
        stats_layout.addWidget(self.stat_rr)
        stats_layout.addWidget(self.stat_qual)
        stats_layout.addWidget(self.stat_conf)
        right_layout.addLayout(stats_layout)
        
        # Audio live trace
        self.audio_plot = RealtimePlot("Live Audio Waveform (Thoracic Acoustics)", y_min=-1.0, y_max=1.0)
        right_layout.addWidget(self.audio_plot)
        top_splitter.addWidget(right_panel)
        
        layout.addWidget(top_splitter)
        
        # Bottom Row: Waveform traces (rPPG Waveform, Respiration Envelope)
        bottom_layout = QHBoxLayout()
        self.rppg_plot = RealtimePlot("Recovered Blood Volume Pulse (rPPG Waveform)")
        self.resp_plot = RealtimePlot("Recovered Respiration Envelope", y_min=-2.0, y_max=2.0)
        bottom_layout.addWidget(self.rppg_plot)
        bottom_layout.addWidget(self.resp_plot)
        
        layout.addLayout(bottom_layout)
        self.stack.addWidget(page)

    def _create_stat_box(self, title, default_val, text_color):
        box = QFrame()
        box.setStyleSheet(f"background-color: {SECTION_COLOR.name()}; border: 1px solid {BORDER_COLOR.name()};")
        box.setFixedHeight(75)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 8, 8, 8)
        
        title_lbl = QLabel(title)
        title_lbl.setFont(QFont("Inter", 8, QFont.Bold))
        title_lbl.setStyleSheet(f"color: {TEXT_COLOR.name()};")
        
        val_lbl = QLabel(default_val)
        val_lbl.setFont(QFont("Inter", 14, QFont.Bold))
        val_lbl.setStyleSheet(f"color: {text_color.name()};")
        
        layout.addWidget(title_lbl)
        layout.addWidget(val_lbl)
        return box

    def _create_analysis_page(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Left Panel: Live Spectrogram rendering
        left_panel = QFrame()
        left_panel.setStyleSheet(f"border: 1px solid {BORDER_COLOR.name()};")
        left_layout = QVBoxLayout(left_panel)
        self.spectrogram_widget = HeatmapSpectrogram()
        left_layout.addWidget(self.spectrogram_widget)
        layout.addWidget(left_panel)
        
        # Right Panel: FFT Cardiac Spectrum
        right_panel = QFrame()
        right_panel.setStyleSheet(f"border: 1px solid {BORDER_COLOR.name()};")
        right_layout = QVBoxLayout(right_panel)
        self.fft_plot = RealtimePlot("Visual rPPG FFT Power Spectrum", y_min=0.0, y_max=1.0)
        right_layout.addWidget(self.fft_plot)
        layout.addWidget(right_panel)
        
        self.stack.addWidget(page)

    def _create_device_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(15, 15, 15, 15)
        
        title = QLabel("CONNECTED HARDWARE TELEMETRY LOGS (ESP32-S3)")
        title.setFont(QFont("Inter", 11, QFont.Bold))
        layout.addWidget(title)
        
        # Telemetry Table
        self.tel_table = QTableWidget(5, 2)
        self.tel_table.setHorizontalHeaderLabels(["Telemetry Metric", "Live Value"])
        self.tel_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tel_table.verticalHeader().setVisible(False)
        self.tel_table.setStyleSheet(f"background-color: {SECTION_COLOR.name()}; border: 1px solid {BORDER_COLOR.name()};")
        layout.addWidget(self.tel_table)
        
        # Console logs
        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setStyleSheet("background-color: #1E1E1E; color: #FFFFFF; font-family: Courier; font-size: 10px;")
        self.console.appendPlainText("[INFO] SonicVitals device logger initialized.")
        layout.addWidget(self.console)
        
        self.stack.addWidget(page)

    def _create_experiments_page(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Left Panel: parameters
        form_panel = QFrame()
        form_panel.setStyleSheet(f"background-color: {SECTION_COLOR.name()}; border: 1px solid {BORDER_COLOR.name()};")
        form_panel.setFixedWidth(300)
        form_layout = QFormLayout(form_panel)
        form_layout.setContentsMargins(15, 15, 15, 15)
        
        form_title = QLabel("ACQUISITION PARAMETERS")
        form_title.setFont(QFont("Inter", 9, QFont.Bold))
        form_layout.addRow(form_title)
        
        form_layout.addRow("Participant ID:", QLineEdit("VIT_SUB_01"))
        
        cam_fps = QComboBox()
        cam_fps.addItems(["15 FPS", "30 FPS"])
        form_layout.addRow("Camera Frame Rate:", cam_fps)
        
        mic_rate = QComboBox()
        mic_rate.addItems(["16000 Hz", "44100 Hz"])
        form_layout.addRow("Audio Sample Rate:", mic_rate)
        
        fuse_strat = QComboBox()
        fuse_strat.addItems(["Quality-Aware Attention (ML)", "Raw Decoupled Estimation"])
        form_layout.addRow("Fusion Strategy:", fuse_strat)
        
        btn_start = QPushButton("START RECORDING SESSION")
        btn_start.setStyleSheet(f"background-color: {EMERALD_GREEN.name()}; color: white; padding: 8px; border: none; font-weight: bold;")
        form_layout.addRow(btn_start)
        
        layout.addWidget(form_panel)
        
        # Right Panel: statistical summary mockup
        summary_panel = QFrame()
        summary_panel.setStyleSheet(f"border: 1px solid {BORDER_COLOR.name()};")
        summary_layout = QVBoxLayout(summary_panel)
        summary_lbl = QLabel("EXPERIMENTAL STATISTICAL REPORT PREVIEW")
        summary_lbl.setFont(QFont("Inter", 9, QFont.Bold))
        summary_layout.addWidget(summary_lbl)
        
        desc = QLabel(
            "Bland-Altman Agreement Plots and Regression summaries will render here "
            "following complete recording sessions."
        )
        desc.setAlignment(Qt.AlignCenter)
        summary_layout.addWidget(desc)
        
        layout.addWidget(summary_panel)
        self.stack.addWidget(page)

    def _create_reports_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(15, 15, 15, 15)
        
        title = QLabel("SAVED CLINICAL REPORT LOGS")
        title.setFont(QFont("Inter", 11, QFont.Bold))
        layout.addWidget(title)
        
        rep_table = QTableWidget(3, 5)
        rep_table.setHorizontalHeaderLabels(["Session ID", "Participant", "Mean HR (BPM)", "Mean RR (Breaths/M)", "Action"])
        rep_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        rep_table.verticalHeader().setVisible(False)
        rep_table.setStyleSheet(f"background-color: {SECTION_COLOR.name()}; border: 1px solid {BORDER_COLOR.name()};")
        
        # Mock Report data
        reports_data = [
            ("SESS_001", "VIT_SUB_01", "72.4", "15.8", "Export PDF"),
            ("SESS_002", "VIT_SUB_02", "81.1", "18.2", "Export PDF"),
            ("SESS_003", "VIT_SUB_03", "68.9", "12.4", "Export PDF")
        ]
        
        for r_idx, row in enumerate(reports_data):
            for c_idx, val in enumerate(row):
                rep_table.setItem(r_idx, c_idx, QTableWidgetItem(val))
                
        layout.addWidget(rep_table)
        self.stack.addWidget(page)

    def _create_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(15, 15, 15, 15)
        
        title = QLabel("SYSTEM CONFIGURATION")
        title.setFont(QFont("Inter", 11, QFont.Bold))
        layout.addWidget(title)
        
        desc = QLabel("Configure network sockets, preprocessing coefficients, and target output folder structures here.")
        layout.addWidget(desc)
        layout.addStretch()
        self.stack.addWidget(page)

    # ================= Realtime Data Update Loop =================

    def _update_loop(self):
        # 1. Fetch telemetry
        tel = self.receiver.get_telemetry()
        if tel["connected"]:
            self.conn_label.setText(f"CONNECTED | RSSI: {WiFi_RSSI_Mock()} dBm")
            self.conn_label.setStyleSheet(f"color: {EMERALD_GREEN.name()}; margin-right: 15px;")
        else:
            self.conn_label.setText("DISCONNECTED")
            self.conn_label.setStyleSheet(f"color: {TERRACOTTA.name()}; margin-right: 15px;")

        # Update Device Telemetry Tab
        self.tel_table.setItem(0, 0, QTableWidgetItem("ESP32-S3 Stream Connection"))
        self.tel_table.setItem(0, 1, QTableWidgetItem("Active" if tel["connected"] else "Offline"))
        self.tel_table.setItem(1, 0, QTableWidgetItem("Video Frame Rate"))
        self.tel_table.setItem(1, 1, QTableWidgetItem(f"{tel['fps']} FPS"))
        self.tel_table.setItem(2, 0, QTableWidgetItem("Network Latency"))
        self.tel_table.setItem(2, 1, QTableWidgetItem(f"{tel['latency_ms']} ms"))
        self.tel_table.setItem(3, 0, QTableWidgetItem("Total Received Packets"))
        self.tel_table.setItem(3, 1, QTableWidgetItem(str(tel["packets_received"])))
        self.tel_table.setItem(4, 0, QTableWidgetItem("Lost Packets"))
        self.tel_table.setItem(4, 1, QTableWidgetItem(str(tel["lost_packets"])))

        # 2. Fetch Video Frame
        ts_v, img = self.receiver.get_latest_video()
        if img is not None:
            # Process visual pipeline (Face Mesh and green average ROI)
            landmarks, face_present = self.visual_dsp.process_frame(img, ts_v)
            
            # Draw landmarks locally on the frame
            for pt in landmarks:
                cv2.circle(img, pt, 1, (10, 100, 15), -1)
                
            # Convert OpenCV frame to Qt Pixmap and show in label
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            qh, qw, qc = img_rgb.shape
            q_img = QImage(img_rgb.data, qw, qh, qw * qc, QImage.Format_RGB888)
            self.cam_feed_label.setPixmap(QPixmap.fromImage(q_img).scaled(
                self.cam_feed_label.width(),
                self.cam_feed_label.height(),
                Qt.KeepAspectRatio
            ))
            
        # 3. Fetch Audio Packet
        while True:
            ts_a, samples = self.receiver.get_audio_chunk()
            if samples is not None:
                self.acoustic_dsp.add_samples(samples)
                # Plot raw samples
                self.audio_plot.update_data(samples)
            else:
                break
                
        # 4. Perform DSP & Sensor Fusion Estimations
        vis_hr, vis_snr = self.visual_dsp.estimate_heart_rate()
        ac_rr, ac_snr = self.acoustic_dsp.estimate_respiratory_rate()
        
        # Run Quality-Aware Fusion
        fused_hr, fused_rr, confidence, w_vis, w_ac = self.fusion_engine.fuse(
            vis_hr, vis_snr, ac_rr, ac_snr
        )
        
        # 5. Update Waveform plots
        rppg_wave = self.visual_dsp.get_filtered_rppg()
        if rppg_wave.size > 0:
            self.rppg_plot.update_data(rppg_wave)
            
        resp_envelope = self.acoustic_dsp.get_breathing_envelope()
        if resp_envelope.size > 0:
            self.resp_plot.update_data(resp_envelope)
            
        # Update Spectrogram and FFT plots
        self.spectrogram_widget.update_spectrogram(self.acoustic_dsp.get_spectrogram())
        
        # Calculate visual FFT trace
        if rppg_wave.size > 0:
            fs = self.visual_dsp.fps
            freqs, psd = welch(rppg_wave, fs=fs, nperseg=min(len(rppg_wave), 128))
            # Normalize PSD for plotting
            norm_psd = psd / max(np.max(psd), 1e-6)
            self.fft_plot.update_data(norm_psd)

        # 6. Update Status Readout displays
        if tel["connected"]:
            # Display values
            self.stat_hr.findChildren(QLabel)[1].setText(f"{fused_hr:.1f} BPM")
            self.stat_rr.findChildren(QLabel)[1].setText(f"{fused_rr:.1f} Br/M")
            self.stat_qual.findChildren(QLabel)[1].setText(f"{vis_snr:.1f} dB")
            self.stat_conf.findChildren(QLabel)[1].setText(f"{confidence*100.0:.1f}%")
            
            # Style update based on thresholds (normal = green, warning = amber, alert = terracotta)
            if confidence > 0.7:
                self.stat_conf.setStyleSheet(f"background-color: {EMERALD_GREEN.name()}33; border: 1px solid {EMERALD_GREEN.name()};")
            elif confidence > 0.4:
                self.stat_conf.setStyleSheet(f"background-color: {WARM_AMBER.name()}33; border: 1px solid {WARM_AMBER.name()};")
            else:
                self.stat_conf.setStyleSheet(f"background-color: {TERRACOTTA.name()}33; border: 1px solid {TERRACOTTA.name()};")
        else:
            # Set offline defaults
            self.stat_hr.findChildren(QLabel)[1].setText("0.0 BPM")
            self.stat_rr.findChildren(QLabel)[1].setText("0.0 Br/M")
            self.stat_qual.findChildren(QLabel)[1].setText("0.0 dB")
            self.stat_conf.findChildren(QLabel)[1].setText("0.0%")
            self.stat_conf.setStyleSheet(f"background-color: {SECTION_COLOR.name()}; border: 1px solid {BORDER_COLOR.name()};")

    def closeEvent(self, event):
        self.receiver.stop()
        event.accept()

# Helper mock for RSSI display
def WiFi_RSSI_Mock():
    return int(-50 + np.random.randint(-5, 5))

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SonicVitals Clinical Dashboard")
    parser.add_argument("--video", type=str, default=None, help="Path to offline video emulation file (.mp4/.avi)")
    parser.add_argument("--audio", type=str, default=None, help="Path to offline audio emulation file (.wav)")
    args, unknown = parser.parse_known_args()

    app = QApplication(sys.argv)
    app.setFont(QFont("Inter", 9))
    window = SonicVitalsWindow(video_file_path=args.video, audio_file_path=args.audio)
    window.show()
    sys.exit(app.exec())
