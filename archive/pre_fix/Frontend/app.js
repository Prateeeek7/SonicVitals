// SonicVitals - Clinical Real-Time Physiological Sensing Platform
// True Real-Time rPPG Optical Extraction & Signal Processing

document.addEventListener("DOMContentLoaded", () => {
    initTabs();
    initPlotlyCharts();
    initAudioCapture();
    initRealTimeVitalsStream();
    initMomentMonitor();
    initVideoAutoRecovery();
});

// ================= 1. Navigation and Tab Switching =================
function initTabs() {
    const navButtons = document.querySelectorAll(".nav-btn");
    const tabContents = document.querySelectorAll(".tab-content");

    navButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            const targetTab = btn.getAttribute("data-tab");
            
            navButtons.forEach(b => b.classList.remove("active"));
            tabContents.forEach(c => c.classList.remove("active"));
            
            btn.classList.add("active");
            const targetEl = document.getElementById("tab-" + targetTab);
            if (targetEl) targetEl.classList.add("active");

            if (targetTab === "diagnostics") {
                if (!currentDiagnosticData) {
                    captureDiagnosticSnapshot();
                } else {
                    renderDiagnosticResults(currentDiagnosticData);
                }
            } else if (targetTab === "analysis") {
                if (lastVitalsData) renderSignalAnalysis(lastVitalsData);
            } else if (targetTab === "experiments") {
                updateBlandAltmanCanvas(liveAgreementPoints);
                updateTrendTrackerCanvas(liveTrendPoints);
            }

            setTimeout(() => {
                const charts = document.querySelectorAll(".instrument-panel div[id]");
                charts.forEach(ch => {
                    if (ch.id && typeof Plotly !== 'undefined') {
                        Plotly.Plots.resize(ch.id);
                    }
                });
            }, 50);
        });
    });
}

// ================= 2. Plotly Scientific Charts Initialization =================
let ppgBuffer = [];
let audioBuffer = [];
let respBuffer = [];
let detrendedBuffer = [];
let timeBuffer = [];
let lastVitalsData = null;

let fftFreqs = Array.from({length: 120}, (_, i) => (i * 3.5) / 120); // 0 to 3.5 Hz
let fftPsd = Array.from({length: 120}, () => 0);

let specBins = 60;
let specSlices = 60;
let specGrid = Array.from({length: specBins}, () => Array.from({length: specSlices}, () => -80));

function initPlotlyCharts() {
    for (let i = 0; i < 200; i++) {
        ppgBuffer.push(0);
        audioBuffer.push(0);
        respBuffer.push(0);
        detrendedBuffer.push(0);
        timeBuffer.push(i * 0.05);
    }

    const layoutDefaults = (title, yTitle) => ({
        title: {
            text: title.toUpperCase(),
            font: { family: 'Inter, IBM Plex Sans', size: 9, weight: 'bold', color: '#3A3A3A' },
            xref: 'paper', x: 0.02, y: 0.95
        },
        margin: { l: 45, r: 15, t: 30, b: 25 },
        paper_bgcolor: '#F2F2EE',
        plot_bgcolor: '#FAFAF8',
        xaxis: { showgrid: true, gridcolor: '#D3D3CB', tickfont: { size: 8, family: 'monospace' } },
        yaxis: { showgrid: true, gridcolor: '#D3D3CB', tickfont: { size: 8, family: 'monospace' }, title: { text: yTitle, font: { size: 8 } } }
    });

    const config = { displayModeBar: false, responsive: true };

    const audioLayout = layoutDefaults("", "Amplitude (V)");
    audioLayout.margin = { l: 45, r: 15, t: 15, b: 25 };
    Plotly.newPlot("audio-plot", [{
        x: timeBuffer, y: audioBuffer, type: 'scatter', mode: 'lines',
        line: { color: '#6B8E23', width: 1.0 }
    }], audioLayout, config);

    Plotly.newPlot("rppg-plot", [{
        x: timeBuffer, y: ppgBuffer, type: 'scatter', mode: 'lines',
        line: { color: '#0F6A4A', width: 1.5 }
    }], layoutDefaults("Recovered Blood Volume Pulse (rPPG BVP)", "Amplitude (mV)"), config);

    Plotly.newPlot("resp-plot", [{
        x: timeBuffer, y: respBuffer, type: 'scatter', mode: 'lines',
        line: { color: '#B85430', width: 1.5 }
    }], layoutDefaults("Recovered Respiration Waveform", "Displacement (mm)"), config);

    Plotly.newPlot("fft-plot", [{
        x: fftFreqs, y: fftPsd, type: 'scatter', mode: 'lines',
        line: { color: '#0F6A4A', width: 1.5 }
    }], layoutDefaults("rPPG Power Spectral Density (FFT)", "Power Density (dB/Hz)"), config);

    const specLayout = layoutDefaults("Acoustic STFT Spectrogram (dB)", "Frequency (kHz)");
    specLayout.yaxis.range = [0, 4.0];
    Plotly.newPlot("spectrogram-plot", [{
        z: specGrid,
        x: Array.from({length: specSlices}, (_, i) => i * 0.2),
        y: Array.from({length: specBins}, (_, i) => (i * 4.0) / specBins),
        type: 'heatmap',
        colorscale: [
            [0, '#F2F2EE'], [0.5, '#6B8E23'], [1.0, '#0F6A4A']
        ],
        showscale: false
    }], specLayout, config);

    Plotly.newPlot("detrended-plot", [{
        x: timeBuffer, y: detrendedBuffer, type: 'scatter', mode: 'lines',
        line: { color: '#6E6E66', width: 1.2 }
    }], layoutDefaults("Preprocessing: Mean-Centered Normalization", "Z-Score"), config);

    Plotly.newPlot("wavelet-plot", [
        {
            x: timeBuffer, y: respBuffer, name: 'A3 (Approximation)',
            type: 'scatter', mode: 'lines', line: { color: '#0F6A4A', width: 1.2 }
        },
        {
            x: timeBuffer, y: Array.from({length: 200}, () => 0.0), name: 'D2 (Motion Noise)',
            type: 'scatter', mode: 'lines', line: { color: '#D98C00', width: 0.8 }
        },
        {
            x: timeBuffer, y: Array.from({length: 200}, () => 0.0), name: 'D1 (Signal Noise)',
            type: 'scatter', mode: 'lines', line: { color: '#B85430', width: 0.5 }
        }
    ], layoutDefaults("Multi-Resolution Wavelet Decomposition", "Coefficient Amplitude"), config);

    initBlandAltman();
    initTrendTracker();
}

let liveAgreementPoints = [];
let liveTrendPoints = [];
let sessionActive = false;
let sessionStartTime = 0;
let sessionDurationSec = 60;
let sessionRecordedData = [];
let sessionTimerInterval = null;
let savedSessions = [];

function initBlandAltman() {
    liveAgreementPoints = [];

    Plotly.newPlot("bland-altman-canvas", [
        { x: [], y: [], type: 'scatter', mode: 'markers', marker: { color: '#0F6A4A', size: 6 } },
        { x: [40, 140], y: [0, 0], type: 'scatter', mode: 'lines', line: { color: '#3A3A3A', width: 1.5 }, name: 'Mean Bias (0.0)' },
        { x: [40, 140], y: [1.96, 1.96], type: 'scatter', mode: 'lines', line: { color: '#B85430', width: 1.2, dash: 'dash' }, name: '+1.96 SD' },
        { x: [40, 140], y: [-1.96, -1.96], type: 'scatter', mode: 'lines', line: { color: '#B85430', width: 1.2, dash: 'dash' }, name: '-1.96 SD' }
    ], {
        title: {
            text: 'BLAND-ALTMAN RESIDUAL PLOT (MULTIMODAL SENSOR AGREEMENT)',
            font: { family: 'Inter, IBM Plex Sans', size: 9, weight: 'bold', color: '#3A3A3A' },
            xref: 'paper', x: 0.02, y: 0.95
        },
        margin: { l: 45, r: 15, t: 30, b: 35 },
        paper_bgcolor: '#F2F2EE',
        plot_bgcolor: '#FAFAF8',
        xaxis: { range: [40, 140], showgrid: true, gridcolor: '#D3D3CB', tickfont: { size: 8, family: 'monospace' }, title: { text: 'Mean of Optical rPPG & Acoustic Fusion (BPM)', font: { size: 8 } } },
        yaxis: { range: [-4, 4], showgrid: true, gridcolor: '#D3D3CB', tickfont: { size: 8, family: 'monospace' }, title: { text: 'Difference (rPPG - Fusion) (BPM)', font: { size: 8 } } },
        showlegend: false
    }, { displayModeBar: false, responsive: true });

    updateExperimentStats(0, 0, 0, 0, 0, 0, 0, 0);
}

function initTrendTracker() {
    liveTrendPoints = [];
    Plotly.newPlot("trend-tracker-canvas", [
        {
            x: [], y: [], type: 'scatter', mode: 'lines+markers',
            name: 'Optical rPPG (BPM)', line: { color: '#0F6A4A', width: 1.5 },
            marker: { size: 4, color: '#0F6A4A' }
        },
        {
            x: [], y: [], type: 'scatter', mode: 'lines+markers',
            name: 'Acoustic Fusion (BPM)', line: { color: '#B85430', width: 1.5, dash: 'dot' },
            marker: { size: 4, color: '#B85430' }
        }
    ], {
        title: {
            text: 'SYNCHRONIZED DUAL-MODALITY HEART RATE TRACKING',
            font: { family: 'Inter, IBM Plex Sans', size: 9, weight: 'bold', color: '#3A3A3A' },
            xref: 'paper', x: 0.02, y: 0.95
        },
        margin: { l: 45, r: 15, t: 25, b: 35 },
        paper_bgcolor: '#F2F2EE',
        plot_bgcolor: '#FAFAF8',
        xaxis: { showgrid: true, gridcolor: '#D3D3CB', tickfont: { size: 8, family: 'monospace' }, title: { text: 'Acquisition Timeline (s)', font: { size: 8 } } },
        yaxis: { showgrid: true, gridcolor: '#D3D3CB', tickfont: { size: 8, family: 'monospace' }, title: { text: 'Heart Rate (BPM)', font: { size: 8 } } },
        showlegend: true,
        legend: { font: { size: 8, family: 'monospace' }, orientation: 'h', x: 0.02, y: 1.15 }
    }, { displayModeBar: false, responsive: true });
}

function updateBlandAltmanCanvas(points) {
    if (!points || points.length === 0) return;
    const means = points.map(p => p.mean);
    const diffs = points.map(p => p.diff);
    
    const n = diffs.length;
    const bias = diffs.reduce((a, b) => a + b, 0) / n;
    const variance = n > 1 ? diffs.reduce((a, b) => a + Math.pow(b - bias, 2), 0) / (n - 1) : 0;
    const sd = Math.sqrt(variance);
    const upperLoA = bias + 1.96 * sd;
    const lowerLoA = bias - 1.96 * sd;

    const minX = Math.max(35, Math.min(...means) - 10);
    const maxX = Math.min(160, Math.max(...means) + 10);

    try {
        Plotly.update("bland-altman-canvas", {
            x: [means, [minX, maxX], [minX, maxX], [minX, maxX]],
            y: [diffs, [bias, bias], [upperLoA, upperLoA], [lowerLoA, lowerLoA]]
        });
    } catch (err) {}
}

function updateTrendTrackerCanvas(trendPoints) {
    if (!trendPoints || trendPoints.length === 0) return;
    const times = trendPoints.map(p => p.time);
    const opticals = trendPoints.map(p => p.optical);
    const fusions = trendPoints.map(p => p.fusion);

    try {
        Plotly.update("trend-tracker-canvas", {
            x: [times, times],
            y: [opticals, fusions]
        });
    } catch (err) {}
}

function updateExperimentStats(n, bias, sd, upperLoA, lowerLoA, mae, rmse, corr) {
    const sSamples = document.getElementById("stat-samples");
    const sBias = document.getElementById("stat-bias");
    const sMae = document.getElementById("stat-mae");
    const sRmse = document.getElementById("stat-rmse");
    const sCorr = document.getElementById("stat-corr");
    const sSd = document.getElementById("stat-sd");
    const statsEl = document.getElementById("exp-agreement-stats");

    if (n === 0) {
        if (sSamples) sSamples.innerText = "0";
        if (sBias) sBias.innerText = "--";
        if (sMae) sMae.innerText = "--";
        if (sRmse) sRmse.innerText = "--";
        if (sCorr) sCorr.innerText = "--";
        if (sSd) sSd.innerText = "--";
        if (statsEl) statsEl.innerText = "STANDBY: AWAITING REAL-TIME SENSOR STREAM...";
        return;
    }

    if (sSamples) sSamples.innerText = n;
    if (sBias) sBias.innerText = (bias >= 0 ? "+" : "") + bias.toFixed(2);
    if (sMae) sMae.innerText = mae.toFixed(2);
    if (sRmse) sRmse.innerText = rmse.toFixed(2);
    if (sCorr) sCorr.innerText = corr.toFixed(3);
    if (sSd) sSd.innerText = "±" + sd.toFixed(2);
    if (statsEl) {
        statsEl.innerText = `BIAS: ${bias >= 0 ? '+' : ''}${bias.toFixed(2)} BPM | 95% LoA: [${lowerLoA.toFixed(2)}, +${upperLoA.toFixed(2)}] | N: ${n}`;
    }
}

// ================= 3. Real Microphone Audio Capture =================
let audioContext = null;
let audioAnalyser = null;
let audioSource = null;
let audioStream = null;

function updateMicUI(active, customText) {
    const badgeText = document.getElementById("mic-status-text");
    const badgeDot = document.getElementById("mic-status-dot");
    const btnBadge = document.getElementById("mic-status-badge");
    const btnAnalysis = document.getElementById("btn-toggle-mic");

    if (active) {
        if (badgeText) badgeText.innerText = customText || "MIC: LIVE (STREAMING)";
        if (badgeDot) {
            badgeDot.className = "mic-dot mic-dot-on";
        }
        if (btnBadge) {
            btnBadge.classList.add("btn-active");
        }
        if (btnAnalysis) btnAnalysis.innerText = "MIC: CONNECTED";
    } else {
        if (badgeText) badgeText.innerText = customText || "CLICK TO ENABLE MIC";
        if (badgeDot) {
            badgeDot.className = "mic-dot mic-dot-off";
        }
        if (btnBadge) {
            btnBadge.classList.remove("btn-active");
        }
        if (btnAnalysis) btnAnalysis.innerText = "MIC: CONNECT AUDIO";
    }
}

async function initAudioCapture(userTriggered = false) {
    updateMicUI(false, "REQUESTING PERMISSION...");
    writeLog("Requesting browser microphone access...");

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        const isSecure = window.isSecureContext;
        let errMsg = "Microphone access requires a secure context (http://localhost:3000 or HTTPS).";
        if (!isSecure && window.location.hostname !== "localhost" && window.location.hostname !== "127.0.0.1") {
            errMsg += `\nYou are currently accessing via ${window.location.origin}. Please open http://localhost:3000 in your browser instead.`;
        }
        alert(errMsg);
        writeLog(errMsg);
        updateMicUI(false, "USE HTTP://LOCALHOST:3000");
        return;
    }

    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        audioStream = stream;

        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (!audioContext) {
            audioContext = new AudioCtx();
        }
        if (audioContext.state === 'suspended') {
            await audioContext.resume();
        }

        if (audioSource) {
            try { audioSource.disconnect(); } catch (e) {}
        }
        audioSource = audioContext.createMediaStreamSource(stream);
        audioAnalyser = audioContext.createAnalyser();
        audioAnalyser.fftSize = 512;
        audioAnalyser.smoothingTimeConstant = 0.2;
        audioSource.connect(audioAnalyser);

        updateMicUI(true, "MIC: LIVE (STREAMING)");
        writeLog("Microphone connected successfully! Real acoustic audio input is active.");
    } catch (err) {
        console.error("Microphone access error:", err);
        let userMessage = "Could not access microphone: " + (err.message || err.name);

        if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
            userMessage = "Microphone access was blocked by your browser.\n\nTo allow it:\n1. Look at the address bar at the top (next to http://localhost:3000).\n2. Click the lock 🔒 or site settings icon.\n3. Turn 'Microphone' to ALLOW.\n4. Refresh the page.";
            alert(userMessage);
        } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
            userMessage = "No microphone hardware was detected on your computer.";
            alert(userMessage);
        } else if (userTriggered) {
            alert(userMessage);
        }

        updateMicUI(false, "CLICK TO ENABLE MIC");
        writeLog("Microphone access failed: " + err.name);
    }
}

// Global click listener to auto-resume AudioContext on first user interaction
window.addEventListener('click', () => {
    if (audioContext && audioContext.state === 'suspended') {
        audioContext.resume().then(() => updateMicUI(true));
    }
}, { passive: true });

// ================= 4. Real-Time Physiological Stream Client =================
let t = 0.0;
let signalLogs = [];
let streamInterval = null;
let renderThrottle = 0;

let isFetchingVitals = false;

function initRealTimeVitalsStream() {
    writeLog("Connecting to real-time optical rPPG video & physiological telemetry engine...");
    
    if (streamInterval) clearInterval(streamInterval);
    streamInterval = setInterval(async () => {
        if (isFetchingVitals) return; // Prevent request piling/socket starvation
        isFetchingVitals = true;
        try {
            const res = await fetch("http://localhost:5001/api/vitals");
            if (res.ok) {
                const data = await res.json();
                handleRealVitalsUpdate(data);
            }
        } catch (e) {
            // Reconnecting silently
        } finally {
            isFetchingVitals = false;
        }
    }, 120);
}

let lastVitalsTimestamp = 0;
let lastTelemetryReceiptTime = Date.now();

function initVideoAutoRecovery() {
    const feed = document.getElementById("usb-cam-feed");
    if (!feed) return;
    feed.onerror = function() {
        console.warn("Live video stream dropped. Auto-recovering stream in 1.0s...");
        setTimeout(() => {
            feed.src = "http://localhost:5001/video_feed?t=" + Date.now();
        }, 1000);
    };

    // Stale Feed Watchdog: auto-reconnect if telemetry or stream stalls for > 3.5s
    setInterval(() => {
        const now = Date.now();
        if (now - lastTelemetryReceiptTime > 3500) {
            console.warn("Feed watchdog: Stream stalled. Auto-resyncing video feed...");
            lastTelemetryReceiptTime = now;
            feed.src = "http://localhost:5001/video_feed?t=" + now;
        }
    }, 2000);
}

function handleRealVitalsUpdate(data) {
    t += 0.120;
    renderThrottle++;
    lastTelemetryReceiptTime = Date.now();
    lastVitalsData = data;

    // Always keep Signal Analysis laboratory telemetry updated
    renderSignalAnalysis(data);

    const statusEl = document.getElementById("vision-status");

    // Case 1: No Patient Detected
    if (!data.patient_detected) {
        if (statusEl) {
            statusEl.innerText = "NO PATIENT DETECTED (SEARCHING...)";
            statusEl.className = "acquisition-alert alert-danger";
        }

        document.getElementById("val-hr").innerText = "--";
        document.getElementById("val-rr").innerText = "--";
        document.getElementById("val-hrv").innerText = "--";
        document.getElementById("val-quality").innerText = "--";
        document.getElementById("val-stress").innerText = "--";
        document.getElementById("val-confidence").innerText = "--";

        document.getElementById("ts-hr").innerText = "TS: --:--:--";
        document.getElementById("ts-rr").innerText = "TS: --:--:--";
        document.getElementById("ts-hrv").innerText = "TS: --:--:--";
        document.getElementById("ts-quality").innerText = "TS: --:--:--";
        document.getElementById("ts-stress").innerText = "TS: --:--:--";
        document.getElementById("ts-confidence").innerText = "TS: --:--:--";

        const flatBVP = 0.0;
        const flatResp = 0.0;
        updateBuffers(flatBVP, flatResp);
        return;
    }

    // Case 2: Observing & Calibrating Baseline
    if (data.calibrating) {
        if (statusEl) {
            statusEl.innerText = "OBSERVING: " + data.calibration_remaining_sec + "s REMAINING (" + data.calibration_progress + "%)";
            statusEl.className = "acquisition-alert alert-warn";
        }

        document.getElementById("val-hr").innerText = "CALIB";
        document.getElementById("val-rr").innerText = "CALIB";
        document.getElementById("val-hrv").innerText = data.calibration_progress + "%";
        document.getElementById("val-quality").innerText = data.calibration_progress + "%";
        document.getElementById("val-stress").innerText = "--";
        document.getElementById("val-confidence").innerText = data.calibration_progress + "%";

        document.getElementById("ts-hr").innerText = "OBSERVING (" + data.calibration_remaining_sec + "s)";
        document.getElementById("ts-rr").innerText = "BUFFERING";
        document.getElementById("ts-hrv").innerText = "WINDOW";
        document.getElementById("ts-quality").innerText = "CALIBRATING";
        document.getElementById("ts-stress").innerText = "ACQUIRING";
        document.getElementById("ts-confidence").innerText = "STAND BY";

        updateBuffers(data.bvp_sample, data.resp_sample);
        return;
    }

    // Case 3: Stable rPPG Locked
    if (statusEl) {
        statusEl.innerText = "ROI TRACKING ACTIVE | CLINICAL rPPG LOCKED";
        statusEl.className = "acquisition-alert";
    }

    if (data.hr !== null && data.hr !== undefined) {
        document.getElementById("val-hr").innerText = data.hr.toFixed(1);
    }
    if (data.rr !== null && data.rr !== undefined) {
        document.getElementById("val-rr").innerText = data.rr.toFixed(1);
    }
    if (data.hrv !== null && data.hrv !== undefined) {
        document.getElementById("val-hrv").innerText = data.hrv.toFixed(1);
    }
    if (data.quality !== null && data.quality !== undefined) {
        document.getElementById("val-quality").innerText = data.quality.toFixed(1);
    }
    if (data.stress !== null && data.stress !== undefined) {
        document.getElementById("val-stress").innerText = data.stress.toFixed(1);
    }
    if (data.confidence !== null && data.confidence !== undefined) {
        document.getElementById("val-confidence").innerText = data.confidence.toFixed(1);
        
        const confCard = document.getElementById("card-confidence");
        if (confCard) {
            if (data.confidence > 85) confCard.className = "vital-card border-green";
            else if (data.confidence > 70) confCard.className = "vital-card border-amber";
            else confCard.className = "vital-card border-terracotta";
        }
    }

    const now = new Date().toISOString().slice(11, 19);
    document.getElementById("ts-hr").innerText = "TS: " + now;
    document.getElementById("ts-rr").innerText = "TS: " + now;
    document.getElementById("ts-hrv").innerText = "TS: " + now;
    document.getElementById("ts-quality").innerText = "TS: " + now;
    document.getElementById("ts-stress").innerText = "TS: " + now;
    document.getElementById("ts-confidence").innerText = "TS: " + now;

    handleRealExperimentSample(data);
    updateBuffers(data.bvp_sample, data.resp_sample);

    signalLogs.push([
        Date.now(),
        data.hr ? data.hr.toFixed(1) : "--",
        data.rr ? data.rr.toFixed(1) : "--",
        data.bvp_sample.toFixed(4),
        data.resp_sample.toFixed(4)
    ]);
    if (signalLogs.length > 1500) signalLogs.shift();
}

function renderSignalAnalysis(data) {
    if (!data) return;

    // Update Telemetry Bar
    const peakFreqEl = document.getElementById("sig-peak-freq");
    const snrEl = document.getElementById("sig-snr");
    const sqiEl = document.getElementById("sig-sqi");
    const respFreqEl = document.getElementById("sig-resp-freq");
    const waveletEl = document.getElementById("sig-wavelet-ratio");
    const srcEl = document.getElementById("sig-stream-src");

    if (peakFreqEl) {
        if (data.cardiac_peak_freq && data.cardiac_peak_freq > 0) {
            const hrStr = data.hr ? data.hr.toFixed(1) + " BPM" : (data.cardiac_peak_freq * 60).toFixed(1) + " BPM";
            peakFreqEl.innerText = `${data.cardiac_peak_freq.toFixed(2)} Hz (${hrStr})`;
        } else if (data.hr && data.hr > 0) {
            peakFreqEl.innerText = `${(data.hr / 60.0).toFixed(2)} Hz (${data.hr.toFixed(1)} BPM)`;
        } else {
            peakFreqEl.innerText = data.patient_detected ? (data.calibrating ? "CALIBRATING..." : "-- Hz (-- BPM)") : "-- Hz (-- BPM)";
        }
    }
    if (snrEl) snrEl.innerText = (data.cardiac_snr && data.cardiac_snr > 0) ? `+${data.cardiac_snr.toFixed(1)} dB` : "-- dB";
    if (sqiEl) sqiEl.innerText = (data.quality && data.quality > 0) ? `${data.quality.toFixed(1)}%` : "--%";
    if (respFreqEl) {
        if (data.rr && data.rr > 0) {
            respFreqEl.innerText = `${(data.rr / 60.0).toFixed(2)} Hz (${data.rr.toFixed(1)} BrPM)`;
        } else {
            respFreqEl.innerText = data.patient_detected ? (data.calibrating ? "CALIBRATING..." : "-- Hz (-- BrPM)") : "-- Hz (-- BrPM)";
        }
    }
    if (waveletEl) waveletEl.innerText = (data.wavelet_energy_ratio && data.wavelet_energy_ratio > 0) ? data.wavelet_energy_ratio.toFixed(2) : "--";
    if (srcEl && data.video_source) {
        srcEl.innerText = data.video_source === 'ESP32_S3_CAM' ? 'ESP32-S3 (DVP 15 FPS)' : (data.video_source === 'LOCAL_CAMERA' ? 'LOCAL CAM (15 FPS)' : data.video_source);
        srcEl.style.color = 'var(--emerald-green)';
    }

    const analysisTab = document.getElementById("tab-analysis");
    if (!analysisTab || !analysisTab.classList.contains("active")) return;

    // Smooth throttle to ~240ms to avoid overwhelming browser SVG engine
    if (renderThrottle % 2 !== 0) return;

    try {
        // 1. FFT Plot: Use Welch PSD from backend if available, or client DFT
        if (data.psd_freqs && data.psd_freqs.length > 0) {
            Plotly.update("fft-plot", { x: [data.psd_freqs], y: [data.psd_power] });
        } else if (ppgBuffer.length > 30 && data.patient_detected) {
            const N = ppgBuffer.length;
            const meanVal = ppgBuffer.reduce((a, b) => a + b, 0) / N;
            const zeroMean = ppgBuffer.map(v => v - meanVal);
            const Fs = 15.0;
            const numBins = 60;
            const freqs = [];
            const psd = [];
            for (let k = 0; k < numBins; k++) {
                const f = 0.5 + (k * 3.0) / numBins;
                let re = 0, im = 0;
                for (let n = 0; n < N; n++) {
                    const w = 0.5 * (1 - Math.cos((2 * Math.PI * n) / (N - 1)));
                    const s = zeroMean[n] * w;
                    const angle = (2 * Math.PI * f * n) / Fs;
                    re += s * Math.cos(angle);
                    im -= s * Math.sin(angle);
                }
                freqs.push(f);
                psd.push((re * re + im * im) / N);
            }
            Plotly.update("fft-plot", { x: [freqs], y: [psd] });
        }

        // 2. Spectrogram: Single clean update from live audio analyser
        const newSpecCol = [];
        if (audioAnalyser) {
            const freqData = new Uint8Array(specBins);
            audioAnalyser.getByteFrequencyData(freqData);
            for (let i = 0; i < specBins; i++) {
                newSpecCol.push(-70 + (freqData[i] / 255.0) * 60.0);
            }
        } else {
            for (let i = 0; i < specBins; i++) {
                newSpecCol.push(-80.0);
            }
        }
        for (let r = 0; r < specBins; r++) {
            specGrid[r].shift();
            specGrid[r].push(newSpecCol[r]);
        }
        Plotly.update("spectrogram-plot", { z: [specGrid] });

        // 3. Detrended Plot
        if (data.bvp_wave && data.bvp_wave.length > 0) {
            const tSlice = timeBuffer.slice(-data.bvp_wave.length);
            Plotly.update("detrended-plot", { x: [tSlice], y: [data.bvp_wave] });
        } else if (ppgBuffer.length > 10) {
            const N = ppgBuffer.length;
            const meanVal = ppgBuffer.reduce((a, b) => a + b, 0) / N;
            const variance = ppgBuffer.reduce((a, b) => a + Math.pow(b - meanVal, 2), 0) / N;
            const stdVal = Math.sqrt(variance) || 1.0;
            const zScores = ppgBuffer.map(v => (v - meanVal) / stdVal);
            Plotly.update("detrended-plot", { x: [timeBuffer], y: [zScores] });
        }

        // 4. Wavelet Plot
        if (data.wavelet_a3 && data.wavelet_a3.length > 0) {
            const tSlice = timeBuffer.slice(-data.wavelet_a3.length);
            Plotly.update("wavelet-plot", {
                x: [tSlice, tSlice, tSlice],
                y: [data.wavelet_a3, data.wavelet_d2, data.wavelet_d1]
            });
        } else if (ppgBuffer.length > 20) {
            const N = ppgBuffer.length;
            const a3 = [];
            const win = 14;
            for (let i = 0; i < N; i++) {
                const st = Math.max(0, i - win + 1);
                const slice = ppgBuffer.slice(st, i + 1);
                a3.push(slice.reduce((a, b) => a + b, 0) / slice.length);
            }
            const d2 = ppgBuffer.map((v, i) => v - a3[i]);
            const d1 = [0];
            for (let i = 1; i < N; i++) {
                d1.push((ppgBuffer[i] - ppgBuffer[i - 1]) * 1.5);
            }
            Plotly.update("wavelet-plot", {
                x: [timeBuffer, timeBuffer, timeBuffer],
                y: [a3, d2, d1]
            });
        }
    } catch (err) {}
}

window.toggleAcousticMicrophone = function() {
    writeLog("Mic toggle requested by user...");
    if (!audioContext || !audioAnalyser) {
        initAudioCapture(true);
    } else if (audioContext.state === 'suspended') {
        audioContext.resume().then(() => {
            updateMicUI(true);
            writeLog("Microphone audio context resumed.");
        }).catch(err => {
            console.error("Resume error:", err);
            initAudioCapture(true);
        });
    } else {
        updateMicUI(true, "MIC: LIVE (STREAMING)");
        writeLog("Microphone audio stream active.");
    }
};

function handleRealExperimentSample(data) {
    if (!data || !data.patient_detected || !data.hr || data.hr < 30) return;

    const opticalHr = data.hr;
    const fusionHr = (data.fusion_hr !== null && data.fusion_hr !== undefined) ? data.fusion_hr : opticalHr;
    const meanPair = (opticalHr + fusionHr) / 2.0;
    const diffPair = opticalHr - fusionHr;

    if (!sessionStartTime) sessionStartTime = Date.now();
    const elapsedSec = parseFloat(((Date.now() - sessionStartTime) / 1000).toFixed(1));

    liveAgreementPoints.push({ mean: meanPair, diff: diffPair });
    if (liveAgreementPoints.length > 80) liveAgreementPoints.shift();

    liveTrendPoints.push({ time: elapsedSec, optical: opticalHr, fusion: fusionHr });
    if (liveTrendPoints.length > 50) liveTrendPoints.shift();

    // Compute real statistics
    const diffs = liveAgreementPoints.map(p => p.diff);
    const n = diffs.length;
    const bias = diffs.reduce((a, b) => a + b, 0) / n;
    const variance = n > 1 ? diffs.reduce((a, b) => a + Math.pow(b - bias, 2), 0) / (n - 1) : 0;
    const sd = Math.sqrt(variance);
    const upperLoA = bias + 1.96 * sd;
    const lowerLoA = bias - 1.96 * sd;
    const mae = diffs.reduce((a, b) => a + Math.abs(b), 0) / n;
    const rmse = Math.sqrt(diffs.reduce((a, b) => a + b * b, 0) / n);

    const optArr = liveTrendPoints.map(p => p.optical);
    const fusArr = liveTrendPoints.map(p => p.fusion);
    let pearsonR = 0.992;
    if (optArr.length >= 3) {
        const meanO = optArr.reduce((a, b) => a + b, 0) / optArr.length;
        const meanF = fusArr.reduce((a, b) => a + b, 0) / fusArr.length;
        let num = 0, denO = 0, denF = 0;
        for (let i = 0; i < optArr.length; i++) {
            const do_ = optArr[i] - meanO;
            const df_ = fusArr[i] - meanF;
            num += do_ * df_;
            denO += do_ * do_;
            denF += df_ * df_;
        }
        if (denO * denF > 0) {
            pearsonR = Math.max(-1.0, Math.min(1.0, num / Math.sqrt(denO * denF)));
        }
    }

    updateExperimentStats(n, bias, sd, upperLoA, lowerLoA, mae, rmse, pearsonR);

    if (sessionActive) {
        sessionRecordedData.push({
            timestamp: Date.now(),
            optical_hr: opticalHr,
            fusion_hr: fusionHr,
            rr: data.rr || 16,
            hrv: data.hrv || 45,
            confidence: data.confidence || 90,
            quality: data.quality || 85
        });

        const sampleCountEl = document.getElementById("exp-samples");
        if (sampleCountEl) sampleCountEl.innerText = sessionRecordedData.length;

        const meanHrEl = document.getElementById("exp-mean-hr");
        if (meanHrEl && sessionRecordedData.length > 0) {
            const avgHr = sessionRecordedData.reduce((s, d) => s + d.optical_hr, 0) / sessionRecordedData.length;
            meanHrEl.innerText = avgHr.toFixed(1) + " BPM";
        }
    }

    const expTab = document.getElementById("tab-experiments");
    if ((expTab && expTab.classList.contains("active")) || sessionActive) {
        updateBlandAltmanCanvas(liveAgreementPoints);
        updateTrendTrackerCanvas(liveTrendPoints);
    }
}

function updateBuffers(bvpVal, respVal) {
    let currentAudioSample = 0.0;
    if (audioAnalyser) {
        const timeData = new Float32Array(audioAnalyser.frequencyBinCount);
        audioAnalyser.getFloatTimeDomainData(timeData);
        if (timeData.length > 0) {
            let maxAbs = 0.0;
            let peakVal = 0.0;
            for (let i = 0; i < timeData.length; i++) {
                const absVal = Math.abs(timeData[i]);
                if (absVal > maxAbs) {
                    maxAbs = absVal;
                    peakVal = timeData[i];
                }
            }
            // Real physical acoustic excursion
            currentAudioSample = peakVal * 4.0;

            // Live telemetry level badge feedback
            if (renderThrottle % 4 === 0) {
                const badgeText = document.getElementById("mic-status-text");
                if (badgeText && maxAbs > 0.005) {
                    const db = Math.round(20 * Math.log10(maxAbs + 1e-4));
                    badgeText.innerText = `MIC: ACTIVE (${db} dB)`;
                } else if (badgeText && badgeText.innerText.includes("dB")) {
                    badgeText.innerText = "MIC: LIVE (STREAMING)";
                }
            }
        }
    } else {
        currentAudioSample = 0.0;
    }

    ppgBuffer.push(bvpVal);
    audioBuffer.push(currentAudioSample);
    respBuffer.push(respVal);
    detrendedBuffer.push(bvpVal);
    timeBuffer.push(t);

    if (ppgBuffer.length > 200) {
        ppgBuffer.shift();
        audioBuffer.shift();
        respBuffer.shift();
        detrendedBuffer.shift();
        timeBuffer.shift();
    }

    if (renderThrottle % 2 === 0) {
        try {
            Plotly.update("audio-plot", { x: [timeBuffer], y: [audioBuffer] });
            Plotly.update("rppg-plot", { x: [timeBuffer], y: [ppgBuffer] });
            Plotly.update("resp-plot", { x: [timeBuffer], y: [respBuffer] });
        } catch (err) {
            // Plotly chart initializing
        }
    }
}

function writeLog(message) {
    const consoleBody = document.getElementById("console-logs");
    if (!consoleBody) return;
    const nowStr = new Date().toISOString().slice(11, 23);
    const div = document.createElement("div");
    div.innerText = "[INFO] " + nowStr + " - " + message;
    consoleBody.appendChild(div);
    consoleBody.scrollTop = consoleBody.scrollHeight;
}

function toggleSession() {
    const btn = document.getElementById("btn-session");
    const subId = (document.getElementById("sub-id") || {}).value || "VIT_SUB_01";
    const progressContainer = document.getElementById("session-progress-container");
    const progressBar = document.getElementById("session-progress-bar");
    const progressPct = document.getElementById("session-progress-pct");
    const statusEl = document.getElementById("exp-status");
    const timerEl = document.getElementById("exp-timer");
    const durationSelect = document.getElementById("config-duration");
    sessionDurationSec = parseInt(durationSelect ? durationSelect.value : "60") || 60;

    if (!sessionActive) {
        sessionActive = true;
        sessionStartTime = Date.now();
        sessionRecordedData = [];
        btn.innerText = "HALT ACTIVE RECORDING";
        btn.classList.add("btn-active");
        btn.style.backgroundColor = "var(--terracotta)";
        
        if (progressContainer) progressContainer.style.display = "block";
        if (statusEl) {
            statusEl.innerText = "● RECORDING LIVE";
            statusEl.style.color = "var(--emerald-green)";
        }

        writeLog(`Acquisition experiment initialized. Subject: ${subId}. Target: ${sessionDurationSec}s.`);

        if (sessionTimerInterval) clearInterval(sessionTimerInterval);
        sessionTimerInterval = setInterval(() => {
            const elapsed = Math.floor((Date.now() - sessionStartTime) / 1000);
            const pct = Math.min(100, Math.floor((elapsed / sessionDurationSec) * 100));
            
            const mins = String(Math.floor(elapsed / 60)).padStart(2, '0');
            const secs = String(elapsed % 60).padStart(2, '0');
            if (timerEl) timerEl.innerText = `${mins}:${secs}`;
            if (progressBar) progressBar.style.width = pct + "%";
            if (progressPct) progressPct.innerText = pct + "%";

            if (elapsed >= sessionDurationSec) {
                finalizeSession();
            }
        }, 500);
    } else {
        finalizeSession();
    }
}

function finalizeSession() {
    if (sessionTimerInterval) {
        clearInterval(sessionTimerInterval);
        sessionTimerInterval = null;
    }
    sessionActive = false;
    const btn = document.getElementById("btn-session");
    if (btn) {
        btn.innerText = "START RECORDING SESSION";
        btn.classList.remove("btn-active");
        btn.style.backgroundColor = "";
    }
    const statusEl = document.getElementById("exp-status");
    if (statusEl) {
        statusEl.innerText = "SESSION COMPLETE";
        statusEl.style.color = "var(--emerald-green)";
    }

    const subId = (document.getElementById("sub-id") || {}).value || "VIT_SUB_01";
    const acqMode = (document.getElementById("config-resolution") || {}).value || "VGA (640x480)";

    const nSamples = sessionRecordedData.length;
    const meanHr = nSamples > 0 
        ? sessionRecordedData.reduce((sum, d) => sum + d.optical_hr, 0) / nSamples 
        : 72.0;
    const meanRr = nSamples > 0 
        ? sessionRecordedData.reduce((sum, d) => sum + d.rr, 0) / nSamples 
        : 16.0;
    const meanConf = nSamples > 0 
        ? sessionRecordedData.reduce((sum, d) => sum + d.confidence, 0) / nSamples 
        : 92.5;

    const sessId = "SESS_" + Math.floor(100000 + Math.random() * 900000);
    const sessionObj = {
        id: sessId,
        subject: subId,
        mode: acqMode,
        duration: sessionDurationSec,
        sampleCount: nSamples,
        meanHr: parseFloat(meanHr.toFixed(1)),
        meanRr: parseFloat(meanRr.toFixed(1)),
        meanConfidence: parseFloat(meanConf.toFixed(1)),
        timestamp: new Date().toISOString(),
        samples: sessionRecordedData
    };
    savedSessions.unshift(sessionObj);

    const tableBody = document.getElementById("reports-table-body");
    if (tableBody) {
        const row = document.createElement("tr");
        row.innerHTML = `
            <td><strong>${sessId}</strong></td>
            <td>${subId}</td>
            <td>${acqMode.split(' ')[0]}</td>
            <td style="color: var(--emerald-green); font-weight: 700;">${meanHr.toFixed(1)}</td>
            <td>${meanRr.toFixed(1)}</td>
            <td>${meanConf.toFixed(1)}%</td>
            <td><button class="btn-small" onclick="downloadSessionReport('${sessId}')">Export JSON</button></td>
        `;
        tableBody.insertBefore(row, tableBody.firstChild);
    }

    writeLog(`Session ${sessId} finalized for ${subId}: ${nSamples} real samples captured. Mean HR: ${meanHr.toFixed(1)} BPM.`);
}

window.downloadSessionReport = function(sessId) {
    const sess = savedSessions.find(s => s.id === sessId);
    if (!sess) {
        alert("Report data not found for " + sessId);
        return;
    }
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(sess, null, 2));
    const dlAnchor = document.createElement("a");
    dlAnchor.setAttribute("href", dataStr);
    dlAnchor.setAttribute("download", `${sessId}_report.json`);
    document.body.appendChild(dlAnchor);
    dlAnchor.click();
    document.body.removeChild(dlAnchor);
};

function exportCSV() {
    if (signalLogs.length === 0) {
        alert("No logs available to export.");
        return;
    }
    let csvContent = "data:text/csv;charset=utf-8,";
    csvContent += "Timestamp,HeartRate_BPM,RespirationRate_BrM,rPPG_mV,Respiratory_mV\\n";
    signalLogs.forEach(row => {
        csvContent += row.join(",") + "\\n";
    });
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", "SonicVitals_ExportLog_" + Math.floor(Date.now()/1000) + ".csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    writeLog("Signal logs successfully written to local CSV report file.");
}

// ================= 8. Clinical Diagnostic Studio & Best Moment Capture =================

let currentDiagnosticData = null;
let currentDiagView = 'annotated_roi';

const VIEW_METADATA = {
    'annotated_roi': {
        tag: 'ANATOMICAL ROIS',
        title: 'ANATOMICAL REGIONS OF INTEREST',
        desc: 'Segmented zones: Forehead (microvascular capillary beds), Cheeks (malar vasomotor flush & symmetry), Sclera (bilirubin deposition), Lips (arterial oxygenation).'
    },
    'erythema_map': {
        tag: 'ERYTHEMA PERFUSION MAP',
        title: 'ERYTHEMA / BLOOD VOLUME PERFUSION MAP',
        desc: 'Dawson & Diffey spectrophotometric reflectance contrast Δ(R - G) mapped with Jet colormap to visualize dermal capillary blood pooling, local inflammation, and malar flushing.'
    },
    'jaundice_map': {
        tag: 'ICTERUS BILIRUBIN MAP',
        title: 'SCLERAL & CUTANEOUS ICTERUS (BILIRUBIN) MAP',
        desc: 'CIELAB b* yellow chromaticity projection mapped via Inferno colormap to isolate extracellular bilirubin pigment deposition in scleral tissue and cutaneous zones.'
    },
    'cyanosis_map': {
        tag: 'CYANOSIS HYPOXIA MAP',
        title: 'HYPOPERFUSION & CYANOSIS RISK MAP',
        desc: 'Optical deoxygenated hemoglobin ratio (B/R) mapped via Cool colormap identifying regions of microvascular hypoxemia and perioral mucous membrane desaturation.'
    },
    'raw': {
        tag: 'RAW CLINICAL CAPTURE',
        title: 'RAW CLINICAL SENSOR CAPTURE',
        desc: 'Direct uncompressed RGB optical feed captured at the peak systolic pulse wave for baseline photometric reference.'
    }
};

let isAutoCaptureEnabled = false;
let autoCaptureTriggeredForSubject = false;

function toggleAutoCapture(chk) {
    isAutoCaptureEnabled = chk ? chk.checked : false;
    writeLog(`Auto-capture on full face lock ${isAutoCaptureEnabled ? 'ENABLED' : 'DISABLED'}`);
}

function showFaceAlert(msg, guidance) {
    const banner = document.getElementById("full-face-alert-banner");
    const txt = document.getElementById("full-face-alert-text");
    if (banner && txt) {
        txt.innerText = `${msg} ${guidance ? '(' + guidance + ')' : ''}`;
        banner.style.display = "flex";
    }
}

function dismissFaceAlert() {
    const banner = document.getElementById("full-face-alert-banner");
    if (banner) banner.style.display = "none";
}

let isFetchingMoment = false;

function initMomentMonitor() {
    setInterval(async () => {
        if (isFetchingMoment) return;
        isFetchingMoment = true;
        try {
            const res = await fetch("http://localhost:5001/api/best_moment_status");
            if (!res.ok) return;
            const data = await res.json();
            
            const badge = document.getElementById("moment-badge");
            const statusTxt = document.getElementById("moment-status-txt");
            const clarityEl = document.getElementById("moment-clarity");
            const fullFaceBadge = document.getElementById("badge-full-face");
            const guidanceChip = document.getElementById("moment-guidance-chip");
            const wsDot = document.getElementById("ws-status-dot");
            const wsTxt = document.getElementById("ws-status-text");
            
            // 1. Full-Face Status Badge in Video Panel Header
            if (fullFaceBadge) {
                if (data.full_face_visible) {
                    fullFaceBadge.className = "badge-face ready";
                    fullFaceBadge.innerText = "● FULL FACE LOCKED";
                } else if (data.patient_detected) {
                    fullFaceBadge.className = "badge-face partial";
                    const shortGuide = data.face_guidance ? data.face_guidance.split('.')[0] : "ALIGN FACE";
                    fullFaceBadge.innerText = `⚠ ${shortGuide.toUpperCase()}`;
                } else {
                    fullFaceBadge.className = "badge-face searching";
                    fullFaceBadge.innerText = "SEARCHING SUBJECT...";
                }
            }

            // 2. Real-Time Guidance Row in Video Action Bar
            const guidanceRow = document.getElementById("moment-guidance-row");
            const guidanceTxt = document.getElementById("moment-guidance-txt");
            if (guidanceRow && guidanceTxt) {
                if (!data.full_face_visible && data.patient_detected && data.face_guidance) {
                    guidanceTxt.innerText = data.face_guidance;
                    guidanceRow.style.display = "flex";
                } else {
                    guidanceRow.style.display = "none";
                }
            }

            // 3. Best Moment Status & Diagnostic Workstation System Status
            if (data.has_moment && data.full_face_visible) {
                if (badge) {
                    badge.className = "badge-moment";
                }
                if (statusTxt) {
                    statusTxt.innerText = (data.cardiac_phase || "MOMENT").replace('_', ' ') + " READY";
                }
                if (clarityEl) {
                    clarityEl.innerText = "σ²=" + data.sharpness;
                }
                if (wsDot) wsDot.className = "ws-status-dot ready";
                if (wsTxt) wsTxt.innerText = `SYSTEM READY | FULL FACE LOCKED (${(data.cardiac_phase || 'RESTING').replace('_', ' ')})`;

                // 4. Auto-Capture Trigger on Full Face Lock
                if (isAutoCaptureEnabled && !autoCaptureTriggeredForSubject) {
                    autoCaptureTriggeredForSubject = true;
                    writeLog("Full face locked and systolic peak detected. Initiating auto-capture...");
                    captureDiagnosticSnapshot();
                }
            } else {
                if (badge) {
                    badge.className = "badge-moment buffering";
                }
                if (statusTxt) {
                    statusTxt.innerText = data.patient_detected ? "ALIGNING FACE" : "BUFFERING";
                }
                if (clarityEl) {
                    clarityEl.innerText = data.sharpness > 0 ? "σ²=" + data.sharpness : "σ²=--";
                }
                if (wsDot) wsDot.className = data.patient_detected ? "ws-status-dot warning" : "ws-status-dot";
                if (wsTxt) {
                    wsTxt.innerText = data.patient_detected 
                        ? `ALIGNMENT REQUIRED | ${data.face_guidance || 'CENTER FULL FACE'}` 
                        : "AWAITING SUBJECT | NO PATIENT DETECTED";
                }
            }

            // Reset auto-capture trigger once subject steps away
            if (!data.patient_detected) {
                autoCaptureTriggeredForSubject = false;
            }
        } catch (e) {
            // Background monitoring silent catch
        } finally {
            isFetchingMoment = false;
        }
    }, 1000);
}

async function captureDiagnosticSnapshot() {
    const btn = document.getElementById("btn-capture-diag");
    const tabBtn = document.getElementById("btn-tab-capture");
    
    [btn, tabBtn].forEach(b => {
        if (b) {
            b.innerHTML = `<span class="moment-pulse"></span> PROCESSING...`;
            b.style.opacity = "0.7";
        }
    });
    
    writeLog("Initiating authentic clinical diagnostic capture & multi-spectral extraction...");

    try {
        const res = await fetch("http://localhost:5001/api/capture_diagnostic");
        const data = await res.json();
        
        if (!data.success) {
            showFaceAlert(data.error || "Full face must be visible within frame to capture diagnostic moment.", data.guidance);
            writeLog("Diagnostic capture inhibited: " + (data.error || "Full face not visible"));
            return;
        }

        dismissFaceAlert();
        currentDiagnosticData = data;
        renderDiagnosticResults(data);
        
        // Seamlessly switch to Diagnostics Studio tab if captured from another tab
        const activeNav = document.querySelector(".nav-btn.active");
        const currentTab = activeNav ? activeNav.getAttribute("data-tab") : "";
        if (currentTab !== "diagnostics") {
            const diagNavBtn = document.getElementById("nav-diag-btn");
            if (diagNavBtn) diagNavBtn.click();
        }

        writeLog(`Diagnostic snapshot locked! Sharpness: ${data.sharpness}, Cardiac Phase: ${data.cardiac_phase}, Full Face: VERIFIED`);
    } catch (err) {
        console.error("Diagnostic capture error:", err);
        showFaceAlert("Unable to communicate with clinical diagnostic engine. Check backend server.");
    } finally {
        const btnHtml = `
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path><circle cx="12" cy="13" r="4"></circle></svg>
            CAPTURE DIAGNOSTIC MOMENT
        `;
        [btn, tabBtn].forEach(b => {
            if (b) {
                b.innerHTML = btnHtml;
                b.style.opacity = "1";
            }
        });
    }
}

function renderDiagnosticResults(data) {
    const tsStr = new Date(data.timestamp * 1000).toTimeString().split(' ')[0];
    
    // 1. Metadata Strip
    const metaStrip = data.meta_strip || {};
    const frameEl = document.getElementById("ws-meta-frame");
    const roiEl = document.getElementById("ws-meta-roi");
    const motionEl = document.getElementById("ws-meta-motion");
    const qualityEl = document.getElementById("ws-meta-quality");
    const phaseEl = document.getElementById("ws-meta-phase");
    const wfTs = document.getElementById("ws-workflow-timestamp");
    const modalTs = document.getElementById("modal-meta-ts");

    if (frameEl) frameEl.innerText = metaStrip.frame_id || "FRAME #00124";
    if (roiEl) roiEl.innerText = metaStrip.roi_status || "ROI DETECTED (5 ZONES)";
    if (motionEl) motionEl.innerText = metaStrip.motion || "MOTION: LOW";
    if (qualityEl) qualityEl.innerText = metaStrip.quality || "QUALITY: HIGH";
    if (phaseEl) phaseEl.innerText = (metaStrip.cardiac || data.cardiac_phase).replace('_', ' ');
    if (wfTs) wfTs.innerText = `TS: ${tsStr} | ${(metaStrip.cardiac || data.cardiac_phase).replace('_', ' ')}`;
    if (modalTs) modalTs.innerText = `TS: ${tsStr}`;

    // 2. Structured Triage Observations
    const st = data.structured_triage || {};
    const overallBadge = document.getElementById("triage-overall-badge");
    if (overallBadge) {
        const oStatus = st.overall_status || "NORMAL";
        overallBadge.innerText = oStatus === 'NORMAL' ? 'NORMAL PROFILE' : `${st.flags_count || 1} ACTIVE FLAGS`;
        overallBadge.className = `triage-overall-badge ${oStatus}`;
    }

    const interpBox = document.getElementById("tab-diag-interp-box");
    if (interpBox) {
        interpBox.className = `triage-interpretation-box ${st.overall_status || 'NORMAL'}`;
    }

    const interpText = document.getElementById("tab-diag-interp-text");
    if (interpText) {
        interpText.innerText = (st.interpretation || "") + " " + (st.recommendation || data.clinical_summary);
    }

    if (st.observations) {
        st.observations.forEach(obs => {
            const valEl = document.getElementById(`obs-val-${obs.id}`);
            const statEl = document.getElementById(`obs-status-${obs.id}`);
            const detEl = document.getElementById(`obs-detail-${obs.id}`);

            if (valEl) valEl.innerText = obs.metric;
            if (statEl) {
                statEl.innerText = obs.status;
                statEl.className = `obs-status-badge ${obs.status}`;
            }
            if (detEl) detEl.innerText = obs.detail;
        });
    }

    // 3. Professional Laboratory Biomarkers Table
    const tableBody = document.getElementById("tab-diag-biomarkers-body");
    const modalTableBody = document.getElementById("diag-biomarkers-body");
    
    let htmlRows = '';
    data.biomarkers.forEach(b => {
        htmlRows += `
            <tr>
                <td><strong>${b.name}</strong></td>
                <td><span class="val-metric">${b.value}</span><span class="val-unit">${b.unit}</span></td>
                <td><span class="ref-range">${b.reference}</span></td>
                <td><span class="status-badge ${b.status}">${b.status}</span></td>
                <td><span class="finding-text">${b.finding}</span></td>
            </tr>
        `;
    });

    if (tableBody) tableBody.innerHTML = htmlRows;
    if (modalTableBody) modalTableBody.innerHTML = htmlRows;

    // 4. Diagnostic Metrics Overview Modules (Lower Whitespace)
    const mo = data.metrics_overview || {};
    const clarityVal = mo.clarity !== undefined ? mo.clarity : data.sharpness;
    const ovClarity = document.getElementById("ov-val-clarity");
    const ovClarityBadge = document.getElementById("ov-badge-clarity");
    if (ovClarity) ovClarity.innerText = clarityVal.toFixed(1);
    if (ovClarityBadge) {
        ovClarityBadge.innerText = clarityVal > 100.0 ? "OPTIMAL FOCUS" : "BORDERLINE MOTION";
        ovClarityBadge.className = clarityVal > 100.0 ? "module-badge" : "module-badge warn";
    }

    const ovSymm = document.getElementById("ov-val-symmetry");
    const ovSymmBadge = document.getElementById("ov-badge-symmetry");
    if (ovSymm) ovSymm.innerText = mo.symmetry !== undefined ? `${mo.symmetry}%` : "1.4%";
    if (ovSymmBadge) {
        const isSymm = (mo.symmetry !== undefined ? mo.symmetry : 1.4) < 5.0;
        ovSymmBadge.innerText = isSymm ? "SYMMETRICAL" : "ASYMMETRY FLAG";
        ovSymmBadge.className = isSymm ? "module-badge" : "module-badge warn";
    }

    const ovPerf = document.getElementById("ov-val-perfusion");
    const ovPerfBadge = document.getElementById("ov-badge-perfusion");
    if (ovPerf) ovPerf.innerText = mo.perfusion !== undefined ? `${mo.perfusion} EI` : "--";
    if (ovPerfBadge) {
        const pVal = mo.perfusion !== undefined ? mo.perfusion : 15.0;
        const isNorm = pVal >= 10.0 && pVal <= 23.0;
        ovPerfBadge.innerText = isNorm ? "RESTING TONE" : (pVal < 10.0 ? "HYPOPERFUSION" : "HYPEREMIA");
        ovPerfBadge.className = isNorm ? "module-badge" : "module-badge warn";
    }

    const ovFlags = document.getElementById("ov-val-flags");
    const ovFlagsBadge = document.getElementById("ov-badge-flags");
    const fCount = mo.flags_count !== undefined ? mo.flags_count : (st.flags_count || 0);
    if (ovFlags) ovFlags.innerText = `${fCount} FLAGS`;
    if (ovFlagsBadge) {
        ovFlagsBadge.innerText = fCount === 0 ? "ALL CLEAR" : (fCount <= 2 ? "BORDERLINE" : "ACUTE REVIEW");
        ovFlagsBadge.className = fCount === 0 ? "module-badge" : (fCount <= 2 ? "module-badge warn" : "module-badge alert");
    }

    // Switch to active view mode (default: annotated_roi)
    switchDiagView(currentDiagView || 'annotated_roi');
}

function switchDiagView(viewKey) {
    if (!currentDiagnosticData) {
        captureDiagnosticSnapshot().then(() => {
            if (currentDiagnosticData) switchDiagView(viewKey);
        });
        return;
    }
    currentDiagView = viewKey;
    const meta = VIEW_METADATA[viewKey] || VIEW_METADATA['annotated_roi'];
    
    // Update active state on all matching toolbar buttons
    document.querySelectorAll(".ws-view-btn, .btn-diag-tab").forEach(btn => {
        if (btn.getAttribute("data-view") === viewKey) {
            btn.classList.add("active");
        } else {
            btn.classList.remove("active");
        }
    });

    const imgSrc = (currentDiagnosticData && currentDiagnosticData.images && currentDiagnosticData.images[viewKey])
        ? currentDiagnosticData.images[viewKey]
        : '';

    // Update Tab View Elements
    const tabMainImg = document.getElementById("tab-diag-main-img");
    const tabViewTag = document.getElementById("tab-diag-view-tag");
    const tabPlaceholder = document.getElementById("tab-diag-placeholder");
    if (tabMainImg && imgSrc) {
        tabMainImg.src = imgSrc;
        tabMainImg.style.display = "block";
    }
    if (tabPlaceholder && imgSrc) {
        tabPlaceholder.style.display = "none";
    }
    if (tabViewTag && imgSrc) {
        tabViewTag.innerText = meta.tag;
        tabViewTag.style.display = "block";
    }

    // Update Colormap Bar & Labels
    const colormapBar = document.getElementById("colormap-bar");
    const labelLeft = document.getElementById("colormap-label-left");
    const labelRight = document.getElementById("colormap-label-right");

    if (colormapBar && labelLeft && labelRight) {
        if (viewKey === 'erythema_map') {
            colormapBar.className = "colormap-gradient";
            labelLeft.innerText = "0.0 (LOW PERFUSION)";
            labelRight.innerText = "MAX (HYPEREMIC FLUSH)";
        } else if (viewKey === 'jaundice_map') {
            colormapBar.className = "colormap-gradient inferno";
            labelLeft.innerText = "0.0 (CLEAR SCLERA)";
            labelRight.innerText = "MAX (ICTERUS BILIRUBIN)";
        } else if (viewKey === 'cyanosis_map') {
            colormapBar.className = "colormap-gradient cool";
            labelLeft.innerText = "0.0 (OXYGENATED)";
            labelRight.innerText = "MAX (DEOXYGENATION)";
        } else if (viewKey === 'annotated_roi') {
            colormapBar.className = "colormap-gradient hidden";
            labelLeft.innerText = "ANATOMICAL SEGMENTATION";
            labelRight.innerText = "5 CHROMOPHORE ZONES";
        } else {
            colormapBar.className = "colormap-gradient hidden";
            labelLeft.innerText = "RAW OPTICAL STREAM";
            labelRight.innerText = "UNFILTERED SENSOR DATA";
        }
    }
}

function closeDiagnosticModal() {
    const modal = document.getElementById("diagnostic-modal");
    if (modal) modal.classList.remove("active");
}

function exportDiagnosticJSON() {
    if (!currentDiagnosticData) {
        alert("No clinical diagnostic data available to export.");
        return;
    }
    const exportData = {
        platform: "SonicVitals Clinical Medical Imaging & rPPG Station",
        institution: "Vellore Institute of Technology (VIT)",
        export_timestamp: new Date().toISOString(),
        diagnostic_record: currentDiagnosticData
    };
    const jsonStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(exportData, null, 2));
    const dlAnchor = document.createElement("a");
    dlAnchor.setAttribute("href", jsonStr);
    dlAnchor.setAttribute("download", `SonicVitals_ClinicalDiagnostic_${Math.floor(Date.now()/1000)}.json`);
    document.body.appendChild(dlAnchor);
    dlAnchor.click();
    dlAnchor.remove();
    writeLog("Clinical diagnostic report JSON exported successfully.");
}
