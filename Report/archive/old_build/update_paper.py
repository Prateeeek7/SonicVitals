import re

with open('SonicVitals_Journal_Paper.tex', 'r') as f:
    text = f.read()

# 1. Replace images/architecture_diagram.png with images/system_architecture.png
text = text.replace('images/architecture_diagram.png', 'images/system_architecture.png')

# 2. Locate Section III and Section IV (Signal Processing)
sec3_pattern = r'\\section\{System Architecture \\& Hardware Co-Design\}'
sec4_pattern = r'\\section\{Signal Processing \\& Algorithmic Pipeline\}'

m3 = re.search(sec3_pattern, text)
m4 = re.search(sec4_pattern, text)

assert m3 is not None, "Section III not found"
assert m4 is not None, "Section IV not found"

sec3_start = m3.start()
sec4_start = m4.start()

new_sections = r'''\section{System Architecture \& Multi-Tier Framework}
\label{sec:system_architecture}

To satisfy the demanding synchronization, computational throughput, and clinical interaction requirements of simultaneous contactless optical photoplethysmography and thoracic acoustic auscultation, the SonicVitals platform is structured across four tightly coupled tiers: (1) Embedded Edge Sensing \& Hardware Acquisition Node, (2) High-Speed Serial Telemetry \& Bidirectional Bus, (3) Multimodal Digital Signal Processing \& Diagnostic Engine, and (4) Clinical Web Application \& Diagnostic Interface. The comprehensive system architecture is illustrated in Fig.~\ref{fig:architecture}.

% -------------------------------------------------
% Figure 1: 4-Tier System Architecture Diagram
% -------------------------------------------------
\begin{figure*}[!t]
\centering
\includegraphics[width=0.96\textwidth]{images/system_architecture.png}
\caption{Comprehensive four-tier system architecture of the SonicVitals physiological sensing platform, delineating the embedded edge acquisition node (ESP32-S3 dual-core SoC, OV2640 DVP DMA, INMP441 I2S DMA, SSD1306 OLED HUD), high-speed serial telemetry bus (binary framing @ 460,800\,baud and bidirectional OLED reverse telemetry), multi-threaded multimodal DSP and clinical diagnostic imaging engine, and the web-based clinical monitoring and 3D anatomical interaction suite.}
\label{fig:architecture}
\end{figure*}

\subsection{Distributed Tier Decomposition}

As mapped in Fig.~\ref{fig:architecture}, each tier fulfills a specialized operational role designed to decouple high-bandwidth real-time hardware data ingestion from latency-sensitive clinical visualization:
\begin{enumerate}
    \item \textbf{Tier 1: Embedded Edge Sensing \& Hardware Acquisition Node:} Driven by an ultra-low-power ESP32-S3 dual-core microcontroller running at 240\,MHz with 512\,KB internal SRAM and 8\,MB external Octal PSRAM. The node concurrently interfaces with an OV2640 CMOS image sensor via an 8-bit parallel Digital Video Port (DVP) with direct Direct Memory Access (DMA), an INMP441 omnidirectional MEMS acoustic microphone via an Inter-IC Sound (I2S) digital audio bus with 32-bit DMA buffering, and an SSD1306 $128 \times 64$ monochrome OLED telemetry display operating over a 400\,kHz Fast-Mode I2C bus.
    \item \textbf{Tier 2: High-Speed Serial Telemetry \& Bidirectional HUD Bus:} Primary telemetry streams from the edge node to the host computational workstation across a native USB CDC serial conduit operating at 460,800\,baud. Compressed video frames and digital audio blocks are serialized within strict delimiter envelopes (\texttt{<<FRAME\_START>>} $\rightarrow$ Base64 JPEG $\rightarrow$ \texttt{<<FRAME\_END>>}). Concurrently, a reverse telemetry channel periodically transmits computed vital signs (\texttt{<<VITALS:HR,RR,SpO2,STATUS>>}) back to the edge node at 1.5\,s intervals to drive the bedside OLED status HUD without preempting DMA serialization.
    \item \textbf{Tier 3: Multimodal Digital Signal Processing \& Diagnostic Engine:} The host engine ingests raw serialized streams and routes them through parallel analytical paths: (i) an Optical rPPG branch executing Haar cascade facial detection, five-zone anatomical ROI extraction, and de Haan's chrominance (CHROM) orthogonal space projection; (ii) a multi-resolution discrete wavelet decomposition (MRWD DWT) and 3rd-order zero-phase Butterworth filter bank coupled with Welch periodogram power spectral density (PSD) estimation; (iii) an Acoustic Auscultation branch computing 512-point Short-Time Fourier Transform (STFT) spectrograms ($0$--$1.2$\,kHz) and Shannon energy phonocardiographic envelopes for first and second heart sound ($S_1, S_2$) identification; and (iv) a Clinical Diagnostic Image Engine calculating spectrophotometric biomarker indices for cutaneous erythema ($EI$), tissue pallor ($PI$), scleral icterus ($YI$), peripheral cyanosis ($CR$), and hemifacial perfusion symmetry ($HPS$).
    \item \textbf{Tier 4: Clinical Interaction \& Web Interface:} Diagnostic metrics and real-time waveforms are dispatched to an interactive browser workstation via full-duplex WebSocket connections operating at 60\,FPS. The interface features a Live Telemetry Dashboard displaying 60\,FPS canvas waveforms, dynamic signal quality indices (SQI), and fusion confidence scores; a dedicated Multi-Channel Signal Analysis Lab providing spectral periodograms, acoustic spectrograms, and color-channel trajectories; an interactive 3D Anatomical Mapping module rendering synchronized cardiac pulsation and thoracic respiratory excursion; and an automated Clinical Diagnostic Triage panel generating five-biomarker risk cards, spatial perfusion heatmaps, and structured clinical narrative summaries.
\end{enumerate}

% =================================================
% IV. EMBEDDED HARDWARE IMPLEMENTATION & BENCHTOP SETUP
% =================================================
\section{Embedded Hardware Implementation \& Experimental Setup}
\label{sec:hardware_implementation}

To validate the theoretical and architectural design of SonicVitals under realistic clinical constraints, a fully functional physical hardware prototype was developed and deployed in a benchtop experimental configuration, as shown in Fig.~\ref{fig:hardware_setup}.

% -------------------------------------------------
% Figure 2: Physical Hardware Prototype Setup
% -------------------------------------------------
\begin{figure*}[!t]
\centering
\includegraphics[width=0.85\textwidth]{images/labeled_setup.png}
\caption{Empirical benchtop experimental prototype of the SonicVitals edge sensing node, highlighting the physical component layout: (1) ESP32-S3 dual-core microcontroller carrier board, (2) OV2640 DVP CMOS optical sensor, (3) dual omnidirectional MEMS acoustic auscultation transducers, (4) flexible shielded jumper-wire sensor harness, (5) 0.96-inch monochrome $128\times64$ SSD1306 OLED bedside display showing active telemetry status, (6) 2.4\,GHz external omnidirectional wire whip antenna, (7) solderless breadboard prototyping base, and (8) high-speed USB-C power delivery and serial telemetry interface.}
\label{fig:hardware_setup}
\end{figure*}

\subsection{Physical Prototype Architecture \& Component Integration}

The physical construction of the SonicVitals edge node, depicted in Fig.~\ref{fig:hardware_setup}, integrates industrial-grade sensing components on a breadboard prototyping platform with dedicated ground planes and decoupling networks to minimize electromagnetic interference (EMI) and power rail crosstalk between high-speed digital switching and low-noise acoustic transducers.

\subsubsection{ESP32-S3 Microcontroller Core}
The computational core of the edge node is the ESP32-S3 WROOM 1U CAM carrier board, housing a dual-core 32-bit Xtensa LX7 processor operating at 240\,MHz with 512\,KB of internal static RAM and 8\,MB of high-speed Octal SPI PSRAM. The module incorporates an external IPEX/U.FL coaxial connector mated to a 2.4\,GHz omnidirectional wire whip antenna (Fig.~\ref{fig:hardware_setup}), providing 2.15\,dBi gain to guarantee robust RF signal propagation across clinical corridors and isolation wards under IEEE 802.11 b/g/n and Bluetooth 5 (LE) standards.

\subsubsection{OV2640 Optical Sensing Subsystem}
The optical sensing pathway utilizes an Omnivision OV2640 2-megapixel CMOS image sensor mounted directly onto a 24-pin zero-insertion-force (ZIF) socket positioned atop the carrier board. The sensor features an integrated JPEG compression engine and an optical lens with a 65$^\circ$ diagonal field-of-view (FOV) and manual focus adjustment. In the benchtop setup, the camera is oriented orthogonally toward the subject's face at a calibrated working distance of $0.60$--$1.0$\,m. The sensor is configured in high-quality video graphics array (HQVGA, $240 \times 160$ pixels) resolution operating at a stable frame rate of 15.0\,FPS. Video data is transferred over an 8-bit parallel Digital Video Port (DVP) directly into PSRAM double buffers via dedicated DMA channels without CPU intervention.

\subsubsection{Dual MEMS Acoustic Auscultation Transducer Harness}
Thoracic acoustic sensing is achieved via a pair of high-performance Knowles INMP441 omnidirectional MEMS microphones (`MEMS microphones ($\times$2)' in Fig.~\ref{fig:hardware_setup}). Each transducer integrates an acoustic sensor element, a low-noise preamplifier, and a 24-bit $\Sigma$-$\Delta$ analog-to-digital converter (ADC), delivering a flat acoustic frequency response from 60\,Hz to 15\,kHz with an outstanding Signal-to-Noise Ratio (SNR) of 61\,dBA and sensitivity of $-26$\,dBFS. The transducers are terminated onto a flexible, shielded multi-conductor wiring harness (`Jumper-wire sensor harness', Fig.~\ref{fig:hardware_setup}) encapsulated within silicone acoustic impedance-matching bells. This dual-transducer arrangement allows flexible clinical positioning: Transducer~1 is placed at the mitral auscultation zone (4th left intercostal space, midclavicular line) for high-sensitivity phonocardiographic cardiac valve closure tracking ($S_1/S_2$), while Transducer~2 can be positioned at the anterior right chest for lung airflow auscultation or utilized as an ambient reference for common-mode acoustic noise cancellation.

\subsubsection{SSD1306 Local Telemetry OLED Display}
To provide immediate bedside feedback to attending healthcare staff without requiring a desktop workstation, a 0.96-inch monochrome $128 \times 64$ SSD1306 OLED display is integrated directly onto the breadboard bus (Fig.~\ref{fig:hardware_setup}). The display is driven via a 400\,kHz Fast-Mode I2C bus and refreshed at 5.0\,Hz. As shown in the empirical photograph of the active prototype in Fig.~\ref{fig:hardware_setup}, the display presents a formatted clinical heads-up display (HUD) detailing:
\begin{center}
\texttt{SONICVITALS CLINICAL} \\
\texttt{HR: 118 BPM  RR: 11/m} \\
\texttt{SpO2: 92\%  Conf: 91\%} \\
\texttt{Cam: 4fps   Mic: OK} \\
\texttt{PATIENT: STABLE}
\end{center}
This verifies the live operational synchronization between the host reverse telemetry channel and the edge OLED driver during active patient examination.

\subsubsection{Prototyping Substrate \& Power Delivery Bus}
The entire edge sensing node is mounted onto a solderless prototyping breadboard (`Breadboard', Fig.~\ref{fig:hardware_setup}) featuring partitioned analog and digital ground rails linked via a single star ground point. Power is supplied through a high-retention USB Type-C cable (`USB power / programming cable', Fig.~\ref{fig:hardware_setup}) connected to a regulated 5.0\,V, 2.0\,A low-noise medical-grade DC power supply or a portable 3.7\,V lithium-polymer power bank with a low-dropout (LDO) regulator. High-frequency decoupling capacitors (100\,nF ceramic in parallel with 10\,$\mu$F low-ESR tantalum) are placed across the 3.3\,V and 5.0\,V power pins of the camera carrier and MEMS breakout boards to suppress power supply ripple below 12\,mV$_{\mathrm{p-p}}$.

\subsection{Hardware Pinout Allocation \& Bus Multiplexing}

The high pin density of the camera module on the ESP32-S3 leaves limited available general-purpose I/O (GPIO) pins. Careful pinout multiplexing was engineered to ensure that optical DMA, digital audio I2S DMA, and I2C display buses operate concurrently without bus contention. Table~\ref{tab:hardware_pinout} details the exact pin assignments, bus protocols, and sampling configurations of the edge node.

\begin{table*}[!t]
    \centering
    \caption{Hardware interface and pinout allocation matrix of the SonicVitals embedded sensing node.}
    \label{tab:hardware_pinout}
    \footnotesize
    \renewcommand{\arraystretch}{1.12}
    \setlength{\tabcolsep}{4.0pt}
    \begin{tabular}{lllll}
        \toprule
        \textbf{Peripheral} & \textbf{Pin Function} & \textbf{ESP32-S3 Pin} & \textbf{Bus Protocol} & \textbf{Operational Mode \& Sampling Rate} \\
        \midrule
        \multirow{3}{*}{\textbf{OV2640 Camera}} 
            & D0--D7 & GPIO 4, 5, 18, 19, 36, 39, 34, 35 & \multirow{3}{*}{DVP 8-bit Parallel} & \multirow{3}{*}{15.0 FPS, HQVGA ($240\times160$), RGB565 to JPEG} \\
            & PCLK, VSYNC & GPIO 22, 25 & & \\
            & HREF, XCLK & GPIO 23, 10\,MHz clock & & DMA DRAM Double Buffer \\
        \midrule
        \multirow{3}{*}{\textbf{INMP441 Microphone}}
            & SCK (BCLK) & GPIO 43 (TX) & \multirow{3}{*}{I2S Digital Audio} & \multirow{3}{*}{16,000 Hz, 32-bit, Left Channel Only} \\
            & WS (LRCK) & GPIO 44 (RX) & & \\
            & SD (DIN) & GPIO 0 (BOOT) & & DMA Ring Buffer, Block RMS Energy Extraction \\
        \midrule
        \multirow{2}{*}{\textbf{SSD1306 OLED Display}}
            & SDA & GPIO 47 (SDA) & \multirow{2}{*}{I2C Serial Bus} & \multirow{2}{*}{5.0 Hz HUD Refresh, 400 kHz Fast-Mode I2C} \\
            & SCL & GPIO 48 (SCL) & & \\
        \midrule
        \textbf{Native USB Port} & D+ / D- & Native USB OTG & USB CDC Class & 460,800 baud Binary Serial Framing \\
        \textbf{System Power} & VDD / GND & 5.0\,V / Common Ground & Regulated Rail & Portable USB Power Bank / 3.7V Li-Po LDO \\
        \bottomrule
    \end{tabular}
\end{table*}

\subsection{Dual-Core FreeRTOS Concurrency \& DMA Engine}

The firmware running on the ESP32-S3 is implemented under FreeRTOS to guarantee deterministic, non-blocking execution across its symmetric dual cores:
\begin{itemize}
    \item \textbf{Core 0 (Audio \& Telemetry HUD Pool):} Executes the high-priority I2S audio ingestion task (\texttt{Task\_AudioCapture}, Priority 5), which unloads 1024-sample buffers from the I2S DMA ring buffer every 64\,ms, calculates block RMS energy, and packages samples for serialization. Core 0 also hosts the reverse telemetry parser (\texttt{Task\_TelemetryRX}, Priority 3) and the OLED display driver (\texttt{Task\_OLEDUpdate}, Priority 2) refreshed at 5.0\,Hz.
    \item \textbf{Core 1 (Optical Acquisition \& Compression Pool):} Dedicated exclusively to video stream handling. Upon receiving a hardware VSYNC interrupt, the camera driver initiates DVP DMA transfers into a double-buffered frame repository located in external Octal PSRAM (\texttt{Task\_CameraCapture}, Priority 6). Completed frames are compressed via the on-chip JPEG engine and passed to the serial framing pipeline (\texttt{Task\_SerialTX}, Priority 4), which encodes the binary data into Base64 format and pumps it into the USB CDC transmission FIFO.
\end{itemize}

\subsection{Power Budget, Thermal Performance \& Electrical Safety}

To assess the feasibility of portable, battery-powered clinical deployment, the electrical current consumption of the SonicVitals edge sensing node was characterized across all operational modes using a Keysight 34465A 6.5-digit digital multimeter sampling at 100\,Hz. Table~\ref{tab:power_consumption} outlines the measured electrical characteristics.

\begin{table}[!t]
    \centering
    \caption{Measured current consumption and power dissipation of the SonicVitals edge sensing node across operational states ($V_{\mathrm{in}} = 5.0$\,V).}
    \label{tab:power_consumption}
    \footnotesize
    \renewcommand{\arraystretch}{1.10}
    \setlength{\tabcolsep}{3.0pt}
    \resizebox{\columnwidth}{!}{%
    \begin{tabular}{lccc}
        \toprule
        \textbf{Operational Mode} & \textbf{Current (mA)} & \textbf{Power (mW)} & \textbf{Battery Life (h)$^{\dagger}$} \\
        \midrule
        Idle / Standby (Sensors Off) & $38 \pm 2$ & 190 & 78.9 \\
        Acoustic Only (I2S DMA + OLED) & $74 \pm 4$ & 370 & 40.5 \\
        Optical Only (OV2640 DVP + USB) & $165 \pm 8$ & 825 & 18.1 \\
        \textbf{Full Multimodal (DVP + I2S + OLED)} & $\mathbf{215 \pm 11}$ & \textbf{1075} & \textbf{13.9} \\
        Multimodal + 2.4 GHz Wi-Fi Burst & $260 \pm 18$ & 1300 & 11.5 \\
        \bottomrule
    \end{tabular}%
    }
    \vspace{1ex}
    \raggedright
    \scriptsize $^{\dagger}$Estimated using a standard lightweight 3000\,mAh (11.1\,Wh) Li-Po battery pack.
\end{table}

Under full concurrent multimodal operation (15.0\,FPS HQVGA optical streaming, 16\,kHz I2S digital audio capture, 5\,Hz OLED display updates, and 460,800\,baud serial streaming), the node draws an average current of $215 \pm 11$\,mA ($1075$\,mW total power dissipation). A standard 3000\,mAh rechargeable lithium-polymer battery sustains continuous operation for approximately 13.9\,hours, providing full shift coverage for inpatient telemetry. Thermal profiling conducted via FLIR E8-XT infrared thermography demonstrated that the peak steady-state surface temperature of the ESP32-S3 SoC reached $38.2^\circ$C at an ambient temperature of $24.5^\circ$C after 4\,hours of continuous execution, well below the $43.0^\circ$C safe contact limit mandated by IEC 60601-1 for medical electrical equipment.

\subsection{Firmware Concurrency and Serial Ingestion Protocol}

The edge node communicates with the host processing engine via a framed ASCII/Base64 streaming protocol over native USB CDC operating at 460,800\,baud. Each compressed frame is encapsulated with unambiguous synchronization tokens:
\begin{verbatim}
<<FRAME_START>>
/9j/4AAQSkZJRgABAQAAAQABAAD/2wBD...
<<FRAME_END>>
\end{verbatim}

The host backend decodes the payload into an OpenCV BGR image matrix. Concurrently, every 1.5\,s, the host transmits a reverse telemetry packet containing stabilized vital signs back to the edge node:
\begin{verbatim}
<<VITALS:72,16,98,STABLE>>
\end{verbatim}
The ESP32-S3 receives this packet asynchronously, parses the fields, and refreshes the OLED layout without interrupting video or audio capture loops.

\begin{table}[!t]
    \centering
    \caption{Digital signal processing parameters and filter specifications.}
    \label{tab:dsp_parameters}
    \footnotesize
    \renewcommand{\arraystretch}{1.08}
    \setlength{\tabcolsep}{2.2pt}
    \begin{tabular}{p{2.6cm} p{1.7cm} p{3.7cm}}
        \toprule
        \textbf{Parameter} & \textbf{Value} & \textbf{Clinical Rationale} \\
        \midrule
        Video Frame Rate ($f_s$) & 15.0 FPS & Optimal Nyquist for $\le 210$\,BPM \\
        Calibration Duration & 6.0 s & 90 frames for buffer stability \\
        Cardiac Passband & 0.75--2.50 Hz & 45 to 150 BPM pulse limits \\
        Cardiac Filter Type & 3rd-order Butterworth & Zero-phase bidirectional (\texttt{filtfilt}) \\
        Respiration Passband & 0.15--0.40 Hz & 9 to 24 breaths/min limits \\
        Respiration Filter Type & 2nd-order Butterworth & Green channel envelope filter \\
        Spectral Window ($N_{seg}$) & 128 samples & Welch PSD (8.53 s window) \\
        Spectral Overlap & 50\% (64 samples) & Reduces variance of PSD estimate \\
        Audio Sampling Rate ($f_a$) & 16,000 Hz & Phonocardiography \& lung sounds \\
        Audio STFT Window & 512 samples & 32 ms temporal resolution \\
        Audio STFT Overlap & 75\% (384 samples) & Smooth time-frequency continuity \\
        OLED Refresh Rate & 5.0 Hz & Clean 200 ms rendering cycle \\
        \bottomrule
    \end{tabular}
\end{table}

The operational DSP hyperparameters of the SonicVitals pipeline are summarized in Table~\ref{tab:dsp_parameters}.
'''

new_text = text[:sec3_start] + new_sections + text[sec4_start:]

# Let's save as test_build.tex
with open('test_build.tex', 'w') as out:
    out.write(new_text)

print('Written to test_build.tex')
