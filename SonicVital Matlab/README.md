# SonicVitals: Advanced Medical Image Processing Pipeline (MATLAB)

`medical_image_processing.m` is the **single-file, all-in-one** clinical medical image processing pipeline for SonicVitals. It measures all physiological vital signs from live webcam video in real-time, extracts the real pulse and oxygenation from facial micro-vascular capillary beds, and automatically generates a publication-grade **Clinical Medical Diagnostic Report in PDF and TXT formats** (no PNG files generated).

---

## Extracted Physiological Parameters (100% Real Optical Sensing)

1. **Heart Rate (HR)** in Beats Per Minute (BPM) & Cardiac Chronotropy status
2. **Contactless Respiration Rate (RR)** in breaths/minute (br/min) & Ventilatory status
3. **Oxygen Saturation ($SpO_2$ %)** via dual-wavelength chrominance ratio-of-ratios
4. **Heart Rate Variability (HRV)**:
   - **SDNN** (Standard Deviation of NN intervals, in ms - global autonomic tone)
   - **RMSSD** (Root Mean Square of Successive Differences, in ms - vagal tone)
   - **pNN50** (% of consecutive beats differing by > 50 ms)
5. **Facial Perfusion & Microvascular Colorimetry**:
   - **Erythema Index (EI)**: superficial capillary hyperemia/vasodilation
   - **Cyanosis Index (CI)**: tissue deoxygenation risk
   - **Perfusion Index (PI %)**: pulsatile signal amplitude
6. **Signal Quality & Hemodynamic Integrity**:
   - de Haan Signal-to-Noise Ratio (SNR, in dB)
   - Signal Quality Index (%)
7. **Automated Clinical Interpretations & Diagnostic Risk Categories**

---

## Compatibility & Requirements

- **MATLAB Online** (Web Browser) or **MATLAB Desktop** (R2019b or newer).
- **Zero toolboxes required**: Digital filtering, peak detection, Welch PSD, face/skin tracking, and PDF rendering are 100% self-contained in pure MATLAB.
- **Webcam Support**: Uses the standard MATLAB Support Package for USB Webcams (pre-installed in MATLAB Online).

### Important for MATLAB Online Users:
When you run `medical_image_processing` in MATLAB Online for the first time:
1. Look at your browser address bar at the top (near `https://matlab.mathworks.com`).
2. If prompted: **"mathworks.com wants to Use your camera"**, click **`Allow`**.
3. If blocked: Click the camera or lock icon (🎥 / 🔒) in the address bar and set Camera to **Allow**.

---

## How to Run

In the MATLAB Command Window, execute:

```matlab
% 1. Default Mode (Connects to live webcam in real-time with live face tracking & vitals preview)
results = medical_image_processing;

% 2. Live Interactive Camera Mode (explicit)
results = medical_image_processing('live');

% 3. Pre-Recorded Patient Video
results = medical_image_processing('patient_video.mp4');

% 4. Static Patient Photo (Colorimetry & Tissue Perfusion)
results = medical_image_processing('patient_photo.jpg');

% 5. Benchmark Simulation (Tests algorithm with synthetic stream without camera)
results = medical_image_processing('synthetic');

% 6. Algorithmic Self-Test
results = medical_image_processing('selftest');
```

---

## Interactive Live Capture & Controls

During real-time camera acquisition:
- **Live Preview Window**: Displays your camera stream with real-time green face tracking and cyan/yellow capillary ROIs.
- **Live Vitals Cards**: Updates Heart Rate, Respiration, SpO2, Perfusion Index, and SNR directly from your skin reflectance.
- **`[📸 CAPTURE PATIENT IMAGE & GENERATE MEDICAL REPORT (PDF)]`**: Click this green button (or press key `'c'`) anytime after 5 seconds to lock the patient frame and compile the medical report.
- **Automatic Auto-Capture**: If no button is pressed, it automatically finishes after 15 seconds of steady recording.

---

## Generated Medical Reports (PDF & TXT Only)

Every session automatically generates:
1. **`SonicVitals_Medical_Report.pdf`**: Publication-grade clinical vector PDF diagnostic report containing:
   - Patient metadata, timestamp, hardware details, and session duration.
   - Captured patient photograph with diagnostic ROI overlays (Forehead and Bilateral Malar Cheeks).
   - Physiological metrics summary table with measured values, reference ranges, and clinical status.
   - 4 diagnostic waveform panels: BVP pulse wave with systolic peaks, contactless respiration waveform, Welch PSD cardiac spectrum, and R-R tachogram.
   - Clinical diagnostic impression narrative and investigational disclaimer.
2. **`SonicVitals_Medical_Report.txt`**: Complete structured plain-text medical report summary.
*(No PNG image files are generated).*
