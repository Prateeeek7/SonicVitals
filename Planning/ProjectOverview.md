# SonicVitals: System Architecture & Implementation Overview

This document provides a comprehensive technical overview of **SonicVitals**, an Edge-AI enabled, multimodal physiological sensing platform. It details what the system is, how it operates, the underlying mathematical and signal processing algorithms, and the network communication layout.

---

## 1. Project Objective & Core Concept

Continuous vital sign monitoring is crucial for clinical and home care. Traditional methods (ECG, pulse oximeters, chest straps) require physical contact, which can cause skin irritation, discomfort, and patient compliance issues. 

**SonicVitals** solves this by combining two complementary sensing modalities into a single, low-cost edge node:
1. **Contactless Visual Pathway (rPPG)**: Remote photoplethysmography tracks sub-visual skin color fluctuations on the face caused by blood pumping from the heart, extracting the **Heart Rate (HR)**.
2. **Low-Contact Acoustic Pathway (Collar Mic)**: A high-precision I2S digital microphone clipped to the user's collar captures chest/respiratory sounds, extracting the **Respiration Rate (RR)**.

By feeding these two signals into an **Adaptive Attention Fusion Engine**, the system dynamically adjusts its confidence weights. If a user moves their head away (lowering video quality), the system relies more on the microphone. If the room gets noisy (lowering audio quality), it relies more on the camera.

---

## 2. Hardware Architecture & Signal Routing

The physical system consists of a compact, battery-powered edge node.

```
+-------------------------------------------------------------------+
|                           EDGE ACQUISITION NODE                   |
|                                                                   |
|  +------------------------+      +-----------------------------+  |
|  |     OV2640 Camera      |      |   INMP441 MEMS Microphone   |  |
|  |  (Internal FPC ribbon) |      |   (Wired to TX, RX, BOOT)   |  |
|  +-----------+------------+      +--------------+--------------+  |
|              |                                  |                 |
|              v (DVP Parallel)                   v (I2S Protocol)  |
|  +-------------------------------------------------------------+  |
|  |                Freenove ESP32-S3 WROOM CAM                  |  |
|  |         (Dual-core 240MHz, 8MB OPI PSRAM)                   |  |
|  +-----------------------------+-------------------------------+  |
|                                |                                  |
|                                v (I2C Protocol)                   |
|                  +-----------------------------+                  |
|                  |      SSD1306 OLED Screen    |                  |
|                  |   (Wired to SDA/SCL Ports)  |                  |
|                  +-----------------------------+                  |
+-------------------------------------------------------------------+
```

### Pin-to-Pin System Map
*   **Camera Module (OV2640)**: Pre-wired internally via FPC connector.
*   **Acoustic Microphone (INMP441)**: Connected via a flexible wire extension to the external headers:
    *   `SCK` (Bit Clock) $\rightarrow$ **TX (GPIO 43)**
    *   `WS` (Word Select) $\rightarrow$ **RX (GPIO 44)**
    *   `SD` (Serial Data) $\rightarrow$ **BOOT (GPIO 0)**
    *   `VDD` / `GND` $\rightarrow$ **3V3 / GND**
*   **OLED Display (SSD1306)**: Provides system status (IP address, Wi-Fi RSSI, sensor status):
    *   `SDA` $\rightarrow$ **SDA Port (GPIO 2)**
    *   `SCL` $\rightarrow$ **SCL Port (GPIO 1)**

---

## 3. Firmware Acquisition & FreeRTOS Multitasking

To prevent packet loss and maintain rigorous sample synchronization, the ESP32-S3 firmware ([Firmware.ino](file:///Users/pratikkumar/Desktop/SEM5%20Projects/SonicVitals/Firmware/Firmware.ino)) leverages **FreeRTOS multitasking** split across its two processing cores:

### Core Allocation Map
```
                  +-----------------------------------+
                  |        ESP32-S3 Dual Cores        |
                  +-----------------+-----------------+
                                    |
            +-----------------------+-----------------------+
            |                                               |
         [CORE 0]                                        [CORE 1]
 (Sensors & Buffer Scheduling)                     (Wi-Fi & Streaming)
            |                                               |
  - Task 1: Camera Capture (15 FPS)                - Task 3: UDP Sender
  - Task 2: I2S Audio Reader (16kHz)                 (Streams packet queues)
  - Queue 1: Video Frames (PSRAM)                  - Task 4: OLED Updater
  - Queue 2: Audio Buffers (SRAM)                    (Draws status charts)
```

### Network Communication Protocol
Data is packetized into a custom binary structure with microsecond-precision hardware timestamps to allow the server to align the video frames with the audio samples.
Each packet begins with a **17-byte Header**:
```cpp
struct PacketHeader {
  uint32_t magic;      // 0x53564e44 -> "SVND" (SonicVitals Node Data)
  uint8_t dataType;    // 1 = JPEG Video Chunk, 2 = PCM Audio Buffer
  uint32_t packetSeq;  // Incrementing sequence counter
  uint64_t timestamp;  // Microsecond timestamp from esp_timer_get_time()
  uint32_t payloadLen; // Length of the following raw data
};
```
*   **Video packets**: Large JPEG frames are fragmented into MTU-compliant UDP packets (<1400 bytes) to prevent network congestion.
*   **Audio packets**: Streamed in chunks of 512 bytes (128 samples of 32-bit audio at 16kHz).

---

## 4. Digital Signal Processing (DSP) Pipelines

Once the server ([server.py](file:///Users/pratikkumar/Desktop/SEM5%20Projects/SonicVitals/Server/server.py)) receives the raw streams, they are piped to the DSP Engine ([dsp.py](file:///Users/pratikkumar/Desktop/SEM5%20Projects/SonicVitals/Server/dsp.py)) which runs parallel extraction pipelines:

### A. Visual rPPG Pipeline (Heart Rate Extraction)
1.  **Face Landmark Tracking**: The server uses **MediaPipe Face Mesh** to locate 468 facial points in real-time.
2.  **Dynamic Region of Interest (ROI)**: Extracts coordinates for three skin regions:
    *   **Forehead**: Placed between the eyebrows and hairline.
    *   **Left Cheek** & **Right Cheek**: Positioned on the malar regions, avoiding the eyes and mouth folds.
3.  **Color Space Extraction**: Averages the Red, Green, and Blue pixels inside each ROI to create a raw temporal signal ($C(t) = [R(t), G(t), B(t)]$).
4.  **Motion Artifact Elimination (POS Algorithm)**: 
    The Plane-Orthogonal-to-Skin (POS) algorithm projects the RGB traces onto an orthogonal plane to isolate skin blood fluctuations from head movements:
    $$P = X_{sub} - \alpha Y_{sub}$$
    where $X_{sub}$ and $Y_{sub}$ are color projections, and $\alpha$ is the ratio of standard deviations of the projection signals.
5.  **Bandpass Filtering**: A Butterworth filter limits the signal to $[0.75\text{ Hz}, 3.0\text{ Hz}]$, representing 45 to 180 BPM.
6.  **Frequency Analysis (PSD)**: Welch's Periodogram computes the Power Spectral Density. The highest frequency peak within the heart rate band is selected as the estimated **Heart Rate (HR)**.

---

### B. Acoustic Respiratory Pipeline (Breathing Rate Extraction)
1.  **High-Pass Filtering**: Raw 16kHz audio passes through a 100 Hz high-pass filter to remove low-frequency physical movements.
2.  **Denoising (Spectral Subtraction)**: Establishes a profile of ambient room hums and subtracts it from the incoming stream.
3.  **Envelope Detection**: A multi-stage filter bank decimates the audio and extracts the envelope of inhalation and exhalation sounds (air turbulence):
    *   The signal is rectified and smoothed using a low-pass filter at 2.0 Hz (to track slow respiration cycles).
4.  **Welch's PSD**: Welch's method is applied to the breathing envelope trace across a window of 15 seconds. The peak frequency within the breathing band $[0.1\text{ Hz}, 0.6\text{ Hz}]$ (6 to 36 breaths per minute) is designated as the **Respiration Rate (RR)**.

---

### C. MATLAB Clinical Medical Image Processing Pipeline
To complement real-time server DSP with clinical-grade diagnostic validation, an offline and live MATLAB processing suite ([`matlab/medical_image_processing.m`](file:///Users/pratikkumar/Desktop/SEM5%20Projects/SonicVitals/matlab/medical_image_processing.m)) processes the video feed from the camera module:
1.  **Clinical Blood Volume Pulse (BVP) Waveform Recovery**:
    *   Applies Viola-Jones face detection and $YC_bC_r$ skin thresholding ($80 \le C_b \le 125, 133 \le C_r \le 173$) to isolate forehead and malar capillary beds.
    *   Decomposes normalized temporal color signals ($R_n, G_n, B_n$) using Plane-Orthogonal-to-Skin (POS) projection to isolate true arterial blood pulsations from ambient lighting and head motion.
2.  **Heart Rate & Heart Rate Variability (HRV)**:
    *   Applies a 4th-order zero-phase Butterworth bandpass filter ($0.75 - 3.0\text{ Hz}$).
    *   Uses Welch's PSD (`pwelch`) to extract the dominant heart rate peak and calculate the pulse Signal-to-Noise Ratio (SNR).
    *   Detects systolic peaks to extract Inter-Beat Intervals (IBIs) and computes clinical HRV indices: **SDNN** (overall autonomic regulation), **RMSSD** (parasympathetic vagal tone), and **pNN50**.
3.  **Non-Contact Oxygen Saturation ($SpO_2$)**:
    *   Calculates the dual-chrominance ratio-of-ratios ($R = \frac{AC_R / DC_R}{AC_B / DC_B}$) to estimate arterial blood oxygenation non-invasively.
4.  **Microvascular Perfusion & Diagnostic Indices**:
    *   Computes the **Erythema Index** ($\log(R) - \log(G)$) to quantify cutaneous flushing/vasodilation and the **Cyanosis Index** ($\frac{R-B}{R+B}$) to detect peripheral tissue hypoxia and hypoperfusion risk.

---

## 5. Adaptive Attention Fusion Engine

The fusion engine ([ml_model.py](file:///Users/pratikkumar/Desktop/SEM5 Projects/SonicVitals/Server/ml_model.py)) combines the estimates using a quality-weighted attention mechanism:

```
[ Visual Path (rPPG) ]    -->  [ Calculate SNR & Motion ]    -->  [ Visual Confidence (W_v) ]  --+
                                                                                                  |
                                                                                                  v
                                                                                           [Attention Weighting]  --> [Final Fused Vitals]
                                                                                                  ^
                                                                                                  |
[ Acoustic Path (Mic) ]   -->  [ Calculate Noise Floor ]     -->  [ Acoustic Confidence (W_a) ] --+
```

### How Confidence Weights are Calculated:
*   **Visual Confidence ($W_v$)**:
    *   **Motion Penalty**: Calculated from the standard deviation of Face Mesh centroid coordinates (higher motion = lower confidence).
    *   **SNR Calculation**: Ratio of the power of the heart rate peak to the power of the surrounding frequency bands.
*   **Acoustic Confidence ($W_a$)**:
    *   **Ambient Noise Floor**: Ratio of the average amplitude of the silence bands to the active inhalation peak envelopes.
    *   **Peak Clarity**: The sharpness (Q-factor) of the peak in the respiratory PSD.

The engine computes the final vitals using normalized weights:
$$\text{Fused HR} = \frac{W_v \cdot \text{HR}_v + W_a \cdot \text{HR}_a}{W_v + W_a}$$

---

## 6. Machine Learning Model (PyTorch Fusion)

To perform robust multimodal fusion, the system uses a custom **PyTorch Neural Network** named `MultimodalFusionNet` defined in [ml_model.py](file:///Users/pratikkumar/Desktop/SEM5%20Projects/SonicVitals/Server/ml_model.py).

### Architecture Specifications:
1. **Visual Encoder**: A 2-layer Feedforward network (3 inputs $\rightarrow$ 16 hidden $\rightarrow$ 16 outputs) that encodes raw visual HR, visual SNR, and facial motion level.
2. **Acoustic Encoder**: A 2-layer Feedforward network (3 inputs $\rightarrow$ 16 hidden $\rightarrow$ 16 outputs) that encodes raw acoustic RR, acoustic SNR, and noise amplitude variance.
3. **Quality Attention Block**: A 2-layer network that takes the quality metrics (visual SNR and acoustic SNR) and outputs raw logits for each channel. A Softmax function is applied to convert these logits into normalized attention weights:
   $$[w_{visual}, w_{acoustic}] = \text{Softmax}(\text{Logits})$$
   These weights modulate the visual and acoustic encoded representations.
4. **Multitask Regression Heads**: The weighted latent vectors are concatenated and passed to three independent regression heads:
   * **Heart Rate Head**: Predicts final filtered HR.
   * **Respiration Rate Head**: Predicts final filtered RR.
   * **System Confidence Head**: Uses a Sigmoid output to predict the overall reliability score ($[0.0, 1.0]$) of the fused readings.

*Note: If PyTorch is not installed in the execution environment, the `AdaptiveFusionEngine` automatically falls back to a deterministic, math-based weighted-average model to ensure reliability.*

---

## 7. Storage Engine (SQLite Database)

For clinical study archiving and local analysis, the server writes all session records to an embedded **SQLite3 Database** (`sessions.db`) managed via [database.py](file:///Users/pratikkumar/Desktop/SEM5%20Projects/SonicVitals/Server/database.py).

### Schema Design:
1. **`sessions` Table**: Tracks structural metadata for each trial.
   * `session_id` (Primary Key, e.g., `SESS_16938...`)
   * `timestamp` (Unix epoch time of start)
   * `participant_id` (Identifier string)
   * `fps` (Calculated video frame rate)
   * `mic_rate` (Audio sample rate, e.g., 16000)
   * `fusion_strategy` (e.g., `Attention-ML` or `Deterministic`)
2. **`physiological_log` Table**: Stores time-series vital sign records linked to the session.
   * `id` (Auto-incrementing PK)
   * `session_id` (Foreign Key referencing `sessions`)
   * `timestamp_ms` (Millisecond-precision epoch time)
   * `vis_hr`, `vis_snr` (Raw visual inputs)
   * `ac_rr`, `ac_snr` (Raw acoustic inputs)
   * `fused_hr`, `fused_rr` (Calculated outputs from the fusion engine)
   * `confidence` (Calculated attention-based overall reliability score)

### Data Export:
* The database manager contains built-in functions to automatically query and export physiological logs into research-ready **CSV files** (saved in the `exports/` folder) for easy processing in Python (Pandas), MATLAB, or R.

---

## 8. Development, Simulation, & Deployment Flow

To make development simple before you finish soldering the physical hardware, the system is equipped with an **Offline Emulation Mode**:

### Development Modes

1.  **Emulation Mode (No Hardware Needed)**:
    Allows testing the entire Python server, DSP pipelines, and GUI by feeding standard dataset video files (`.mp4`) and audio files (`.wav`) through the system:
    ```bash
    npm run emulate
    ```
    This reads the video, runs MediaPipe, extracts RGB traces, filters them, plays the audio, denoises it, and displays both real-time waveforms on the desktop GUI.

2.  **Production Mode (With Hardware)**:
    When you flash the ESP32-S3 board with the firmware, it connects to your Wi-Fi router. You run:
    ```bash
    npm run gui
    ```
    The Python server opens a UDP socket, binds to port `50005`, waits for the ESP32-S3 packets, and processes the live feeds in real-time.
