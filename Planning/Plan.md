I think we should first step back and evaluate **whether the research problem itself is strong**, because that determines whether the project is merely a good engineering build or something that could become a publishable paper.

After looking at recent trends (2023–2026), there are thousands of papers on:

* Camera-only heart rate estimation (rPPG)
* Smartphone PPG using a fingertip
* Respiratory rate estimation using microphones
* Wearable ECG and PPG fusion

However, **very few systems combine contactless vision, acoustic sensing, edge hardware, adaptive signal-quality estimation, and multimodal AI into a single low-cost embedded platform**. That is where the novelty should come from—not from estimating heart rate itself.

Therefore, I would **not** build "another vital sign monitoring system." I would build an **adaptive multimodal physiological sensing platform**.

---

# Proposed Research Title

**SonicVitals: An Edge-AI Enabled Multimodal Physiological Sensing Platform using Contactless Vision, Acoustic Analysis, and Adaptive Signal Fusion**

This title intentionally avoids words like *app* or *smartphone*. It positions the work as a research platform instead of a software application.

---

# Core Research Problem

Current physiological monitoring systems generally fall into three categories. Clinical systems provide high accuracy but require expensive equipment and physical contact with the patient. Wearable systems offer continuous monitoring but suffer from user discomfort, battery limitations, and poor long-term compliance. Contactless camera-based systems are inexpensive but become unreliable under poor illumination, facial motion, occlusions, or skin tone variations. Similarly, microphone-based respiratory monitoring is sensitive to environmental noise and room acoustics.

Each sensing modality performs well only under certain conditions. Existing research rarely addresses how multiple inexpensive sensing modalities can be combined intelligently to overcome the weaknesses of each individual sensor. Furthermore, most contactless systems rely entirely on software running on smartphones or computers, without considering an embedded edge sensing architecture suitable for deployment in real-world environments.

The central research question of SonicVitals is therefore:

> **Can a low-cost embedded multimodal sensing platform intelligently combine visual and acoustic physiological signals to achieve more robust and reliable vital sign estimation than existing single-modality approaches?**

This is the contribution your work aims to answer.

---

# Research Hypothesis

The hypothesis is that adaptive multimodal sensor fusion, supported by signal-quality assessment and machine learning, will significantly improve the robustness and reliability of physiological parameter estimation compared with camera-only or microphone-only systems, while remaining inexpensive enough for practical deployment.

---

# Overall Concept

The proposed system consists of two tightly integrated components: a dedicated edge hardware node responsible for multimodal physiological data acquisition and a software platform responsible for signal processing, artificial intelligence inference, visualization, and data management.

Rather than embedding heavy artificial intelligence models on a resource-constrained microcontroller, the hardware focuses exclusively on synchronized sensing and efficient transmission of physiological data. Computationally intensive digital signal processing and deep learning algorithms execute on a desktop or laptop computer during development. This separation enables rapid experimentation while preserving a clear migration path toward future edge inference.

---

# Hardware Architecture

The hardware serves as a **physiological sensing node** rather than a complete processing unit.

The central controller is an **ESP32-S3**, selected because it offers a dual-core Xtensa LX7 processor, integrated Wi-Fi and Bluetooth, improved RAM compared with earlier ESP32 variants, native USB support, I2S interfaces for digital microphones, camera interfaces, and compatibility with TensorFlow Lite Micro for future TinyML deployment.

An OV2640 camera module continuously captures facial video at a moderate frame rate. Unlike fingerprint-based PPG systems, the camera observes subtle temporal variations in facial skin reflectance caused by blood volume changes, enabling remote photoplethysmography.

An INMP441 MEMS digital microphone simultaneously records respiratory sounds, speech, and weak thoracic acoustic signatures. The microphone communicates over the I2S protocol, providing higher-quality digital audio than inexpensive analog modules while reducing susceptibility to electrical interference.

An OLED display provides basic device status information, including Wi-Fi connectivity, acquisition state, battery level, and synchronization status. Power is supplied through a rechargeable lithium-ion battery with integrated charging circuitry.

The ESP32 timestamps every video frame and audio packet before transmitting synchronized data streams to the host computer through Wi-Fi. Importantly, the embedded firmware performs only lightweight preprocessing such as frame resizing, audio buffering, timestamp generation, and optional compression, minimizing computational load while ensuring deterministic acquisition.

---

# Software Architecture

The software platform represents the primary research contribution.

Incoming synchronized data streams first enter a data acquisition manager responsible for temporal alignment, buffering, and packet integrity verification. A synchronization module compensates for network latency and reconstructs continuous multimodal physiological streams.

The visual processing pipeline begins with facial landmark detection using MediaPipe Face Mesh. Regions of interest such as the forehead and cheeks are dynamically extracted because these areas exhibit strong blood perfusion. Average RGB intensity signals are converted into remote photoplethysmographic waveforms through chrominance-based methods such as CHROM or POS algorithms.

These physiological waveforms undergo temporal normalization, detrending, illumination correction, adaptive filtering, Independent Component Analysis, and band-pass filtering before spectral analysis.

Simultaneously, the acoustic processing pipeline performs spectral denoising, pre-emphasis filtering, adaptive noise cancellation, Short-Time Fourier Transform, Mel-frequency spectral analysis, wavelet denoising, and respiratory segmentation. Breathing cycles, respiratory rhythm, and acoustic energy distributions are extracted from the processed audio signals.

Both processing branches generate complementary physiological features that are synchronized and forwarded to the multimodal fusion engine.

---

# Signal Processing Foundation

Signal and Systems forms the mathematical foundation of the project.

Physiological signals are treated as discrete-time stochastic processes. Video intensity variations and acoustic waveforms are sampled according to Nyquist criteria before entering digital preprocessing pipelines.

Noise suppression employs finite impulse response and infinite impulse response filters specifically designed for physiological frequency bands. Frequency-domain representations are obtained using Fast Fourier Transform and Short-Time Fourier Transform to isolate cardiac and respiratory frequency components. Wavelet transforms enable multi-resolution analysis of transient physiological phenomena while preserving temporal localization.

Cross-correlation estimates synchronization between visual and acoustic modalities. Power spectral density estimation identifies dominant physiological frequencies, whereas adaptive filtering suppresses environmental interference. Peak detection algorithms identify cardiac cycles and respiratory phases, enabling estimation of heart rate variability and breathing intervals.

Thus, nearly every major concept taught in Signal and Systems—including convolution, Fourier analysis, filtering, spectral estimation, sampling, aliasing, windowing, and stochastic signal analysis—is directly applied.

---

# Artificial Intelligence Architecture

Instead of relying on a single deep learning model, the system employs a modular multimodal architecture.

The visual branch consists of one-dimensional temporal convolutional layers followed by bidirectional recurrent networks or lightweight Transformers capable of modeling periodic blood flow dynamics.

The acoustic branch processes Mel spectrograms using convolutional neural networks that learn respiratory and phonocardiographic representations.

Before prediction, an adaptive attention mechanism evaluates the confidence of each sensing modality. Rather than assigning equal importance, the fusion network dynamically adjusts modality weights according to estimated signal quality. For example, under poor illumination the visual branch receives lower weight, whereas excessive environmental noise reduces reliance on acoustic features.

The fused latent representation is processed by multitask learning heads that simultaneously estimate heart rate, respiratory rate, heart-rate variability, stress index, and an overall physiological confidence score.

---

# Embedded Firmware

The ESP32 firmware implements deterministic real-time acquisition.

Tasks are separated using FreeRTOS. Independent tasks continuously capture camera frames and microphone samples while maintaining synchronized timestamps. Double buffering ensures uninterrupted streaming, and a communication task packages synchronized sensor data for transmission over Wi-Fi.

The firmware intentionally avoids computationally intensive signal processing, allowing future firmware updates to incorporate lightweight preprocessing or TinyML inference without architectural redesign.

---

# Desktop Platform

The desktop application functions as both an experimental environment and an end-user monitoring interface.

Researchers can visualize live physiological waveforms, inspect frequency spectra, evaluate signal quality, compare predicted values against ground truth, and analyze historical recordings. Interactive dashboards display recovered remote PPG signals, respiratory waveforms, spectrograms, heart-rate variability metrics, stress indices, and confidence scores. Data are stored in a structured database to facilitate reproducible experiments and statistical analysis.

---

# Expected Outputs

The completed platform will estimate heart rate, respiratory rate, heart-rate variability, stress level, signal quality, and a composite wellness index. More importantly, it will demonstrate how adaptive multimodal sensing improves robustness compared with individual sensing modalities under varying lighting conditions, user motion, and environmental noise.

---

# Research Contributions

The primary contribution is the development of a **low-cost embedded multimodal physiological sensing platform** that combines synchronized vision and acoustic sensing with adaptive AI-based fusion. A second contribution is the introduction of a signal-quality-aware fusion strategy that dynamically adjusts the influence of each sensing modality. The third contribution is a modular hardware–software architecture designed for future migration toward edge inference while remaining computationally practical for current embedded hardware.

---

## My assessment

This version is no longer just a semester project—it is a **research platform**. It spans embedded systems, digital signal processing, computer vision, machine learning, biomedical engineering, IoT, and edge computing in a technically coherent way.

One suggestion I would make before implementation is to **narrow the scope of the first paper**. Rather than attempting to estimate every possible vital sign, focus on **heart rate, respiratory rate, and signal-quality-aware adaptive fusion**. These are measurable, supported by available datasets, and sufficient to establish a strong research contribution. Features such as stress estimation, fatigue detection, or wellness scoring can then become natural extensions for subsequent publications. This phased approach is more likely to produce rigorous results and a publishable outcome than trying to solve too many problems in a single project.

I went through the proposal you uploaded. 

From a research perspective, **this is significantly stronger than a normal semester project**, but it is still at the **conceptual architecture stage**. It explains *what* the system is and *why* it is novel, but **it does not yet explain exactly how to engineer, validate, and publish it**.

If your goal is **a research-grade Signal & Systems project**, IEEE paper, or even future journal publication, then the work should be expanded into a complete engineering research project.


# What the final project should contain

Instead of building

> "An app that measures heart rate"

you should build

> **A complete Edge AI Biomedical Sensing System**

which includes

Hardware

↓

Signal Acquisition

↓

Signal Processing

↓

Machine Learning

↓

Sensor Fusion

↓

Performance Evaluation

↓

Research Paper

---

# Entire Research Flow

The project should follow an actual biomedical engineering research pipeline.

```
Research Problem

↓

Literature Survey

↓

Research Gap

↓

Objectives

↓

System Design

↓

Hardware Design

↓

Software Design

↓

Signal Processing

↓

Machine Learning

↓

Sensor Fusion

↓

Testing

↓

Validation

↓

Statistical Analysis

↓

Comparison with Existing Papers

↓

Future Work
```

This is exactly how IEEE biomedical papers are structured.

---

# Chapter 1

## Literature Survey

This alone should contain around **20–30 recent papers (2022–2026).**

Study areas include

Remote PPG

Microphone-based respiration

Signal processing

Biomedical DSP

TinyML

ESP32 AI

Edge Computing

Multimodal AI

Adaptive Sensor Fusion

Quality Assessment

Explain for each paper:

* objective
* dataset
* methodology
* algorithm
* sensors
* accuracy
* limitations

Then create one comparison table.

Example columns

| Paper | Sensor | AI | Accuracy | Limitation |
| ----- | ------ | -- | -------- | ---------- |

Then identify

**Research Gap**

This becomes your novelty.

---

# Chapter 2

## Problem Formulation

Instead of saying

"Estimate heart rate"

define mathematical problems.

Example

Given

Video

```
V(t)
```

Audio

```
A(t)
```

Estimate

Heart Rate

```
HR=f(V,A)
```

Respiration

```
RR=f(V,A)
```

Subject to

Motion

Lighting

Noise

Occlusion

Synchronization

This becomes an optimization problem.

---

# Chapter 3

## Hardware Design

This section should include actual engineering drawings.

Complete hardware block diagram

ESP32-S3

↓

OV2640 Camera

↓

INMP441

↓

OLED

↓

Battery

↓

USB

↓

Laptop

Then explain

GPIO allocation

Power distribution

Current consumption

Voltage levels

I2S timing

Camera timing

WiFi throughput

Memory utilization

FreeRTOS task scheduling

Latency

---

# Chapter 4

## Embedded Firmware

Not just

"ESP streams data"

Instead explain

Task 1

Camera

Task 2

Microphone

Task 3

WiFi

Task 4

Synchronization

Task 5

OLED

Task 6

Power

Task scheduling diagram

Interrupt handling

DMA

Double buffering

Ring buffers

Packet loss recovery

CRC

Timestamp synchronization

---

# Chapter 5

## Signal Processing

This is the most important chapter because your course is **Signals and Systems**.

Every step needs mathematical explanation.

### Video Pipeline

RGB extraction

↓

ROI Tracking

↓

CHROM

↓

POS

↓

ICA

↓

Detrending

↓

Normalization

↓

Bandpass

↓

FFT

↓

Peak Detection

↓

Heart Rate

---

### Audio Pipeline

Raw Audio

↓

Pre-emphasis

↓

Noise Removal

↓

Windowing

↓

STFT

↓

Mel Spectrogram

↓

Wavelets

↓

Respiratory Peaks

↓

Breathing Rate

Every filter should include equations.

Every transform should include mathematics.

---

# Chapter 6

## Artificial Intelligence

Instead of saying

"CNN"

Explain

Input

↓

Feature Extraction

↓

Temporal Learning

↓

Attention

↓

Fusion

↓

Output

Architecture example

```
Camera

↓

CNN

↓

LSTM

↓

Feature Vector

               ↘

                 Attention

               ↗

Microphone

↓

CNN

↓

Feature Vector

↓

Fusion

↓

Dense

↓

HR

RR

Confidence
```

---

# Chapter 7

## Sensor Fusion

This is actually your novelty.

You should mathematically explain

Early Fusion

Late Fusion

Feature Fusion

Decision Fusion

Adaptive Fusion

Confidence Weighting

Bayesian Fusion

Kalman Fusion

Attention Fusion

Then justify why

Adaptive Attention Fusion

is chosen.

---

# Chapter 8

## Dataset

Use both

Public Dataset

and

Your Own Dataset

Possible datasets include

* VIPL-HR
* UBFC-rPPG
* PURE
* COHFACE
* MMSE-HR

Then

collect

10–20 volunteers

using your hardware.

Now compare

Public

vs

Real World

---

# Chapter 9

## Experimental Setup

Explain

Lighting

Distance

Noise

Walking

Talking

Different Skin Tone

Mask

Glasses

Head Rotation

Motion

Night

Day

Indoor

Outdoor

All should become experiments.

---

# Chapter 10

## Performance Metrics

Do not only show accuracy.

Include

MAE

RMSE

MAPE

Precision

Recall

F1

Pearson Correlation

Signal-to-Noise Ratio

Latency

FPS

Power Consumption

Inference Time

Memory Usage

Communication Delay

Packet Loss

---

# Chapter 11

## Statistical Analysis

Biomedical papers require

Bland–Altman Plot

Regression

Confidence Interval

P-value

ANOVA

Correlation

Error Distribution

This distinguishes research from engineering.

---

# Chapter 12

## Comparison

Compare against

Camera Only

↓

Microphone Only

↓

Fusion

↓

Existing Papers

Show

Lighting

Motion

Noise

Accuracy

Robustness

Latency

Cost

---

# Chapter 13

## Future Work

Future improvements

TinyML

Edge Inference

Stress Detection

SpO₂

Blood Pressure Estimation

Sleep Monitoring

Emotion Recognition

ECG Fusion

Radar Fusion

Continuous Monitoring

Cloud Analytics

---

# Research Questions

Instead of one research question, define multiple:

1. Can multimodal sensing improve heart rate estimation under motion compared to camera-only methods?
2. Does adaptive signal-quality-aware fusion outperform fixed-weight fusion?
3. Can an ESP32-S3 reliably acquire synchronized multimodal physiological signals in real time?
4. What is the computational trade-off between edge acquisition and desktop inference?
5. How does lighting and environmental noise affect multimodal physiological sensing accuracy?

These become the backbone of your paper.

---

# Expected Deliverables

By the end of the project, you should have:

* A complete ESP32-S3 hardware prototype with camera, microphone, OLED, battery, and enclosure.
* Firmware for synchronized multimodal data acquisition using FreeRTOS.
* A desktop application for live visualization, recording, and analysis.
* Signal processing pipelines for remote PPG and respiratory audio extraction.
* A multimodal AI model for heart rate and respiratory rate estimation with adaptive sensor fusion.
* A custom dataset collected from volunteers, alongside experiments on public datasets.
* Comprehensive performance evaluation, statistical validation, and comparison with state-of-the-art methods.
* An IEEE-format research paper, presentation, and technical documentation.

## Overall assessment

This project has the potential to become much more than a course assignment. If executed rigorously, it aligns with undergraduate research suitable for IEEE conferences or biomedical engineering journals because it combines embedded systems, signal processing, computer vision, machine learning, IoT, and biomedical instrumentation into a single, coherent platform.

However, the key to making it publishable is **depth, not breadth**. Rather than adding more sensors or more predicted vital signs, focus on demonstrating that your **adaptive multimodal fusion** approach consistently outperforms camera-only and microphone-only systems under challenging conditions such as motion, poor lighting, and environmental noise. That evidence—not the number of features—is what will make the work scientifically valuable.
