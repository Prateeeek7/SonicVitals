"""Text of the SonicVitals final project report (laid out by build_report.py into the university template).

Block types: ('h1', title) chapter on a new page; ('h2', title); ('h3', title); ('p', text);
('bullets', [items]); ('fig', image path, caption, width cm); ('table', caption, rows, col widths cm);
('eq', text). Every number reported here is a measured value from the benchmark files, the automated
tests or the live sessions recorded during development.
"""
import glob
import os

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, 'figs')
IMG = os.path.join(os.path.dirname(HERE), 'Images')


def shot(stamp):
    return glob.glob(os.path.join(IMG, f'Screenshot 2026-10-22 at {stamp}*'))[0]


TITLE = 'SonicVitals: Contactless Vital-Sign Sensing with a Low-Cost Optical–Acoustic Edge Node, Skin-Metered Exposure Control and Quality-Gated Remote Photoplethysmography'

EXEC_SUMMARY = (
    'SonicVitals is a low-cost, contactless system that estimates heart rate, breathing rate and related physiological '
    'indicators from ordinary video of the face. An ESP32-S3 edge node with a GC2145 camera, an INMP441 MEMS microphone '
    'and an SSD1306 display streams raw skin colour sums, video and audio over Wi-Fi to a Python processing engine; the '
    'laptop webcam can be used as an alternative camera. The engine tracks the face with sub-pixel motion compensation, '
    'extracts the blood-volume pulse with three classical remote-photoplethysmography (rPPG) methods and three deep '
    'networks, and reports a heart rate only when independent methods agree, flagging values that change faster than '
    'physiology allows. Breathing rate is fused from four independent signals, and the dashboard adds camera heart-rate '
    'variability, a blood-flow (perfusion) map, a liveness check, blink rate, head steadiness and colorimetric skin '
    'indices. On the public UBFC-rPPG dataset the quality-gated SonicVitals estimate reached a mean absolute error of '
    '1.56 BPM (RMSE 2.73 BPM, r = 0.99) on 30-second windows, better than CHROM, POS and three cross-dataset deep '
    'models. The complete pipeline runs in real time at about 30 frames per second on a laptop.')

CONTENT = [
    # ------------------------------------------------------------------ 1
    ('h1', '1. INTRODUCTION'),
    ('p', 'Vital signs such as heart rate and breathing rate are the first measurements taken in almost every clinical and '
          'wellness setting. They are normally obtained with contact sensors: a pulse oximeter clip, ECG electrodes or a '
          'chest belt. Contact sensors are accurate, but they need to be attached, cleaned and powered, they can irritate '
          'fragile skin (newborns, burn patients, the elderly), and they are inconvenient for continuous monitoring of '
          'people who are working, studying or driving. A sensor that can measure the same quantities from a distance, '
          'using only a camera, removes these barriers.'),
    ('p', 'Remote photoplethysmography (rPPG) makes this possible. With every heartbeat the volume of blood in the skin '
          'increases slightly; blood absorbs green light strongly, so the skin becomes marginally darker and redder at '
          'each systole. The change is tiny, typically 0.1-0.5 % of the skin brightness, invisible to the eye but '
          'measurable by an ordinary camera when many pixels are averaged over time [1], [24]. Breathing modulates the '
          'same signal and moves the head and shoulders, so the breathing rate can be recovered from the same video. '
          'This project, SonicVitals, builds a complete contactless monitoring system around this principle: a custom '
          'edge sensor node, a signal-processing engine that combines classical and deep-learning methods, and a '
          'real-time web dashboard that explains how every value was obtained and how much it can be trusted.'),
    ('h2', '1.1 Literature Review'),
    ('p', 'Verkruysse et al. first showed that the pulse can be measured from a consumer camera under ambient light, '
          'with the green channel carrying the strongest signal [1]. Poh et al. applied blind source separation to the '
          'red, green and blue channels of a webcam and later extended the approach to breathing rate and heart-rate '
          'variability [2], [3]. These early methods are sensitive to motion and lighting changes, because any change '
          'in illumination or in the angle of the skin also changes the colour of the pixels.'),
    ('p', 'Model-based methods address this weakness by exploiting the known colour properties of skin. The CHROM '
          'method of de Haan and Jeanne builds two chrominance signals in which specular reflections and intensity '
          'changes cancel, and combines them with a ratio that adapts to the signal [4]. The POS method of Wang et al. '
          'projects the normalised colour signal onto a plane orthogonal to the skin tone, which is more robust to '
          'varying skin tones and illumination [5]. Both methods remain the reference baselines in the field. '
          'Li et al. added illumination rectification, using the background as a reference for lighting changes that '
          'affect skin and background alike [21].'),
    ('p', 'Deep-learning methods learn the mapping from face video to pulse directly. TS-CAN uses a two-branch '
          'attention network with temporal shift modules [9], PhysNet uses a 3-D spatio-temporal convolutional network '
          '[10] and EfficientPhys uses a single-branch network with built-in normalisation [11]. The rPPG-Toolbox '
          'provides pretrained models and a common evaluation protocol on public datasets such as UBFC-rPPG [6], PURE '
          '[7] and VIPL-HR [8], [12], and pyVHR offers a framework for classical methods including spatial fusion of '
          'many skin patches [13]. A recurring finding is that deep models perform very well on the dataset they were '
          'trained on but lose accuracy across datasets, cameras and skin tones [12], [22].'),
    ('p', 'Robust heart-rate tracking from noisy spectra has been studied for wrist photoplethysmography: TROIKA tracks '
          'spectral peaks over time and rejects implausible jumps [14]. For breathing, Karlen et al. showed that three '
          'respiratory modulations of the PPG (intensity, amplitude and frequency variation) can be fused, accepting a '
          'rate only when the modulations agree [15]; Tarassenko et al. demonstrated camera-based monitoring in a '
          'clinical setting [16]. Kamshilin et al. introduced photoplethysmographic imaging, mapping the pulse '
          'amplitude over the skin to visualise blood perfusion [17]. Soukupova and Cech measured blinks with the eye '
          'aspect ratio of facial landmarks [18], which MediaPipe makes available in real time [19]. Heart-rate '
          'variability standards are defined by the Task Force of the ESC and NASPE [23].'),
    ('h2', '1.2 Research Gap'),
    ('p', 'The literature leaves several practical gaps that this project addresses:'),
    ('bullets', [
        'Most rPPG work reports accuracy on curated datasets, but a deployed system must decide in real time whether a '
        'given reading is trustworthy. Few systems expose a quality gate, and fewer explain to the user why a value '
        'is shown, held or withheld.',
        'Classical and deep-learning methods are usually compared offline. A live system that runs both side by side '
        'on the same face, and uses their agreement as evidence, is rarely described.',
        'Low-cost embedded hardware is seldom combined with rPPG; most systems rely on a laptop webcam. Edge nodes that '
        'compute skin statistics before video compression, and control camera exposure for the skin, are uncommon.',
        'Secondary indicators (breathing pattern, camera HRV, perfusion mapping, liveness, blink rate) are usually '
        'studied separately rather than delivered together, each with an honest statement of its confidence.',
    ]),
    ('h2', '1.3 Problem Statement'),
    ('p', 'Design and implement a contactless, low-cost vital-sign monitoring system that measures heart rate and '
          'breathing rate from face video in real time, works with both an embedded edge camera node and a standard '
          'webcam, rejects motion and lighting artifacts, reports how much each value can be trusted, and provides '
          'additional physiological and behavioural indicators on a clear, explainable dashboard. The accuracy of the '
          'heart-rate estimate must be validated against contact reference measurements on a public dataset.'),
    ('h3', '1.3.1 Relevance of the problem statement w.r.t. SDG'),
    ('p', 'The project is most directly aligned with Sustainable Development Goal 3, Good Health and Well-being: '
          'contactless screening lowers the cost and effort of routine vital-sign checks, supports remote and '
          'continuous monitoring, and avoids contact-sensor hygiene problems. It also contributes to SDG 9, Industry, '
          'Innovation and Infrastructure, through an open, low-cost hardware and software design that can be built '
          'from commodity parts, and to SDG 10, Reduced Inequalities, because the system needs no specialised medical '
          'equipment and can run on hardware that costs a few thousand rupees.'),

    # ------------------------------------------------------------------ 2
    ('h1', '2. PROJECT OBJECTIVE'),
    ('p', 'The objectives of the project are:'),
    ('bullets', [
        'To build an ESP32-S3 edge sensor node with a camera, a MEMS microphone and an OLED display that streams '
        'synchronised physiological data to a host computer over Wi-Fi.',
        'To estimate heart rate from face video using classical rPPG methods (CHROM, POS, GREEN) with motion '
        'compensation, artifact repair, illumination rectification and a signal-quality gate.',
        'To run three pretrained deep-learning rPPG models live alongside the classical methods and combine all of '
        'them into one robust heart-rate output that is held and flagged when it changes implausibly fast.',
        'To estimate breathing rate by fusing several independent respiratory signals, and to classify the breathing '
        'pattern as regular, irregular or paused.',
        'To derive secondary indicators from the same video: camera heart-rate variability, a blood-flow (perfusion) '
        'map with perfusion index, a liveness check, blink rate and head steadiness, together with colorimetric '
        'skin indices in a diagnostics studio.',
        'To design a real-time web dashboard in which every value carries a clear status, and to validate the '
        'heart-rate accuracy on the public UBFC-rPPG dataset against contact PPG references.',
    ]),

    # ------------------------------------------------------------------ 3
    ('h1', '3. PROPOSED WORK'),
    ('p', 'SonicVitals is organised in three tiers: an embedded edge node that acquires and pre-processes the sensor '
          'data, a host signal-processing engine that turns the data into physiological measurements, and a web '
          'dashboard that presents the results. Figure 3.1 shows the architecture and Figure 3.2 the processing '
          'pipeline from camera frame to displayed value.'),
    ('fig', os.path.join(FIG, 'architecture.png'), 'Fig. 3.1: SonicVitals system architecture', 16.0),
    ('h2', '3.1 Design Approach / System Model / Algorithm'),
    ('h3', '3.1.1 Edge sensor node'),
    ('p', 'The edge node is built around an ESP32-S3 microcontroller with external PSRAM. The GC2145 camera captures '
          'RGB565 frames at 240 x 160 pixels and 10 frames per second. Because the GC2145 has no hardware JPEG encoder, '
          'the node computes the skin statistics on the raw pixels before any compression: for each skin box sent by '
          'the host it sums the red, green and blue values, excluding saturated and near-black pixels, and streams the '
          'sums for every frame (10 Hz). Every second frame is compressed in software to JPEG at quality 65 and sent as '
          'video (5 fps) for face detection and display. The node also controls the camera exposure through the sensor '
          'registers, following a host controller that meters the brightness of the skin (target level 165 out of 255), '
          'so that the face is neither clipped nor too dark.'),
    ('p', 'The INMP441 MEMS microphone is read over I2S at 16 kHz, low-pass filtered with a 63-tap FIR filter and '
          'decimated to 4 kHz before streaming. The SSD1306 OLED display shows the heart rate, breathing rate and '
          'status sent back by the host. All data use a line-based protocol over a TCP connection on port 3333: '
          '<<FRAME>> for video, <<RGB>> for skin sums, <<AUDIO>> for sound blocks and <<INFO>> for diagnostics; the host '
          'sends <<ROI>> boxes, <<CAM:EXP>> exposure commands and <<VITALS>> for the display. Every record carries a '
          'microsecond timestamp from the node clock, so video, skin sums and audio share one time base.'),
    ('h3', '3.1.2 Face detection, skin regions and motion compensation'),
    ('p', 'Each frame is converted to grey scale and searched for faces with a Haar cascade classifier [20] on a '
          'copy reduced to 320 pixels width. Detection runs on every third frame while a face is present; between '
          'detections the face is followed by the tracker described below. A full-face gate accepts a frame only when '
          'the whole face is inside the image with a margin of 3.5 %, occupies at least 20 % of the width and 22 % of '
          'the height (and at most 88-90 %), and has a width-to-height ratio of at least 0.65; otherwise the operator '
          'receives guidance such as "Chin is cut off at bottom".'),
    ('p', 'Four skin regions are placed relative to the face box: the forehead (20-80 % of the width, 11-26 % of the '
          'height), both cheeks (below the eyes, above the beard line) and the nose. A YCrCb skin mask computed once '
          'for each region removes hair, eyebrows and beard. To keep the regions on the same skin while the head moves '
          'by a few pixels, the face is tracked by sub-pixel phase correlation [29]: a 96 x 96 grey template of the face '
          'is stored when the regions are locked, and every frame is registered against it with a Hann window. The '
          'regions are then sampled at the measured shift with sub-pixel interpolation. The regions are re-locked only '
          'if the face moves by more than 25 % of its width or the tracker loses confidence for eight frames.'),
    ('h3', '3.1.3 Signal conditioning'),
    ('p', 'The mean skin colour of the regions forms three time series (R, G, B). They are resampled to a uniform '
          '15 Hz grid from their true timestamps; gaps up to 2 s are bridged. Motion and region re-locks appear as '
          'jumps far larger than the pulse; they are repaired in the derivative domain: frame-to-frame changes of the '
          'log-colour larger than four robust standard deviations (median absolute deviation) are set to zero and the '
          'signal is re-integrated. When a clear movement occurred, only the still stretch after it is analysed if it '
          'lasts at least 12 s. Lighting changes that affect both the skin and the background are removed by '
          'illumination rectification [21]: the relative skin change is regressed on the relative change of non-skin '
          'background strips in the 0.6-3 Hz band and the common part is subtracted. The rectification is applied only '
          'when the background carries a real lighting change (at least 30 % of the skin band power); otherwise pulse '
          'leaking into the background strips would be subtracted from the skin.'),
    ('h3', '3.1.4 Pulse extraction and quality gate'),
    ('p', 'Three pulse extractors run on the conditioned signal. CHROM [4] normalises each channel by its mean over a '
          'sliding 3 s window and forms'),
    ('eq', 'X = 3R - 2G,   Y = 1.5R + G - 1.5B,   S = X - (sigma_X / sigma_Y) Y'),
    ('p', 'with overlap-add of the windows. POS [5] uses 1.6 s windows and projects the normalised colour onto the '
          'plane orthogonal to the skin tone:'),
    ('eq', 'S1 = G - B,   S2 = -2R + G + B,   P = S1 + (sigma_S1 / sigma_S2) S2'),
    ('p', 'GREEN is the inverted green channel [1]. The CHROM pulse is band-pass filtered between 0.75 and 2.5 Hz '
          '(45-150 beats per minute) and its power spectrum is estimated with Welch\'s method [25] (256-sample segments, '
          '4096-point FFT). The heart rate is the strongest spectral peak, refined by parabolic interpolation; when a '
          'previous accepted value exists, a peak within 12 BPM of it is preferred if it holds at least half the power '
          'of the global peak. Peaks that are equally strong in the background spectrum are skipped as lighting. '
          'Signal quality is measured with the signal-to-noise ratio of de Haan and Jeanne [4]:'),
    ('eq', 'SNR = 10 log10 [ P(|f - f0| <= 0.1 Hz  or  |f - 2f0| <= 0.2 Hz) / P(rest of 0.5-4 Hz) ]'),
    ('p', 'An estimate passes the quality gate when the SNR is at least -2 dB, both POS and GREEN find the CHROM peak '
          'within 6 BPM (method consensus), at least 80 % of the segment is backed by real frames and at most 15 % of '
          'it had to be repaired.'),
    ('h3', '3.1.5 Spectral tracking, deep models and robust consensus'),
    ('p', 'For a continuous estimate the spectra of the four skin regions and three extractors (twelve spectra) are '
          'normalised and combined by their median, following the spatial fusion of pyVHR [13]. A discrete Bayes '
          'filter on a 0.5 BPM grid between 45 and 150 BPM tracks the heart rate over time in the spirit of TROIKA '
          '[14]: the probability is propagated with a Gaussian drift of 3 BPM per 2 s update, 2 % of it may jump '
          'anywhere, and the sharpened ensemble spectrum is the likelihood. The confidence is the probability mass '
          'within +/-3 BPM of the most probable rate.'),
    ('p', 'Three deep models from the rPPG-Toolbox [12] run in a background thread on the last 30 s of face crops '
          '(the face box enlarged 1.5 times, resized to 72 x 72 pixels and interpolated to 30 Hz): TS-CAN [9], PhysNet '
          '[10] and EfficientPhys [11], all trained on the PURE dataset. They are updated every 12 s and need at least '
          '12 fps video, so they run with the webcam. The displayed heart rate is the robust average of all methods: '
          'the median of the available rates selects the majority, methods within 8 BPM of it are averaged, and the '
          'rest are reported as outliers. A value is shown as confirmed only when at least four methods (60 %) agree, '
          'including an independent family (a deep model) or the strict quality gate; otherwise it is shown as an '
          'estimate.'),
    ('p', 'Because a resting heart rate averaged over 30 s cannot jump by 20 BPM in 2 s, a display stabiliser smooths '
          'the readings (exponential average, weight 0.3), holds the value and raises a RAPID CHANGE flag when a '
          'reading is more than 8 BPM away, accepts a new level only after four confirmed readings in a row agree '
          'within 5 BPM, and withdraws the value with an UNSTABLE flag if the readings never settle within 15 s.'),
    ('fig', os.path.join(FIG, 'pipeline.png'), 'Fig. 3.2: Processing pipeline from camera frame to dashboard', 10.0),
    ('h3', '3.1.6 Breathing rate and breathing pattern'),
    ('p', 'Breathing is estimated from four independent sources: the slow change of skin brightness (respiratory-'
          'induced intensity variation), the beat-to-beat pulse height (amplitude variation), the beat-to-beat interval '
          '(frequency variation, respiratory sinus arrhythmia) and the vertical movement of the head measured by the '
          'face tracker. Each source is detrended below 0.07 Hz, differenced to whiten random-walk drift, and its '
          'periodogram is searched between 0.1 and 0.6 Hz (6-36 breaths per minute); a peak on the band edge is '
          'rejected. A source counts only if its peak holds a minimum share of the power, set just above the level '
          'reached by noise alone. Following the smart-fusion principle of Karlen et al. [15], a breathing rate is '
          'reported only when at least two sources (and at least half of them) agree within 4 breaths per minute, or '
          'when one very clear brightness or head-motion source is present. Breathing uses only the time since the '
          'last head movement and needs at least 20 s of it.'),
    ('p', 'The breathing pattern is classified from the clearest agreeing source: breaths are the peaks of the '
          'band-passed waveform; breathing is irregular when the breath-to-breath intervals vary by more than 30 % '
          '(coefficient of variation), and a pause is detected when the breathing envelope stays below 30 % of its '
          'typical level for at least 8 s.'),
    ('h3', '3.1.7 Camera heart-rate variability'),
    ('p', 'Heart-rate variability needs the time of every beat. The skin colour is therefore put on a 30 Hz grid at its '
          'own timestamps, the CHROM pulse is band-passed between 0.7 and 3.5 Hz (a wide band keeps the beat-to-beat '
          'variation that a narrow band would smooth away), interpolated to 240 Hz with a cubic spline, and systolic '
          'peaks are located at least 0.6 of a beat apart. Intervals more than 20 % from the median are rejected and '
          'the RMSSD [23] is computed from successive differences of adjacent clean intervals. Because camera noise '
          'shifts every beat time, the value is reported only with at least 20 fps video, at least 15 clean intervals '
          '(80 % of all) and a pulse SNR of at least +1 dB, the level at which the timing error was measured to be '
          'about 11 ms (Section 5.5).'),
    ('h3', '3.1.8 Blood-flow (perfusion) map and perfusion index'),
    ('p', 'Following photoplethysmographic imaging [17], the motion-compensated face box is reduced to a grid of '
          '32 x 32 cells, and the pulse in every cell is measured by lock-in detection at the heart rate: the green '
          'signal of each cell is multiplied by a complex exponential at the heart-rate frequency and summed over the '
          'window. The face-wide pulse (the sum over all skin cells) gives the reference phase, and each cell\'s '
          'in-phase component is an unbiased amplitude estimate in which noise averages to zero. The in-phase values '
          'are averaged over neighbouring skin cells (Gaussian, sigma 1.5 cells), and their uncertainty is measured by '
          'the same estimate at frequencies away from the heart rate:'),
    ('eq', 'z = (A_in-phase(f0) - mean_off) / sd_off ;     PI = 2 x A x 100 %  (peak-to-peak / DC)'),
    ('p', 'Every skin cell receives a value; cells with z of 2.5 or more are drawn at full opacity and less certain '
          'cells fade out. The map is made on request from a 30 s capture during which the subject must stay still; '
          'the capture restarts automatically if the head moves by more than 3 % of its size or the face is lost. With '
          'a weak pulse the map falls back to 16 x 16 or 8 x 8 cells. The perfusion index (PI) is reported overall and '
          'for the forehead, both cheeks and the nose.'),
    ('h3', '3.1.9 Liveness, blink rate and head steadiness'),
    ('p', 'Liveness combines two independent cues. A live face pulses: the frequency between 45 and 150 BPM at which '
          'the largest share of skin cells pulse in phase is searched, and the evidence is that share multiplied by '
          'the phase coherence. A live face also blinks. The face is LIVE when the pulse evidence is at least 0.15 for '
          'two updates or when at least two blinks occurred in the last 30 s; it is flagged as a possible photo or '
          'screen only when there is neither pulse nor blink for 30 s. Blinks are measured with the MediaPipe face '
          'mesh [19] (478 landmarks): the eye aspect ratio [18]'),
    ('eq', 'EAR = ( |p2 - p6| + |p3 - p5| ) / ( 2 |p1 - p4| )'),
    ('p', 'drops sharply when the lids close. A blink is a dip whose depth is at least 35 % of the median EAR and '
          'which lasts at most 0.5 s; dips are measured relative to the openness on both sides, so a change of gaze '
          'does not hide or double-count a blink. The blink rate is counted over the last 60 s and needs at least '
          '15 fps. Head steadiness is the RMS spread of the face position over 10 s, in percent of the face size: '
          'below 1.5 % STEADY, above 4 % MOVING. The head pose (yaw and pitch) is estimated from six landmarks with a '
          'perspective-n-point solution.'),
    ('h3', '3.1.10 Acoustic channel and colorimetric indices'),
    ('p', 'The acoustic engine processes the INMP441 audio for heart sounds (phonocardiography, PCG) when the '
          'microphone is placed on the chest: the signal is band-passed between 25 and 400 Hz, decimated to 1 kHz, and '
          'its Shannon energy envelope is computed over 20 ms windows. The heart period is the lag of the envelope '
          'autocorrelation peak between 0.4 and 1.33 s, accepted when the peak exceeds 0.4 and at least 60 % of the S1 '
          'intervals agree with it; S1 times also give an RMSSD. The audio is displayed as a band-passed waveform and a '
          'short-time Fourier spectrogram.'),
    ('p', 'The Diagnostics Studio analyses the sharpest full-face frame of the last 8 s (highest Laplacian variance) in '
          'five regions: forehead, both cheeks, the eye band and the lips. It reports five exploratory colorimetric '
          'indices (Section 3.2.4) and three colour maps of the face: red minus green, CIELAB b* (yellowness) and the '
          'blue-to-red ratio.'),

    ('h2', '3.2 Technical Descriptions'),
    ('h3', '3.2.1 Hardware prototype'),
    ('p', 'Figure 3.3 shows the assembled prototype: the ESP32-S3 camera board on a breadboard with the GC2145 camera, '
          'the SSD1306 OLED display on the I2C bus (GPIO 47/48), the INMP441 microphone harness on the I2S pins and a '
          'wire antenna for Wi-Fi. The node is powered over USB, which is also used for programming.'),
    ('fig', os.path.join(FIG, 'setup_labeled.png'), 'Fig. 3.3: SonicVitals edge sensor node prototype', 14.0),
    ('h3', '3.2.2 Firmware'),
    ('p', 'The firmware (Arduino framework, PlatformIO) runs two FreeRTOS tasks pinned to the two processor cores: a '
          'camera task (core 1) that captures frames, computes the skin sums and compresses every second frame into a '
          'PSRAM ring buffer, and an audio task (core 0) that reads I2S blocks of 256 samples, filters and decimates '
          'them. The main loop streams the data and always sends the newest video frame first, so that a slow link drops '
          'old frames instead of accumulating delay. Video is Base64-encoded inside '
          'the line protocol. The node reports its reset reason, free heap, task stack margins and current exposure in '
          'periodic <<INFO>> records, which the Device tab shows.'),
    ('h3', '3.2.3 Dashboard'),
    ('p', 'The dashboard is a single-page web application (HTML, JavaScript and Plotly) that polls the REST API of the '
          'Flask server four times per second. The Dashboard tab (Figure 3.4) shows the camera view with the face and '
          'skin regions, the readout cards, the microphone panel, the recovered pulse and breathing waveforms, the '
          'heart-rate history and the signal quality against the acceptance gate. Each card shows one large value and '
          'one status badge (green confirmed, amber estimate, red flag, grey no value); the reason behind each badge is '
          'shown on hover.'),
    ('fig', shot('8.26.38'), 'Fig. 3.4: Dashboard waveforms: recovered pulse, breathing waveform, heart-rate history and signal quality', 16.0),
    ('p', 'The method-comparison panel (Figure 3.5) lists the heart rate of every method at the same moment, marks '
          'which methods enter the robust average and which are left out as outliers, and plots them with the value '
          'shown on the heart-rate card.'),
    ('fig', shot('8.25.34'), 'Fig. 3.5: Live method comparison (six of seven methods agree; TS-CAN left out as an outlier)', 12.0),
    ('p', 'The Face Insights panel (Figure 3.6) contains the blood-flow map capture, the liveness, perfusion index, '
          'breathing pattern, blink rate and head steadiness cards, and two live graphs: eye openness with every blink '
          'marked, and the breathing movement of the head with every breath marked.'),
    ('fig', shot('9.12.44'), 'Fig. 3.6: Face Insights panel with a captured blood-flow map and live graphs', 16.0),
    ('p', 'The Signal Analysis tab (Figure 3.7) shows the power spectrum of the pulse with the cardiac band and the '
          'chosen peak, the microphone spectrogram, the standardised pulse, a moving-average decomposition into trend, '
          'pulsatile part and first difference, the relative skin-colour change of the three channels and the agreement '
          'of CHROM, POS and GREEN over time. Six readouts summarise the cardiac peak, SNR, spectral concentration, '
          'respiration frequency, method agreement and motion repair, and the video source with its measured frame '
          'rate.'),
    ('fig', shot('8.28.29'), 'Fig. 3.7: Signal Analysis: Welch power spectrum with cardiac band and standardised pulse', 6.8),
    ('fig', shot('8.28.48'), 'Fig. 3.8: Signal Analysis: skin colour change (R, G, B) and method agreement over time', 16.0),
    ('h3', '3.2.4 Diagnostics Studio'),
    ('p', 'The Diagnostics Studio (Figure 3.9) captures the sharpest full-face frame and computes five exploratory '
          'colour indices from 8-bit camera values. Their ranges are software settings and have not been validated '
          'clinically; the studio is a research tool for colour observation, not a diagnostic device.'),
    ('table', 'Table 3.1: Colorimetric indices of the Diagnostics Studio', [
        ['Index', 'Region', 'Formula (region means)', 'Software range'],
        ['Erythema index (EI)', 'Forehead', '100 (log10 R - log10 G)', '8-23 within range'],
        ['Pallor index', 'Both cheeks', '(G_L + B_L + G_R + B_R) / (2 (R_L + R_R))', '< 0.72 within range'],
        ['Eye-band yellowness (YI)', 'Eye band', '100 (R + G - 2B) / (R + G + B)', '< 12 within range'],
        ['Lip blue/red ratio (CR)', 'Lips', 'B / R', '< 0.76 within range'],
        ['Hemifacial asymmetry (HFI)', 'Both cheeks', '100 |G_L - G_R| / (G_L + G_R)', '< 5 % within range'],
        ['Frame clarity', 'Whole frame', 'variance of the Laplacian', '> 100 adequate'],
    ], [4.0, 2.4, 6.2, 3.4]),
    ('fig', shot('8.28.05'), 'Fig. 3.9: Diagnostics Studio: region capture, index summary and colorimetric indices', 16.0),
]

CONTENT += [
    # ------------------------------------------------------------------ 4
    ('h1', '4. HARDWARE/SOFTWARE TOOLS USED'),
    ('h2', '4.1 Hardware'),
    ('table', 'Table 4.1: Hardware components', [
        ['Component', 'Specification', 'Role'],
        ['ESP32-S3 camera board', 'Dual-core Xtensa LX7, 240 MHz, 512 KB SRAM, external PSRAM, Wi-Fi [26]', 'Edge acquisition, skin sums, streaming'],
        ['GC2145 image sensor', '2 MP CMOS, RGB565 output, register exposure control', 'Face video, 240 x 160 at 10 fps'],
        ['INMP441 microphone', 'MEMS, omnidirectional, 24-bit I2S, SNR 61 dB [27]', 'Acoustic channel (heart sounds)'],
        ['SSD1306 OLED', '0.96 inch, 128 x 64, I2C', 'Local display of vitals and status'],
        ['Laptop webcam', '640 x 480 at 30 fps (Apple MacBook Air M4 host)', 'Alternative camera, deep models'],
        ['Breadboard, jumper wires, USB cable, wire antenna', '-', 'Assembly, power and programming'],
    ], [4.2, 7.0, 4.8]),
    ('h2', '4.2 Software'),
    ('table', 'Table 4.2: Software tools and libraries', [
        ['Tool / library', 'Use'],
        ['Arduino framework, PlatformIO, ESP32 camera driver', 'Firmware development and flashing'],
        ['Python 3.10, NumPy, SciPy', 'Signal processing, spectral analysis, filtering'],
        ['OpenCV 4.11', 'Face detection, phase correlation, image processing, colour maps'],
        ['PyTorch, rPPG-Toolbox pretrained weights', 'TS-CAN, PhysNet, EfficientPhys inference'],
        ['MediaPipe Face Mesh', '478 facial landmarks for blinks and head pose'],
        ['Flask, Flask-CORS', 'REST API and video stream to the dashboard'],
        ['HTML, CSS, JavaScript, Plotly.js', 'Web dashboard and live graphs'],
        ['pytest', 'Automated test suite (79 tests)'],
        ['Google Colab (NVIDIA T4 GPU)', 'Benchmark on the UBFC-rPPG dataset'],
        ['MATLAB', 'Early signal-processing prototype'],
    ], [7.0, 9.0]),
    ('h2', '4.3 Datasets'),
    ('p', 'UBFC-rPPG (DATASET_2) [6] contains face videos recorded at 30 fps with a synchronised contact pulse '
          'oximeter signal; the first ten subjects were used for the benchmark. The deep models were trained on PURE '
          '[7] (rPPG-Toolbox weights [12]), so their UBFC-rPPG results are cross-dataset. Sessions recorded with the '
          'prototype were used for development and the live results.'),

    # ------------------------------------------------------------------ 5
    ('h1', '5. RESULT ANALYSIS'),
    ('h2', '5.1 Evaluation Methodology'),
    ('p', 'The heart-rate accuracy was evaluated on public data with contact references; the secondary indicators were '
          'evaluated on synthetic face videos with known ground truth (a real face image with an injected pulse, '
          'breathing modulations, head sway and camera noise), on recorded sessions and in live operation. The '
          'synthetic tests are part of an automated test suite of 79 tests that runs on every change. Metrics are the '
          'mean absolute error (MAE), the root-mean-square error (RMSE), the Pearson correlation r, the share of '
          'windows within 5 BPM and the coverage, i.e. the share of windows in which a method gives an output.'),
    ('h2', '5.2 Heart Rate on UBFC-rPPG'),
    ('p', 'The benchmark ran in Google Colab on the first ten UBFC-rPPG subjects with 30 s windows and a 10 s step. '
          'The reference heart rate of each window was computed from the contact PPG with the same post-processing as '
          'the predictions. Table 5.1 and Figure 5.1 summarise the results.'),
    ('table', 'Table 5.1: Heart-rate results on UBFC-rPPG (10 subjects, 30 s windows)', [
        ['Method', 'Coverage', 'MAE (BPM)', 'RMSE (BPM)', 'r', 'Within 5 BPM', 'ms per window'],
        ['GREEN', '100 %', '22.04', '34.21', '0.07', '47 %', '2.4'],
        ['CHROM', '100 %', '2.40', '6.48', '0.93', '86 %', '19.6'],
        ['POS', '100 %', '2.08', '5.41', '0.95', '86 %', '78.6'],
        ['TS-CAN (PURE -> UBFC)', '100 %', '1.68', '4.95', '0.96', '89 %', '278.5'],
        ['PhysNet (PURE -> UBFC)', '100 %', '1.90', '5.00', '0.95', '86 %', '159.9'],
        ['EfficientPhys (PURE -> UBFC)', '100 %', '3.88', '9.09', '0.88', '81 %', '141.9'],
        ['SonicVitals (raw)', '100 %', '2.30', '4.92', '0.96', '89 %', '71.8'],
        ['SonicVitals (gated)', '81 %', '1.56', '2.73', '0.99', '93 %', '71.8'],
        ['SonicVitals (display)', '86 %', '2.45', '3.30', '0.98', '87 %', '71.8'],
    ], [4.6, 1.7, 1.8, 1.9, 1.2, 2.0, 2.2]),
    ('fig', os.path.join(FIG, 'benchmark.png'), 'Fig. 5.1: MAE and RMSE of all methods on UBFC-rPPG', 16.0),
    ('p', 'The quality-gated SonicVitals estimate is the most accurate method: MAE 1.56 BPM, RMSE 2.73 BPM and '
          'r = 0.99, with 93 % of its windows within 5 BPM of the reference. The gate withholds 19 % of the windows, '
          'precisely the difficult ones; the low RMSE shows that the large errors that dominate the other methods are '
          'removed. Even without the gate (raw), SonicVitals has a lower RMSE than CHROM, POS and all three deep '
          'models, because artifact repair and illumination rectification remove the largest errors. The GREEN '
          'baseline fails on this dataset (MAE 22 BPM), confirming the value of chrominance-based methods. Among the '
          'cross-dataset deep models, TS-CAN and PhysNet are close to POS, and EfficientPhys is weaker. On whole '
          'videos, the gated SonicVitals estimate reached an MAE of 0.84 BPM on the 70 % of videos it accepted, all '
          'within 5 BPM of the reference. Processing '
          'one 30 s window takes about 72 ms on the CPU, far below real time.'),
    ('h2', '5.3 Live Heart-Rate Operation'),
    ('p', 'In live operation every method runs on the same face at the same time. In the session of Figure 3.5, six of '
          'the seven methods agreed between 76.1 and 76.9 BPM and the card showed their average of 76 BPM; TS-CAN '
          'read 65.9 BPM and was left out as an outlier. In another session all seven methods agreed between 78.7 and '
          '82.6 BPM and the card showed 81 BPM. Head stillness has a strong effect on signal quality: in a one-minute '
          'session the pulse SNR was between -4 and -9 dB while the head moved by 2.5-14 % of the face size, and rose '
          'to between -1 and +1.5 dB once the head was still (0.6-0.9 %), when six of seven methods agreed at '
          '81-83 BPM.'),
    ('p', 'The display stabiliser was evaluated by replaying a recorded webcam session: the raw single-window peak '
          'varied over a range of 44 BPM, while the value shown on the card changed by at most 0.7 BPM between '
          'updates and was labelled as an estimate throughout. Figure 3.4 shows the heart-rate history of a live '
          'session with the value shown on the card, accepted and rejected camera estimates, and flags raised during '
          'rapid changes.'),
    ('h3', '5.3.1 Effect of motion compensation and background handling'),
    ('p', 'Two signal-conditioning steps were validated on synthetic video. With a head sway of 5 pixels at 0.9 Hz, '
          'inside the heart-rate band, fixed skin regions produced a colour artifact of 3.35 % band RMS; with phase-'
          'correlation motion compensation the artifact fell to 0.20 %, a 17-fold reduction. Gating the illumination '
          'rectification on the strength of the background signal raised the SNR of a still synthetic face from '
          '-10.3 dB to +1.1 dB and restored the correct heart rate (74.5 BPM instead of 99 BPM), because pulse leaking '
          'into the background strips was no longer subtracted from the skin.'),
    ('h2', '5.4 Breathing Rate'),
    ('p', 'The breathing estimator was evaluated on synthetic faces with realistic random-walk drift of 1-2 % '
          '(as measured in live sessions), the three respiratory modulations of the pulse and head motion. Figure 5.2 '
          'compares it with a single green-channel peak search.'),
    ('fig', os.path.join(FIG, 'rr_accuracy.png'), 'Fig. 5.2: Breathing-rate error, single green peak versus four-source fusion', 12.5),
    ('p', 'The four-source fusion reached an MAE of 0.08-0.14 breaths per minute between 8 and 24 breaths per minute, '
          'against 0.88-7.82 for the single-peak method, which was pulled towards the lower band edge by drift. The '
          'fused rate was reported in 92-100 % of the windows between 12 and 24 breaths per minute, and no rate was '
          'reported in 160 windows without breathing. Live, the breathing-rate card read 18-19 breaths per minute '
          'while the breaths marked on the live breathing graph gave 16-20 breaths per minute (Figure 5.3).'),
    ('fig', shot('8.51.11'), 'Fig. 5.3: Live breathing movement of the head with detected breaths', 15.0),
    ('h2', '5.5 Camera Heart-Rate Variability'),
    ('p', 'Camera HRV was evaluated on synthetic 30 fps videos with known beat-to-beat intervals. Without camera noise '
          'the RMSSD error was about 2 ms. With noise, every beat time shifts and the error grows quickly with falling '
          'pulse SNR (Figure 5.4): about 11 ms at +1.2 dB and 64 ms at -2.1 dB; below -3.5 dB the beats cannot be '
          'timed. The display gate of +1 dB was set from this measurement, so that a camera HRV value is shown only '
          'when its error is small.'),
    ('fig', os.path.join(FIG, 'hrv_snr.png'), 'Fig. 5.4: RMSSD error of camera HRV versus pulse SNR', 12.0),
    ('h2', '5.6 Face Insights'),
    ('h3', '5.6.1 Blood-flow map'),
    ('p', 'The perfusion map was first validated on a synthetic face with a uniform injected pulse (Figure 5.5): the '
          'pulse is mapped over the skin and absent from the eyes, hair and background. The phase-referenced method '
          'raised the mapped skin area substantially over per-cell detection (Figure 5.6): from 28 % to 94 % for a '
          '0.15 % pulse and from 10 % to 71 % for a 0.08 % pulse, while the false coverage on a still photo stayed '
          'between 0.2 and 2.6 %. The measured perfusion index was within about 20 % of the injected pulse size. In a '
          'live 30 s capture (Figure 3.6) 46 % of the skin was mapped at a heart rate of 79 BPM, with a perfusion index '
          'of 0.13 % (forehead 0.09 %, left cheek 0.12 %, nose 0.17 %); the strongest blood flow appeared around the '
          'nose, a well-perfused region.'),
    ('fig', os.path.join(FIG, 'synthetic_map.png'), 'Fig. 5.5: Validation of the blood-flow map on a synthetic face with a known injected pulse', 6.5),
    ('fig', os.path.join(FIG, 'map_coverage.png'), 'Fig. 5.6: Skin area mapped by the first and the final perfusion-map method', 12.0),
    ('h3', '5.6.2 Liveness'),
    ('p', 'The pulse-based liveness evidence separated still photos from pulsing faces cleanly (Figure 5.7): thirteen '
          'photos at 30 fps and 5 fps reached at most 0.053, and five pulsing faces at least 0.39, including a weak '
          '0.15 % pulse and the 5 fps edge-camera case. All photos were classified as NO PULSE and all pulsing faces '
          'as LIVE. On a recorded real session with a weak pulse, the face was classified LIVE through the blink cue, '
          'and a still photo with detectable landmarks but no blinks was flagged as a possible photo.'),
    ('fig', os.path.join(FIG, 'liveness.png'), 'Fig. 5.7: Liveness evidence of still photos and pulsing faces', 12.0),
    ('h3', '5.6.3 Blink rate and head steadiness'),
    ('p', 'The blink detector was verified frame by frame on a recorded 45 s session: it found 20 blinks (about 27 per '
          'minute while talking) and every detected moment showed closed or closing eyes. A synthetic test with seven '
          'blinks, a change of eye openness after a gaze shift and a 1.5 s eye closure detected exactly the seven '
          'blinks and ignored the closure. Live, the blink rate was 14-16 per minute. Figure 5.8 shows the live eye-'
          'openness graph with each detected blink. Head steadiness correctly separated still periods (0.2-0.9 % of '
          'the face size) from movement (up to 14 %).'),
    ('fig', shot('8.50.49'), 'Fig. 5.8: Live eye openness (eye aspect ratio) with detected blinks', 15.0),
    ('h2', '5.7 Acoustic Channel'),
    ('p', 'The acoustic channel streams continuously from the edge node at 4 kHz with no lost blocks over the Wi-Fi '
          'link. Figure 5.9 shows its short-time Fourier spectrogram on the dashboard, which displays the energy of the '
          'microphone signal over time and frequency.'),
    ('fig', os.path.join(IMG, 'spectrogram_audio.png'), 'Fig. 5.9: Acoustic short-time Fourier spectrogram', 12.0),
    ('h2', '5.8 Real-Time Performance'),
    ('p', 'Profiling showed that face detection on every frame was the largest cost. Running detection on every third '
          'frame (the phase-correlation tracker follows the face in between), running the face-landmark model on its '
          'own thread, and reading the webcam on a separate thread that timestamps each frame on arrival reduced the '
          'per-frame processing time from 21.4 ms to 10.6 ms and raised the processed frame rate from a median of '
          '16.4 to 27 fps, with the camera delivering 28-30 fps (Figure 5.10). The perfusion map and liveness search '
          'take about 110 ms every 2 s in a background thread.'),
    ('fig', os.path.join(FIG, 'performance.png'), 'Fig. 5.10: Processed frame rate and per-frame processing time', 14.0),
    ('h2', '5.9 Discussion'),
    ('p', 'The results show that a quality gate is as important as the pulse extractor: by withholding the 19 % most '
          'difficult windows, SonicVitals reduced the RMSE on UBFC-rPPG by about half compared with the best baseline. '
          'In live use the same principle appears as the robust consensus and the display stabiliser: the card shows '
          'one steady, explained value and flags disagreements instead of displaying jumps. The secondary indicators '
          'behave as designed on synthetic data with known truth; in live operation their quality depends strongly on '
          'lighting and stillness, which the dashboard communicates through its status badges and HOLD STILL '
          'guidance.'),
]

CONTENT += [
    # ------------------------------------------------------------------ 6
    ('h1', '6. CONCLUSION AND FUTURE WORK'),
    ('h2', '6.1 Summary'),
    ('p', 'SonicVitals demonstrates a complete contactless vital-sign monitoring system built from low-cost parts. The '
          'ESP32-S3 edge node computes skin statistics on raw pixels, controls its exposure for the skin, and streams '
          'video, skin sums and audio over Wi-Fi with a common time base. The host engine combines motion-compensated '
          'skin regions, artifact repair, illumination rectification, three classical pulse extractors, three deep '
          'networks, spectral tracking and a robust consensus into one heart-rate value whose confidence is always '
          'visible. On UBFC-rPPG the gated estimate reached an MAE of 1.56 BPM and an RMSE of 2.73 BPM, outperforming '
          'CHROM, POS and the cross-dataset deep models. Breathing rate is fused from four signals with an accuracy of '
          'about 0.1 breaths per minute on synthetic data, and the dashboard adds camera HRV, a blood-flow map with '
          'perfusion index, liveness, blink rate, head steadiness and colorimetric indices, all running at about '
          '30 fps.'),
    ('h2', '6.2 Limitations and Constraints'),
    ('bullets', [
        'Camera-based measurements depend on lighting and stillness: under uneven room light and with head movement '
        'the pulse SNR falls, and the system shows estimates or withholds values rather than confirmed readings.',
        'Darker skin absorbs more of the green light that carries the pulse, which lowers the rPPG signal [22]; even, '
        'frontal illumination is therefore especially important.',
        'The heart-rate benchmark covered ten UBFC-rPPG subjects; PURE and VIPL-HR evaluations and a larger, more '
        'diverse cohort are needed to establish generalisation.',
        'The edge camera delivers 5 fps video for face detection, which is too slow for the deep models, camera HRV and '
        'blink counting; these features use the webcam.',
        'The colorimetric indices and their ranges are uncalibrated software settings, and the system is a research '
        'prototype, not a certified medical device.',
        'The acoustic channel requires firm contact of the microphone with the chest; its quantitative validation '
        'against a reference is part of future work.',
    ]),
    ('h2', '6.3 Improvement / Future Work'),
    ('bullets', [
        'Extend the benchmark to the full UBFC-rPPG, PURE and VIPL-HR datasets, including the tracked and display '
        'outputs, and report cross-dataset results for all methods.',
        'Validate the live heart rate, breathing rate and HRV against an ECG or finger pulse oximeter in a controlled '
        'study with participants of different skin tones.',
        'Add a stethoscope chest piece to couple heart sounds into the MEMS microphone and validate the acoustic heart '
        'rate and HRV against ECG.',
        'Calibrate a camera SpO2 estimate (ratio of ratios) against a reference oximeter, and fine-tune the deep models '
        'on data recorded with the prototype.',
        'Move the edge node to a native USB link or a faster camera mode to raise the video rate, and add an infrared '
        'illuminator for operation in low light.',
    ]),

    # ------------------------------------------------------------------ 7
    ('h1', '7. SOCIAL AND ENVIRONMENTAL IMPACT'),
    ('p', 'Social impact. Contactless monitoring can make routine vital-sign checks easier and more hygienic in clinics, '
          'schools, workplaces and homes, and it is gentle for people whose skin is fragile. Because the system uses '
          'commodity hardware and open software, it can be reproduced at low cost, which supports screening in '
          'resource-limited settings and telemedicine. The dashboard is designed to be honest about uncertainty: it '
          'never presents an unverified reading as confirmed, which is essential for responsible use of health '
          'technology. Face video is personal data; SonicVitals processes it locally on the host computer and stores '
          'recordings only when a session is started explicitly. Known biases, such as the lower signal for darker '
          'skin, are documented so that future versions can be evaluated and improved for all users.'),
    ('p', 'Environmental impact. The edge node uses a few low-power components on a breadboard and is powered over '
          'USB; it can reuse an existing laptop as the processing host, so no dedicated computer is needed. Contactless '
          'measurement avoids disposable electrodes and probe covers, reducing consumable waste. The modular design '
          'allows components to be replaced or reused individually, which limits electronic waste.'),

    # ------------------------------------------------------------------ 8
    ('h1', '8. WORK PLAN'),
    ('h2', '8.1 Timeline'),
    ('table', 'Table 8.1: Project timeline', [
        ['Period', 'Activity', 'Outcome'],
        ['July 2026', 'Problem definition, literature survey, project planning', 'Project plan and hardware list'],
        ['August 2026', 'Detailed design, component selection and procurement', 'Project plan document (22 Aug)'],
        ['September 2026', 'MATLAB signal-processing prototype, hardware setup plan', 'Working offline rPPG prototype'],
        ['Early October 2026', 'Edge node assembly and firmware, Wi-Fi streaming, first recordings', 'Streaming prototype (5-9 Oct)'],
        ['Mid October 2026', 'Skin-metered exposure, firmware hardening, UBFC-rPPG benchmark', 'Benchmark results (15 Oct)'],
        ['Late October 2026', 'Motion compensation, consensus and stabiliser, breathing fusion, HRV, face insights, dashboard', 'Final real-time system (22 Oct)'],
        ['October 2026', 'Testing, documentation, report and presentation', 'Final report and viva material'],
    ], [3.3, 8.4, 4.3]),
    ('h2', '8.2 Individual Contribution'),
    ('table', 'Table 8.2: Individual contribution', [
        ['Team member', 'Contribution'],
        ['Janhavee Dhote', 'Literature survey, benchmark evaluation on UBFC-rPPG, result analysis, report and documentation'],
        ['Pratik Kumar', 'Signal-processing engine (rPPG pipeline, fusion, breathing, HRV, face insights), web dashboard, system integration'],
        ['Uday Krishan Khandelwal', 'Edge node hardware assembly, ESP32-S3 firmware, camera and microphone interfacing, testing'],
    ], [4.5, 11.5]),

    # ------------------------------------------------------------------ 9
    ('h1', '9. COST ANALYSIS'),
    ('p', 'Table 9.1 lists the components of the prototype with approximate retail prices in Indian online stores '
          '(October 2026). The software stack is entirely free and open source; the laptop used as the processing host '
          'is existing equipment and is not included.'),
    ('table', 'Table 9.1: Cost of the prototype', [
        ['Item', 'Quantity', 'Approx. cost (INR)'],
        ['ESP32-S3 camera development board (with GC2145 camera)', '1', '1,200'],
        ['INMP441 I2S MEMS microphone module', '1', '250'],
        ['SSD1306 0.96 inch I2C OLED display', '1', '250'],
        ['Breadboard', '1', '100'],
        ['Jumper wires and sensor harness', '1 set', '100'],
        ['USB cable', '1', '150'],
        ['Wire antenna and miscellaneous', '-', '100'],
        ['Total', '', '2,150'],
    ], [10.0, 2.2, 3.8]),
    ('p', 'A complete edge node therefore costs roughly 2,000-2,500 rupees, a small fraction of the cost of a '
          'multi-parameter patient monitor, while the processing runs on an ordinary laptop.'),
]

REFERENCES = [
    'W. Verkruysse, L. O. Svaasand, and J. S. Nelson, "Remote plethysmographic imaging using ambient light," Opt. Express, vol. 16, no. 26, pp. 21434-21445, 2008.',
    'M.-Z. Poh, D. J. McDuff, and R. W. Picard, "Non-contact, automated cardiac pulse measurements using video imaging and blind source separation," Opt. Express, vol. 18, no. 10, pp. 10762-10774, 2010.',
    'M.-Z. Poh, D. J. McDuff, and R. W. Picard, "Advancements in noncontact, multiparameter physiological measurements using a webcam," IEEE Trans. Biomed. Eng., vol. 58, no. 1, pp. 7-11, 2011.',
    'G. de Haan and V. Jeanne, "Robust pulse rate from chrominance-based rPPG," IEEE Trans. Biomed. Eng., vol. 60, no. 10, pp. 2878-2886, 2013.',
    'W. Wang, A. C. den Brinker, S. Stuijk, and G. de Haan, "Algorithmic principles of remote PPG," IEEE Trans. Biomed. Eng., vol. 64, no. 7, pp. 1479-1491, 2017.',
    'S. Bobbia, R. Macwan, Y. Benezeth, A. Mansouri, and J. Dubois, "Unsupervised skin tissue segmentation for remote photoplethysmography," Pattern Recognit. Lett., vol. 124, pp. 82-90, 2019.',
    'R. Stricker, S. Muller, and H.-M. Gross, "Non-contact video-based pulse rate measurement on a mobile service robot," in Proc. IEEE Int. Symp. Robot and Human Interactive Communication (RO-MAN), 2014, pp. 1056-1062.',
    'X. Niu, S. Shan, H. Han, and X. Chen, "RhythmNet: End-to-end heart rate estimation from face via spatial-temporal representation," IEEE Trans. Image Process., vol. 29, pp. 2409-2423, 2020.',
    'X. Liu, J. Fromm, S. Patel, and D. McDuff, "Multi-task temporal shift attention networks for on-device contactless vitals measurement," in Proc. Advances in Neural Information Processing Systems (NeurIPS), 2020.',
    'Z. Yu, X. Li, and G. Zhao, "Remote photoplethysmograph signal measurement from facial videos using spatio-temporal networks," in Proc. British Machine Vision Conf. (BMVC), 2019.',
    'X. Liu, B. Hill, Z. Jiang, S. Patel, and D. McDuff, "EfficientPhys: Enabling simple, fast and accurate camera-based cardiac measurement," in Proc. IEEE/CVF Winter Conf. Applications of Computer Vision (WACV), 2023, pp. 5008-5017.',
    'X. Liu, G. Narayanswamy, A. Paruchuri, X. Zhang, J. Tang, Y. Zhang, R. Sengupta, S. Patel, Y. Wang, and D. McDuff, "rPPG-Toolbox: Deep remote PPG toolbox," in Proc. NeurIPS Datasets and Benchmarks Track, 2023.',
    'G. Boccignone, D. Conte, V. Cuculo, A. D\'Amelio, G. Grossi, R. Lanzarotti, and E. Mortara, "pyVHR: a Python framework for remote photoplethysmography," PeerJ Comput. Sci., vol. 8, e929, 2022.',
    'Z. Zhang, Z. Pi, and B. Liu, "TROIKA: A general framework for heart rate monitoring using wrist-type photoplethysmographic signals during intensive physical exercise," IEEE Trans. Biomed. Eng., vol. 62, no. 2, pp. 522-531, 2015.',
    'W. Karlen, S. Raman, J. M. Ansermino, and G. A. Dumont, "Multiparameter respiratory rate estimation from the photoplethysmogram," IEEE Trans. Biomed. Eng., vol. 60, no. 7, pp. 1946-1953, 2013.',
    'L. Tarassenko, M. Villarroel, A. Guazzi, J. Jorge, D. A. Clifton, and C. Pugh, "Non-contact video-based vital sign monitoring using ambient light and auto-regressive models," Physiol. Meas., vol. 35, no. 5, pp. 807-831, 2014.',
    'A. A. Kamshilin, S. Miridonov, V. Teplov, R. Saarenheimo, and E. Nippolainen, "Photoplethysmographic imaging of high spatial resolution," Biomed. Opt. Express, vol. 2, no. 4, pp. 996-1006, 2011.',
    'T. Soukupova and J. Cech, "Real-time eye blink detection using facial landmarks," in Proc. 21st Computer Vision Winter Workshop, 2016.',
    'C. Lugaresi et al., "MediaPipe: A framework for building perception pipelines," arXiv:1906.08172, 2019.',
    'P. Viola and M. Jones, "Rapid object detection using a boosted cascade of simple features," in Proc. IEEE Conf. Computer Vision and Pattern Recognition (CVPR), 2001, pp. I-511-I-518.',
    'X. Li, J. Chen, G. Zhao, and M. Pietikainen, "Remote heart rate measurement from face videos under realistic situations," in Proc. IEEE Conf. Computer Vision and Pattern Recognition (CVPR), 2014, pp. 4264-4271.',
    'E. M. Nowara, D. McDuff, and A. Veeraraghavan, "A meta-analysis of the impact of skin type and gender on non-contact photoplethysmography measurements," in Proc. IEEE/CVF CVPR Workshops, 2020.',
    'Task Force of the European Society of Cardiology and the North American Society of Pacing and Electrophysiology, "Heart rate variability: Standards of measurement, physiological interpretation, and clinical use," Circulation, vol. 93, no. 5, pp. 1043-1065, 1996.',
    'J. Allen, "Photoplethysmography and its application in clinical physiological measurement," Physiol. Meas., vol. 28, no. 3, pp. R1-R39, 2007.',
    'P. D. Welch, "The use of fast Fourier transform for the estimation of power spectra: A method based on time averaging over short, modified periodograms," IEEE Trans. Audio Electroacoust., vol. 15, no. 2, pp. 70-73, 1967.',
    'Espressif Systems, "ESP32-S3 Series Datasheet," version 1.9, 2024. [Online]. Available: https://www.espressif.com',
    'InvenSense, "INMP441: Omnidirectional microphone with bottom port and I2S digital output," datasheet, 2014.',
    'J. M. Bland and D. G. Altman, "Statistical methods for assessing agreement between two methods of clinical measurement," Lancet, vol. 327, no. 8476, pp. 307-310, 1986.',
    'C. D. Kuglin and D. C. Hines, "The phase correlation image alignment method," in Proc. IEEE Int. Conf. Cybernetics and Society, 1975, pp. 163-165.',
]
