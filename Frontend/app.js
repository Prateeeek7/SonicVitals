// SonicVitals browser workstation.
// Every number shown here comes from the host engine (http://localhost:5001).
// Nothing is simulated in the browser: if a quantity is unavailable it is shown as "--".

const API = "http://localhost:5001";

document.addEventListener("DOMContentLoaded", () => {
    initTabs();
    initPlotlyCharts();
    initRealTimeVitalsStream();
    initAudioStream();
    initDeviceMonitor();
    initConfigView();
    initMomentMonitor();
    initVideoAutoRecovery();
    initCameraSwitch();
    initMethodsPanel();
    writeLog("Workstation loaded. Waiting for the host engine at " + API + ".");
});

// ================= 1. Navigation =================
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
                if (!currentDiagnosticData) captureDiagnosticSnapshot();
                else renderDiagnosticResults(currentDiagnosticData);
            } else if (targetTab === "analysis") {
                if (lastVitalsData) renderSignalAnalysis(lastVitalsData, true);
            } else if (targetTab === "experiments") {
                updateBlandAltmanCanvas(liveAgreementPoints);
                updateTrendTrackerCanvas(liveTrendPoints);
            }

            // Plots drawn while their tab was hidden have Plotly's default size: fit them now.
            requestAnimationFrame(() => {
                if (!targetEl || typeof Plotly === "undefined") return;
                targetEl.querySelectorAll(".js-plotly-plot").forEach(gd => Plotly.Plots.resize(gd));
            });
        });
    });
}

// ================= 2. Charts =================
const PLOT_CONFIG = { displayModeBar: false, responsive: true };
let lastVitalsData = null;

function layoutDefaults(title, yTitle, xTitle) {
    return {
        title: {
            text: title.toUpperCase(),
            font: { family: "Inter, IBM Plex Sans", size: 9, weight: "bold", color: "#3A3A3A" },
            xref: "paper", x: 0.02, y: 0.95
        },
        margin: { l: 45, r: 15, t: 30, b: 32 },
        paper_bgcolor: "#F2F2EE",
        plot_bgcolor: "#FAFAF8",
        xaxis: {
            showgrid: true, gridcolor: "#D3D3CB", tickfont: { size: 8, family: "monospace" },
            title: { text: xTitle || "", font: { size: 8 } }
        },
        yaxis: {
            showgrid: true, gridcolor: "#D3D3CB", tickfont: { size: 8, family: "monospace" },
            title: { text: yTitle, font: { size: 8 } }
        }
    };
}

function relTimeAxis(n, fs) {
    // Seconds relative to the newest sample (0 = now).
    return Array.from({ length: n }, (_, i) => (i - (n - 1)) / fs);
}

function initPlotlyCharts() {
    const audioLayout = layoutDefaults("", "Normalized amplitude", "Time (s)");
    audioLayout.margin = { l: 45, r: 15, t: 15, b: 32 };
    Plotly.newPlot("audio-plot", [{
        x: [], y: [], type: "scatter", mode: "lines",
        line: { color: "#6B8E23", width: 1.0 }
    }], audioLayout, PLOT_CONFIG);

    Plotly.newPlot("rppg-plot", [{
        x: [], y: [], type: "scatter", mode: "lines",
        line: { color: "#0F6A4A", width: 1.5 }
    }],
        layoutDefaults("Recovered pulse (CHROM, 0.75-2.5 Hz)", "z-score (a.u.)", "Time (s)"), PLOT_CONFIG);

    Plotly.newPlot("resp-plot", [{
        x: [], y: [], type: "scatter", mode: "lines",
        line: { color: "#B85430", width: 1.5 }
    }],
        layoutDefaults("Respiratory waveform (green, 0.15-0.40 Hz)", "z-score (a.u.)", "Time (s)"), PLOT_CONFIG);

    Plotly.newPlot("fft-plot", [{
        x: [], y: [], type: "scatter", mode: "lines",
        line: { color: "#0F6A4A", width: 1.5 }
    }],
        layoutDefaults("rPPG power spectral density (Welch)", "Relative power (dB)", "Frequency (Hz)"), PLOT_CONFIG);

    const specLayout = layoutDefaults("Chest microphone spectrogram (STFT, dB)", "Frequency (Hz)", "Time (s)");
    Plotly.newPlot("spectrogram-plot", [{
        z: [[0]], x: [0], y: [0], type: "heatmap", zmin: -60, zmax: 0,
        colorscale: [[0, "#F2F2EE"], [0.5, "#6B8E23"], [1.0, "#0F6A4A"]], showscale: false
    }],
        specLayout, PLOT_CONFIG);

    Plotly.newPlot("detrended-plot", [{
        x: [], y: [], type: "scatter", mode: "lines",
        line: { color: "#6E6E66", width: 1.2 }
    }],
        layoutDefaults("Standardized pulse signal", "z-score (a.u.)", "Time (s)"), PLOT_CONFIG);

    Plotly.newPlot("wavelet-plot", [
        { x: [], y: [], name: "Trend (moving average)", type: "scatter", mode: "lines", line: { color: "#0F6A4A", width: 1.2 } },
        { x: [], y: [], name: "Pulsatile (signal - trend)", type: "scatter", mode: "lines", line: { color: "#D98C00", width: 0.9 } },
        { x: [], y: [], name: "First difference", type: "scatter", mode: "lines", line: { color: "#B85430", width: 0.6 } }
    ], Object.assign(layoutDefaults("Moving-average decomposition", "z-score (a.u.)", "Time (s)"), {
        legend: { orientation: "h", x: 0, y: -0.22, font: { size: 8 } }, margin: { l: 45, r: 15, t: 30, b: 58 }
    }), PLOT_CONFIG);

    const hrLayout = layoutDefaults("Heart rate history (last 5 min)", "Heart rate (BPM)", "Time (s)");
    hrLayout.showlegend = true;
    hrLayout.legend = { orientation: "h", x: 0, y: -0.28, font: { size: 8 } };
    hrLayout.margin = { l: 45, r: 15, t: 30, b: 58 };
    hrLayout.yaxis.range = [40, 150];
    Plotly.newPlot("hr-trend-plot", [
        { x: [], y: [], name: "Displayed HR", type: "scatter", mode: "lines", line: { color: "#0F6A4A", width: 2.2 } },
        { x: [], y: [], name: "Camera estimate (accepted)", type: "scatter", mode: "markers", marker: { color: "#0F6A4A", size: 5 } },
        { x: [], y: [], name: "Camera estimate (rejected)", type: "scatter", mode: "markers",
          marker: { color: "rgba(0,0,0,0)", size: 5, line: { color: "#9A9A90", width: 1 } } },
        { x: [], y: [], name: "Microphone (PCG)", type: "scatter", mode: "markers", marker: { color: "#B85430", size: 5, symbol: "diamond" } },
        { x: [], y: [], name: "Tracked (high confidence)", type: "scatter", mode: "lines", line: { color: "#0F6A4A", width: 1.5, dash: "dot" } },
        { x: [], y: [], name: "Tracked (low confidence)", type: "scatter", mode: "lines", line: { color: "#D98C00", width: 1.2, dash: "dot" } }
    ], hrLayout, PLOT_CONFIG);

    const qLayout = layoutDefaults("Signal quality vs acceptance gate", "Pulse SNR (dB)", "Time (s)");
    qLayout.yaxis.range = [-12, 6];
    qLayout.showlegend = true;
    qLayout.legend = { orientation: "h", x: 0, y: -0.28, font: { size: 8 } };
    qLayout.margin = { l: 45, r: 45, t: 30, b: 58 };
    qLayout.yaxis2 = { overlaying: "y", side: "right", range: [-0.2, 2.6], dtick: 1, showgrid: false,
                       tickfont: { size: 8, family: "monospace" }, title: { text: "Methods agreeing", font: { size: 8 } } };
    Plotly.newPlot("quality-plot", [
        { x: [], y: [], name: "SNR", type: "scatter", mode: "lines", line: { color: "#3A3A3A", width: 1.4 } },
        { x: [], y: [], name: "Gate (SNR)", type: "scatter", mode: "lines", line: { color: "#B85430", width: 1.2, dash: "dash" } },
        { x: [], y: [], name: "POS / green agreeing with CHROM", type: "scatter", mode: "lines", yaxis: "y2",
          line: { color: "#D98C00", width: 1, shape: "hv" }, fill: "tozeroy", fillcolor: "rgba(217,140,0,0.12)" }
    ], qLayout, PLOT_CONFIG);

    const rgbLayout = layoutDefaults("Skin colour change (gated skin boxes, motion-suppressed)", "Change from mean (%)", "Time (s)");
    rgbLayout.showlegend = true;
    rgbLayout.legend = { orientation: "h", x: 0, y: -0.22, font: { size: 8 } };
    rgbLayout.margin = { l: 45, r: 15, t: 30, b: 58 };
    Plotly.newPlot("rgb-plot", [
        { x: [], y: [], name: "Red", type: "scatter", mode: "lines", line: { color: "#C0392B", width: 1 } },
        { x: [], y: [], name: "Green", type: "scatter", mode: "lines", line: { color: "#27AE60", width: 1 } },
        { x: [], y: [], name: "Blue", type: "scatter", mode: "lines", line: { color: "#2E86C1", width: 1 } }
    ], rgbLayout, PLOT_CONFIG);

    const mLayout = layoutDefaults("Method agreement: CHROM vs POS vs green", "Heart rate (BPM)", "Time (s)");
    mLayout.showlegend = true;
    mLayout.legend = { orientation: "h", x: 0, y: -0.22, font: { size: 8 } };
    mLayout.margin = { l: 45, r: 15, t: 30, b: 58 };
    mLayout.yaxis.range = [40, 150];
    Plotly.newPlot("methods-plot", [
        { x: [], y: [], name: "CHROM", type: "scatter", mode: "lines+markers", line: { color: "#0F6A4A", width: 1.2 }, marker: { size: 4 } },
        { x: [], y: [], name: "POS", type: "scatter", mode: "lines+markers", line: { color: "#D98C00", width: 1.2 }, marker: { size: 4 } },
        { x: [], y: [], name: "Green", type: "scatter", mode: "lines+markers", line: { color: "#6B8E23", width: 1.2, dash: "dot" }, marker: { size: 4 } }
    ], mLayout, PLOT_CONFIG);

    initBlandAltman();
    initTrendTracker();
}

// ================= 2b. History of what was shown, and why =================
const HISTORY_S = 300;
let hrHistory = [];
let lastHistoryT = 0;

function recordHistory(d) {
    const now = Date.now() / 1000;
    if (now - lastHistoryT < 1.0) return;
    lastHistoryT = now;
    const face = !!d.patient_detected;
    hrHistory.push({
        t: now, hr: d.hr, opt: face ? d.optical_hr : null, ok: !!d.optical_hr_ok, aco: d.acoustic_hr,
        snr: face ? d.cardiac_snr : null, gate: d.snr_gate_db, cons: face && d.optical_hr != null ? d.optical_consensus : null,
        pos: face ? d.optical_hr_pos : null, green: face ? d.optical_hr_green : null,
        trk: face ? d.tracked_hr : null, trkc: face ? d.tracked_conf : null,
        why: face && d.optical_hr != null ? hrRejectionReason(d) : ""
    });
    while (hrHistory.length && now - hrHistory[0].t > HISTORY_S) hrHistory.shift();
    renderHistory();
}

function renderHistory() {
    if (!hrHistory.length) return;
    const now = hrHistory[hrHistory.length - 1].t;
    const x = hrHistory.map(h => h.t - now);
    const pick = (f) => hrHistory.map(h => { const v = f(h); return v == null ? null : v; });
    try {
        const hi = (h) => h.trk != null && h.trkc >= 0.8;
        Plotly.update("hr-trend-plot", {
            x: [x, x, x, x, x, x],
            y: [pick(h => h.hr), pick(h => h.ok ? h.opt : null), pick(h => h.ok ? null : h.opt), pick(h => h.aco),
                pick(h => hi(h) ? h.trk : null), pick(h => h.trk != null && !hi(h) ? h.trk : null)],
            text: [[], [], hrHistory.map(h => h.why), [], hrHistory.map(h => h.trkc), hrHistory.map(h => h.trkc)],
            hovertemplate: [null, "%{y:.1f} BPM accepted<extra></extra>", "%{y:.1f} BPM: %{text}<extra></extra>", null,
                "tracked %{y:.1f} BPM, confidence %{text:.0%}<extra></extra>", "tracked %{y:.1f} BPM, confidence %{text:.0%}<extra></extra>"]
        });
        Plotly.update("quality-plot", {
            x: [x, x, x],
            y: [pick(h => h.snr), pick(h => h.snr == null ? null : h.gate), pick(h => h.cons)]
        });
        const analysisTab = document.getElementById("tab-analysis");
        if (analysisTab && analysisTab.classList.contains("active")) {
            Plotly.update("methods-plot", {
                x: [x, x, x], y: [pick(h => h.opt), pick(h => h.pos), pick(h => h.green)]
            });
        }
    } catch (err) { }
}

function renderFaceBadge(d) {
    const badge = document.getElementById("badge-full-face");
    if (!badge) return;
    if (d.full_face_visible) {
        badge.className = "badge-face ready";
        badge.innerText = "● FULL FACE (GATE PASSED)";
    } else if (d.patient_detected) {
        badge.className = "badge-face partial";
        badge.innerText = "⚠ " + (d.face_guidance ? d.face_guidance.split(".")[0] : "ALIGN FACE").toUpperCase();
    } else {
        badge.className = "badge-face searching";
        badge.innerText = "SEARCHING SUBJECT...";
    }
}

// ================= 3. Experiments: optical vs acoustic agreement =================
let liveAgreementPoints = [];
let liveTrendPoints = [];
let lastAgreementUpdate = 0;
let sessionActive = false;
let sessionStartTime = 0;
let sessionDurationSec = 60;
let sessionRecordedData = [];
let sessionTimerInterval = null;
let sessionBackendId = null;
let savedSessions = [];

function initBlandAltman() {
    liveAgreementPoints = [];
    Plotly.newPlot("bland-altman-canvas", [
        { x: [], y: [], type: "scatter", mode: "markers", marker: { color: "#0F6A4A", size: 6 } },
        { x: [40, 140], y: [0, 0], type: "scatter", mode: "lines", line: { color: "#3A3A3A", width: 1.5 } },
        { x: [40, 140], y: [0, 0], type: "scatter", mode: "lines", line: { color: "#B85430", width: 1.2, dash: "dash" } },
        { x: [40, 140], y: [0, 0], type: "scatter", mode: "lines", line: { color: "#B85430", width: 1.2, dash: "dash" } }
    ], Object.assign(layoutDefaults("Bland-Altman: optical vs acoustic HR",
        "Optical - acoustic (BPM)", "Mean of optical and acoustic HR (BPM)"), { showlegend: false }), PLOT_CONFIG);
    updateExperimentStats(0);
}

function initTrendTracker() {
    liveTrendPoints = [];
    const layout = layoutDefaults("Optical and acoustic heart rate", "Heart rate (BPM)", "Elapsed (s)");
    layout.showlegend = true;
    layout.legend = { font: { size: 8, family: "monospace" }, orientation: "h", x: 0.02, y: 1.15 };
    Plotly.newPlot("trend-tracker-canvas", [
        {
            x: [], y: [], type: "scatter", mode: "lines+markers", name: "Optical rPPG (BPM)",
            line: { color: "#0F6A4A", width: 1.5 }, marker: { size: 4, color: "#0F6A4A" }
        },
        {
            x: [], y: [], type: "scatter", mode: "lines+markers", name: "Acoustic PCG (BPM)",
            line: { color: "#B85430", width: 1.5, dash: "dot" }, marker: { size: 4, color: "#B85430" }
        }
    ], layout, PLOT_CONFIG);
}

function agreementStats(points) {
    const n = points.length;
    if (n === 0) return null;
    const diffs = points.map(p => p.diff);
    const bias = diffs.reduce((a, b) => a + b, 0) / n;
    const sd = n > 1 ? Math.sqrt(diffs.reduce((a, b) => a + (b - bias) ** 2, 0) / (n - 1)) : 0;
    const mae = diffs.reduce((a, b) => a + Math.abs(b), 0) / n;
    const rmse = Math.sqrt(diffs.reduce((a, b) => a + b * b, 0) / n);
    let r = null;
    if (n >= 3) {
        const xs = points.map(p => p.optical), ys = points.map(p => p.acoustic);
        const mx = xs.reduce((a, b) => a + b, 0) / n, my = ys.reduce((a, b) => a + b, 0) / n;
        let num = 0, dx = 0, dy = 0;
        for (let i = 0; i < n; i++) {
            num += (xs[i] - mx) * (ys[i] - my);
            dx += (xs[i] - mx) ** 2;
            dy += (ys[i] - my) ** 2;
        }
        if (dx > 0 && dy > 0) r = num / Math.sqrt(dx * dy);
    }
    return { n, bias, sd, mae, rmse, r, lo: bias - 1.96 * sd, hi: bias + 1.96 * sd };
}

function updateBlandAltmanCanvas(points) {
    const st = agreementStats(points);
    if (!st) return;
    const means = points.map(p => (p.optical + p.acoustic) / 2);
    const minX = Math.max(35, Math.min(...means) - 10), maxX = Math.min(160, Math.max(...means) + 10);
    try {
        Plotly.update("bland-altman-canvas", {
            x: [means, [minX, maxX], [minX, maxX], [minX, maxX]],
            y: [points.map(p => p.diff), [st.bias, st.bias], [st.hi, st.hi], [st.lo, st.lo]]
        });
    } catch (err) { }
}

function updateTrendTrackerCanvas(points) {
    if (!points.length) return;
    try {
        Plotly.update("trend-tracker-canvas", {
            x: [points.map(p => p.time), points.map(p => p.time)],
            y: [points.map(p => p.optical), points.map(p => p.acoustic)]
        });
    } catch (err) { }
}

function setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.innerText = text;
}

function updateExperimentStats(n, st) {
    if (!n || !st) {
        ["stat-bias", "stat-mae", "stat-rmse", "stat-corr", "stat-sd"].forEach(id => setText(id, "--"));
        setText("stat-samples", "0");
        setText("exp-agreement-stats", "NEEDS SIMULTANEOUS OPTICAL AND ACOUSTIC HR");
        return;
    }
    setText("stat-samples", String(n));
    setText("stat-bias", (st.bias >= 0 ? "+" : "") + st.bias.toFixed(2));
    setText("stat-mae", st.mae.toFixed(2));
    setText("stat-rmse", st.rmse.toFixed(2));
    setText("stat-corr", st.r === null ? "--" : st.r.toFixed(3));
    setText("stat-sd", "±" + st.sd.toFixed(2));
    setText("exp-agreement-stats",
        `BIAS: ${st.bias >= 0 ? "+" : ""}${st.bias.toFixed(2)} BPM | 95% LoA: [${st.lo.toFixed(2)}, ${st.hi.toFixed(2)}] | N: ${n}`);
}

function handleAgreementSample(data) {
    // One point per 2 s display update, only when both channels produced an estimate.
    if (!data.display_updated || data.display_updated === lastAgreementUpdate) return;
    lastAgreementUpdate = data.display_updated;
    if (data.optical_hr == null || data.acoustic_hr == null) return;

    if (!sessionStartTime) sessionStartTime = Date.now();
    const elapsed = parseFloat(((Date.now() - sessionStartTime) / 1000).toFixed(1));
    const point = { optical: data.optical_hr, acoustic: data.acoustic_hr, diff: data.optical_hr - data.acoustic_hr, time: elapsed };
    liveAgreementPoints.push(point);
    if (liveAgreementPoints.length > 120) liveAgreementPoints.shift();
    liveTrendPoints.push(point);
    if (liveTrendPoints.length > 90) liveTrendPoints.shift();

    updateExperimentStats(liveAgreementPoints.length, agreementStats(liveAgreementPoints));
    const expTab = document.getElementById("tab-experiments");
    if ((expTab && expTab.classList.contains("active")) || sessionActive) {
        updateBlandAltmanCanvas(liveAgreementPoints);
        updateTrendTrackerCanvas(liveTrendPoints);
    }
}

// ================= 4. Vitals stream =================
let streamInterval = null;
let isFetchingVitals = false;
let signalLogs = [];
let lastLoggedUpdate = 0;
let lastTelemetryReceiptTime = Date.now();

function initRealTimeVitalsStream() {
    if (streamInterval) clearInterval(streamInterval);
    streamInterval = setInterval(async () => {
        if (isFetchingVitals) return;
        isFetchingVitals = true;
        try {
            const res = await fetch(API + "/api/vitals");
            if (res.ok) handleRealVitalsUpdate(await res.json());
        } catch (e) {
            // host not reachable; device monitor reports it
        } finally {
            isFetchingVitals = false;
        }
    }, 250);
}

function initVideoAutoRecovery() {
    const feed = document.getElementById("usb-cam-feed");
    if (!feed) return;
    feed.onerror = () => setTimeout(() => { feed.src = API + "/video_feed?t=" + Date.now(); }, 1000);
    setInterval(() => {
        const now = Date.now();
        if (now - lastTelemetryReceiptTime > 3500) {
            lastTelemetryReceiptTime = now;
            feed.src = API + "/video_feed?t=" + now;
        }
    }, 2000);
}

function fmt(v, digits) {
    return (v === null || v === undefined || Number.isNaN(v)) ? "--" : Number(v).toFixed(digits);
}

function sourceLabel(src) {
    if (src === "ESP32_S3_CAM") return "ESP32-S3";
    if (src === "LOCAL_CAMERA") return "HOST WEBCAM (FALLBACK)";
    return src || "--";
}

function handleRealVitalsUpdate(data) {
    lastTelemetryReceiptTime = Date.now();
    lastVitalsData = data;

    setText("video-meta", `SOURCE: ${sourceLabel(data.video_source)} | ${fmt(data.measured_fps, 1)} FPS (MEASURED)`);
    renderFaceBadge(data);
    recordHistory(data);
    renderSignalAnalysis(data, false);
    renderDashboardWaveforms(data);

    const statusEl = document.getElementById("vision-status");
    const now = new Date().toISOString().slice(11, 19);

    if (!data.patient_detected && data.fusion_source !== "acoustic") {
        if (statusEl) {
            statusEl.innerText = "NO PATIENT DETECTED (SEARCHING...)";
            statusEl.className = "acquisition-alert alert-danger";
        }
        ["val-hr", "val-rr", "val-hrv", "val-quality", "val-source", "val-spo2"].forEach(id => setText(id, "--"));
        setText("ts-hr", "TS: --:--:--");
        setText("ts-rr", "TS: --:--:--");
        setText("ts-hrv", "TS: --:--:--");
        setText("ts-quality", "TS: --:--:--");
        setText("ts-source", "OPT -- | PCG --");
        return;
    }

    if (statusEl) {
        if (data.status === "STABLE") {
            const sig = data.optical_hr_ok ? `SNR ${fmt(data.cardiac_snr, 1)} dB` : `LOW SIGNAL (SNR ${fmt(data.cardiac_snr, 1)} dB) - HOLD STILL`;
            statusEl.innerText = `FACE GATE PASSED | ${fmt(data.segment_seconds, 0)} s | ${sig}`;
            statusEl.className = "acquisition-alert";
        } else if (data.status === "REACQUIRING") {
            const held = data.hr_age_s != null ? ` | LAST VALUE HELD ${fmt(data.hr_age_s, 0)} s` : "";
            statusEl.innerText = `REACQUIRING: ${data.calibration_remaining_sec}s TO NEW ESTIMATE${held}`;
            statusEl.className = "acquisition-alert alert-warn";
        } else if (data.status === "CALIBRATING") {
            statusEl.innerText = `BUFFERING: ${data.calibration_remaining_sec}s REMAINING (${data.calibration_progress}%)`;
            statusEl.className = "acquisition-alert alert-warn";
        } else {
            statusEl.innerText = `ALIGN FACE: ${data.face_guidance || ""}`;
            statusEl.className = "acquisition-alert alert-warn";
        }
    }

    renderConfidenceCards(data);
    renderSecondaryCards(data, now);

    const qCard = document.getElementById("card-quality");
    if (qCard && data.quality != null) {
        qCard.className = "vital-card " + (data.quality >= 50 ? "border-green" : data.quality >= 25 ? "border-amber" : "border-terracotta");
    }

    handleAgreementSample(data);

    if (data.display_updated && data.display_updated !== lastLoggedUpdate) {
        lastLoggedUpdate = data.display_updated;
        signalLogs.push([new Date(data.display_updated * 1000).toISOString(), fmt(data.hr, 1), fmt(data.rr, 1),
        fmt(data.hrv, 1), data.fusion_source || "", fmt(data.optical_hr, 1), fmt(data.acoustic_hr, 1),
        fmt(data.quality, 1), data.video_source || ""]);
        if (signalLogs.length > 3000) signalLogs.shift();
        if (sessionActive) {
            sessionRecordedData.push({
                time: data.display_updated, hr: data.hr, rr: data.rr, hrv: data.hrv,
                optical_hr: data.optical_hr, acoustic_hr: data.acoustic_hr, quality: data.quality,
                source: data.fusion_source
            });
            setText("exp-samples", String(sessionRecordedData.length));
            const hrs = sessionRecordedData.map(d => d.hr).filter(v => v != null);
            if (hrs.length) setText("exp-mean-hr", (hrs.reduce((a, b) => a + b, 0) / hrs.length).toFixed(1) + " BPM");
        }
    }
}

// Heart-rate and breathing cards: the accepted value when every check passes; otherwise the
// current estimate, marked "~" in amber with the reason it is not (yet) accepted.
function setCard(valId, tsId, value, digits, low, note) {
    const el = document.getElementById(valId);
    if (el) {
        el.textContent = value == null ? "--" : (low ? "~" : "") + Number(value).toFixed(digits);
        el.classList.toggle("low-conf", !!low && value != null);
    }
    const ts = document.getElementById(tsId);
    if (ts) {
        ts.textContent = note;
        ts.classList.toggle("low-conf", !!low);
    }
}

function hrRejectionReason(d) {
    if ((d.segment_seconds || 0) < 10) return `BUFFERING ${fmt(d.segment_seconds, 0)}/10 s`;
    if (d.optical_hr_ok) return "CONFIRMING (3 AGREEING READINGS)";
    const why = [];
    if (d.cardiac_snr != null && d.snr_gate_db != null && d.cardiac_snr < d.snr_gate_db) why.push(`WEAK SIGNAL ${fmt(d.cardiac_snr, 1)} dB`);
    if (d.optical_consensus != null && d.optical_consensus < 2) why.push(`METHODS DISAGREE ${d.optical_consensus}/2`);
    if ((d.artifact_frac || 0) > 0.15) why.push("MOVEMENT");
    return "LOW CONFIDENCE: " + (why.join(", ") || "QUALITY CHECK");
}

function renderConfidenceCards(d) {
    const held = (age) => age != null && age > 3 ? ` | HELD ${fmt(age, 0)} s` : "";
    // Heart rate
    if (d.hr != null) {
        const src = d.fusion_source ? d.fusion_source.toUpperCase() : "";
        setCard("val-hr", "ts-hr", d.hr, 1, false, `ACCEPTED ${src}${d.cardiac_snr != null ? " | SNR " + fmt(d.cardiac_snr, 1) + " dB" : ""}${held(d.hr_age_s)}`);
    } else if (d.patient_detected && d.tracked_hr != null && d.tracked_conf >= (d.tracked_high_conf || 0.8)) {
        setCard("val-hr", "ts-hr", d.tracked_hr, 1, false, `TRACKED, HIGH CONFIDENCE ${fmt(100 * d.tracked_conf, 0)}% (${d.ensemble_spectra} SPECTRA)`);
    } else if (d.patient_detected && d.tracked_hr != null) {
        setCard("val-hr", "ts-hr", d.tracked_hr, 0, true, `TRACKED, LOW CONFIDENCE ${fmt(100 * d.tracked_conf, 0)}% | ` + hrRejectionReason(d).replace("LOW CONFIDENCE: ", ""));
    } else if (d.patient_detected && d.optical_hr != null) {
        setCard("val-hr", "ts-hr", d.optical_hr, 0, true, "CAMERA " + hrRejectionReason(d));
    } else if (d.acoustic_hr_estimate != null) {
        setCard("val-hr", "ts-hr", d.acoustic_hr_estimate, 0, true, "MICROPHONE ONLY: LOW CONFIDENCE (IRREGULAR BEATS)");
    } else {
        setCard("val-hr", "ts-hr", null, 0, false, d.patient_detected ? "BUFFERING" : "NO FACE / NO HEART SOUNDS");
    }
    // Breathing rate
    if (d.rr != null) {
        setCard("val-rr", "ts-rr", d.rr, 1, false, "ACCEPTED" + held(d.rr_age_s));
    } else if (d.patient_detected && d.optical_rr_estimate != null) {
        setCard("val-rr", "ts-rr", d.optical_rr_estimate, 0, true, `LOW CONFIDENCE: WEAK BREATHING PEAK (Q ${fmt(100 * (d.rr_quality || 0), 0)}%)`);
    } else {
        setCard("val-rr", "ts-rr", null, 0, false, !d.patient_detected ? "NO FACE"
            : (d.segment_seconds || 0) < 15 ? `NEEDS 15 s (${fmt(d.segment_seconds, 0)} s)` : "NO BREATHING PEAK");
    }
}

// ================= Live method comparison =================
const FAMILY_COLOR = { "Ours (gated + tracked)": "#0F6A4A", "Signal processing": "#D98C00", "Deep learning (PURE-trained)": "#2E86C1", "Acoustic": "#B85430" };

function initMethodsPanel() {
    const layout = layoutDefaults("Heart rate by method", "", "Heart rate (BPM)");
    layout.xaxis.range = [40, 150];
    layout.yaxis.automargin = true;
    layout.margin = { l: 120, r: 15, t: 30, b: 36 };
    Plotly.newPlot("methods-chart", [{ x: [], y: [], type: "scatter", mode: "markers", marker: { size: 12 } }], layout, PLOT_CONFIG);
    let busy = false;
    setInterval(async () => {
        if (busy) return;
        busy = true;
        try {
            const res = await fetch(API + "/api/methods");
            if (res.ok) renderMethods(await res.json());
        } catch (e) { } finally { busy = false; }
    }, 2000);
}

function renderMethods(m) {
    const body = document.getElementById("methods-body");
    if (!body) return;
    body.innerHTML = m.methods.map(r => {
        const est = r.hr == null && r.estimate != null;
        const off = r.hr == null && !est;
        const cls = (r.name === "SonicVitals" ? "ours " : "") + (off ? "off" : "");
        const dot = `<span style="color:${FAMILY_COLOR[r.family] || "#666"}">●</span>`;
        const val = r.hr != null ? Number(r.hr).toFixed(1) : est ? `<span class="low-conf-inline">~${Number(r.estimate).toFixed(1)}</span>` : "--";
        return `<tr class="${cls}"><td>${dot} ${r.name}</td><td>${r.family}</td><td class="hr-cell">${val}</td><td>${r.note || ""}</td></tr>`;
    }).join("");
    const pts = m.methods.filter(r => r.hr != null).reverse();
    try {
        Plotly.react("methods-chart", [{
            x: pts.map(r => r.hr), y: pts.map(r => r.name), type: "scatter", mode: "markers",
            marker: { size: 12, color: pts.map(r => FAMILY_COLOR[r.family] || "#666") },
            hovertemplate: "%{y}: %{x:.1f} BPM<extra></extra>"
        }], Object.assign(layoutDefaults("Heart rate by method", "", "Heart rate (BPM)"), {
            xaxis: { range: [40, 150], gridcolor: "#D3D3CB", tickfont: { size: 8, family: "monospace" }, title: { text: "Heart rate (BPM)", font: { size: 8 } } },
            yaxis: { automargin: true, tickfont: { size: 9 } },
            margin: { l: 120, r: 15, t: 30, b: 36 },
            shapes: m.median != null ? [{ type: "line", x0: m.median, x1: m.median, yref: "paper", y0: 0, y1: 1, line: { color: "#9A9A90", dash: "dot", width: 1 } }] : []
        }), PLOT_CONFIG);
    } catch (e) { }
    const agree = m.spread == null ? "--" : m.spread <= 6 ? `AGREE (spread ${m.spread} BPM)` : `DISAGREE (spread ${m.spread} BPM)`;
    setText("methods-meta", `MEDIAN ${m.median == null ? "--" : m.median} BPM | ${agree}`);
    setText("methods-foot", `Deep models: ${m.deep_status}` + (m.bg_rejected && m.bg_rejected.length ? ` | lighting peaks rejected (seen on the wall): ${m.bg_rejected.join(", ")} BPM` : ""));
}

// HRV, signal quality, HR source and SpO2: a value when one exists, otherwise the reason why not.
function renderSecondaryCards(d, now) {
    const micOn = !!d.acoustic_connected;
    // HRV comes from heart-sound beat timing (PCG); the camera signal is too weak to time single beats.
    if (d.hrv != null) {
        setCard("val-hrv", "ts-hrv", d.hrv, 0, false, "HEART SOUNDS (PCG) | TS: " + now);
    } else if (d.patient_detected && d.camera_rmssd != null) {
        setCard("val-hrv", "ts-hrv", d.camera_rmssd, 0, true, "CAMERA PULSE PEAKS, EXPLORATORY (15 Hz TIMING)");
    } else {
        setCard("val-hrv", "ts-hrv", null, 0, false, micOn ? "NEEDS 20 HEART-SOUND BEATS (MIC ON CHEST)"
            : "NEEDS HIGH-CONFIDENCE CAMERA TRACK OR ESP32 MIC ON CHEST");
    }
    // Signal quality: fused quality when an HR is accepted, otherwise the camera's spectral concentration.
    if (d.quality != null) {
        setCard("val-quality", "ts-quality", d.quality, 0, false, "MAX(Q_OPT, RHO_PCG)");
    } else if (d.patient_detected && d.optical_quality != null && d.optical_hr != null) {
        setCard("val-quality", "ts-quality", 100 * d.optical_quality, 0, true,
            `CAMERA ONLY, NOT ACCEPTED | SNR ${fmt(d.cardiac_snr, 1)} dB (GATE ${fmt(d.snr_gate_db, 0)})`);
    } else {
        setCard("val-quality", "ts-quality", null, 0, false, "NO SIGNAL YET");
    }
    // HR source: which sensor the accepted HR came from.
    const src = d.fusion_source ? d.fusion_source.toUpperCase() : null;
    setText("val-source", src ? (d.fusion_disagreement ? src + " (CONFLICT)" : src)
        : d.tracked_hr != null ? "CAMERA (TRACKED)" : "NONE");
    setText("ts-source", src ? `OPT ${fmt(d.optical_hr, 1)} | PCG ${fmt(d.acoustic_hr, 1)}`
        : `NO ACCEPTED HR | CAMERA TRACK ${fmt(d.tracked_hr, 0)} (${fmt(100 * (d.tracked_conf || 0), 0)}%) | MIC ${micOn ? "~" + fmt(d.acoustic_hr_estimate, 0) : "OFFLINE"}`);
    // SpO2 needs a per-camera calibration against a finger oximeter; without it no number is shown.
    if (d.spo2 != null) {
        setText("val-spo2", fmt(d.spo2, 1));
        setText("ts-spo2", "CALIBRATED FIT (EXPLORATORY)");
    } else {
        setText("val-spo2", "--");
        setText("ts-spo2", "NOT CALIBRATED: NEEDS FINGER-OXIMETER CALIBRATION" + (d.spo2_ratio != null ? ` | R=${fmt(d.spo2_ratio, 3)}` : ""));
    }
}

let dashRenderTick = 0;
function renderDashboardWaveforms(data) {
    if (++dashRenderTick % 2 !== 0) return;
    const fs = data.analysis_fs || 15;
    try {
        if (data.bvp_wave && data.bvp_wave.length) {
            Plotly.update("rppg-plot", { x: [relTimeAxis(data.bvp_wave.length, fs)], y: [data.bvp_wave] });
        }
        if (data.resp_wave && data.resp_wave.length) {
            Plotly.update("resp-plot", { x: [relTimeAxis(data.resp_wave.length, fs)], y: [data.resp_wave] });
        }
    } catch (err) { }
}

function renderSignalAnalysis(data, force) {
    if (!data) return;
    if (data.cardiac_peak_freq != null) {
        setText("sig-peak-freq", `${data.cardiac_peak_freq.toFixed(2)} Hz (${(data.cardiac_peak_freq * 60).toFixed(1)} BPM)`);
    } else {
        setText("sig-peak-freq", data.patient_detected ? "NEEDS 10 s SEGMENT" : "-- Hz (-- BPM)");
    }
    setText("sig-snr", data.cardiac_snr == null ? "-- dB" : `${data.cardiac_snr >= 0 ? "+" : ""}${data.cardiac_snr.toFixed(1)} dB`);
    setText("sig-sqi", data.optical_quality ? `${(100 * data.optical_quality).toFixed(1)}%` : "--%");
    setText("sig-resp-freq", data.optical_rr == null ? "-- Hz (-- BrPM)"
        : `${(data.optical_rr / 60).toFixed(3)} Hz (${data.optical_rr.toFixed(1)} BrPM)`);
    setText("sig-wavelet-ratio", data.optical_hr == null ? "--"
        : `${data.optical_consensus}/2 | ${fmt(100 * (data.artifact_frac || 0), 0)}% REPAIRED`
          + (data.still_trimmed_s ? ` | ${fmt(data.still_trimmed_s, 0)} s SKIPPED` : ""));
    setText("sig-stream-src", `${sourceLabel(data.video_source)} (${fmt(data.measured_fps, 1)} FPS)`);

    const analysisTab = document.getElementById("tab-analysis");
    if (!force && (!analysisTab || !analysisTab.classList.contains("active"))) return;

    const fs = data.analysis_fs || 15;
    try {
        Plotly.update("fft-plot", { x: [data.psd_freqs || []], y: [data.psd_power || []] });
        const f0 = data.cardiac_peak_freq;
        Plotly.relayout("fft-plot", {
            shapes: [
                { type: "rect", xref: "x", yref: "paper", x0: 0.75, x1: 2.5, y0: 0, y1: 1,
                  fillcolor: "rgba(15,106,74,0.06)", line: { width: 0 } },
                ...(f0 != null ? [{ type: "line", xref: "x", yref: "paper", x0: f0, x1: f0, y0: 0, y1: 1,
                  line: { color: data.optical_hr_ok ? "#0F6A4A" : "#B85430", width: 1.5, dash: "dot" } }] : [])
            ],
            annotations: f0 != null ? [{ x: f0, y: 1, xref: "x", yref: "paper", yanchor: "bottom", showarrow: false,
                text: `${(f0 * 60).toFixed(1)} BPM ${data.optical_hr_ok ? "(accepted)" : "(rejected)"}`,
                font: { size: 9, color: data.optical_hr_ok ? "#0F6A4A" : "#B85430" } }] : []
        });
        const rgb = data.rgb_norm || [[], [], []];
        if (rgb[0] && rgb[0].length) {
            const tx = relTimeAxis(rgb[0].length, fs);
            Plotly.update("rgb-plot", { x: [tx, tx, tx], y: rgb });
        }
        renderHistory();
        if (data.bvp_wave && data.bvp_wave.length) {
            Plotly.update("detrended-plot", { x: [relTimeAxis(data.bvp_wave.length, fs)], y: [data.bvp_wave] });
        }
        if (data.trend_wave && data.trend_wave.length) {
            const tx = relTimeAxis(data.trend_wave.length, fs);
            Plotly.update("wavelet-plot", { x: [tx, tx, tx], y: [data.trend_wave, data.pulsatile_wave, data.diff_wave] });
        }
    } catch (err) { }
}

// ================= 5. Chest microphone stream (INMP441 via host) =================
let isFetchingAudio = false;

function initAudioStream() {
    setInterval(async () => {
        if (isFetchingAudio) return;
        isFetchingAudio = true;
        try {
            const res = await fetch(API + "/api/audio");
            if (res.ok) renderAudio(await res.json());
        } catch (e) {
        } finally {
            isFetchingAudio = false;
        }
    }, 500);
}

function renderAudio(a) {
    const dot = document.getElementById("mic-status-dot");
    if (!a.connected) {
        setText("mic-status-text", "NO AUDIO STREAM FROM NODE");
        if (dot) dot.className = "mic-dot mic-dot-off";
        return;
    }
    if (dot) dot.className = "mic-dot mic-dot-on";
    setText("mic-status-text", `INMP441 | PCG ${fmt(a.hr, 1)} BPM | rho ${fmt(a.rho, 2)} | lost ${a.blocks_lost}`);
    try {
        if (a.wave && a.wave.length) {
            const n = a.wave.length;
            const x = Array.from({ length: n }, (_, i) => -a.wave_seconds + (i * a.wave_seconds) / (n - 1));
            Plotly.update("audio-plot", { x: [x], y: [a.wave] });
        }
        const analysisTab = document.getElementById("tab-analysis");
        if (a.spec && a.spec.length && analysisTab && analysisTab.classList.contains("active")) {
            const cols = a.spec[0].length;
            const tx = Array.from({ length: cols }, (_, i) => -a.spec_seconds + ((i + 0.5) * a.spec_seconds) / cols);
            Plotly.update("spectrogram-plot", { z: [a.spec], x: [tx], y: [a.spec_freqs] });
        }
    } catch (err) { }
}

// ================= 6. Device monitor (real link statistics) =================
function stateCell(ok, warnText) {
    if (ok === null) return '<td class="state-na">N/A</td>';
    return ok ? '<td class="state-stable">OK</td>' : `<td class="state-warn">${warnText || "CHECK"}</td>`;
}

function initDeviceMonitor() {
    const poll = async () => {
        let d = null;
        try {
            const res = await fetch(API + "/api/device");
            if (res.ok) d = await res.json();
        } catch (e) { }
        renderDevice(d);
    };
    poll();
    setInterval(poll, 1000);
}

// Icon-only camera switch: ESP32-S3 camera <-> host (Mac) webcam.
function renderCameraSwitch(choice) {
    const btn = document.getElementById("camera-switch");
    if (!btn || !choice) return;
    const webcam = choice === "webcam";
    btn.classList.toggle("webcam", webcam);
    const label = webcam ? "Using Mac webcam. Switch to ESP32-S3 camera" : "Using ESP32-S3 camera. Switch to Mac webcam";
    btn.setAttribute("aria-label", label);
    btn.title = label;
}

function initCameraSwitch() {
    const btn = document.getElementById("camera-switch");
    if (!btn) return;
    btn.addEventListener("click", async () => {
        btn.disabled = true;
        try {
            const res = await fetch(API + "/api/camera", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
            if (res.ok) {
                const d = await res.json();
                renderCameraSwitch(d.camera);
                writeLog(d.camera === "webcam" ? "Camera switched to the Mac webcam." : "Camera switched to the ESP32-S3 camera.");
            }
        } catch (e) { }
        btn.disabled = false;
    });
}

// Camera exposure is set from skin brightness by the host (backend/exposure.py).
function renderExposure(d) {
    const el = document.getElementById("exposure-meta");
    if (!el) return;
    if (d && d.camera_choice === "webcam") {
        const bad = (d.webcam_status || "").startsWith("unavailable");
        el.textContent = bad ? "CAMERA: MAC WEBCAM UNAVAILABLE (ALLOW CAMERA ACCESS FOR THE SERVER)"
                             : "CAMERA: MAC WEBCAM (ITS OWN AUTO EXPOSURE)";
        el.classList.toggle("warn", bad);
        return;
    }
    const c = d && d.connected ? d.exposure_ctl : null;
    if (!c || c.exposure == null) { el.textContent = "CAMERA EXPOSURE: --"; el.classList.remove("warn"); return; }
    const pct = (v) => v == null ? "--" : (100 * v).toFixed(0) + "%";
    const action = (c.action || "").toUpperCase();
    el.textContent = `CAMERA EXPOSURE: ${c.exposure} ROWS (SET FROM SKIN) | SKIN LEVEL ${c.level == null ? "--" : c.level}`
        + ` | CLIPPED ${pct(c.clip)} | DARK ${pct(c.dark)} | ${action === "OK" ? "IN RANGE" : (action === "WAITING" || !action) ? "WAITING FOR FACE" : action}`;
    el.classList.toggle("warn", action !== "OK" && action !== "" && action !== "WAITING");
}

let lastDeviceConnected = null;
function renderDevice(d) {
    const ind = document.getElementById("connection-indicator");
    const tabInd = document.getElementById("device-tab-status");
    let text, cls;
    if (!d) {
        text = "HOST ENGINE OFFLINE"; cls = "connection-status disconnected";
    } else if (d.connected) {
        text = `NODE ${d.transport || ""} | ${d.port}` + (d.camera_choice === "webcam" ? " | MAC WEBCAM" : "");
        cls = "connection-status connected";
    } else if (d.camera_choice === "webcam") {
        text = "MAC WEBCAM | NODE OFFLINE (NO MIC)"; cls = "connection-status disconnected";
    } else {
        text = "NO NODE CONNECTED"; cls = "connection-status disconnected";
    }
    if (ind) { ind.className = cls; setText("status-text", text); }
    renderExposure(d);
    if (d) renderCameraSwitch(d.camera_choice);
    if (tabInd) { tabInd.className = cls; setText("device-tab-status-text", text); }

    const connected = d ? !!d.connected : false;
    if (connected !== lastDeviceConnected) {
        writeLog(connected ? `Edge node connected on ${d.port} (${d.firmware || "firmware ?"}).` : "Edge node not connected.");
        lastDeviceConnected = connected;
    }

    const body = document.getElementById("device-table-body");
    if (!body || !d) return;
    const s = d.stat || {};
    const fps = d.host_fps;
    const rows = [
        ["Host link", d.connected ? `${d.port} (${d.transport || "?"})` : "not connected", "native USB-CDC for mic builds", stateCell(d.connected ? true : false, "OFFLINE")],
        ["Firmware", d.firmware || "--", "SonicVitals v2", stateCell(d.firmware ? d.firmware.endsWith("v2") : null, "OLD FW")],
        ["Camera (node report)", s.cam_ready === undefined ? "--" : (s.cam_ready ? `ready, ${fmt(s.fps, 1)} fps sent` : "not ready"), "OV2640 initialized", stateCell(s.cam_ready === undefined ? null : !!s.cam_ready)],
        ["Frame rate measured on host", fps == null ? "--" : `${fps.toFixed(2)} fps (jitter SD ${fmt(d.frame_interval_sd_ms, 1)} ms)`, ">= 5 fps (Nyquist for 150 BPM); target 10-15", stateCell(fps == null ? null : fps >= 5, "TOO LOW")],
        ["Mean JPEG size", s.jpeg_avg_bytes ? `${(s.jpeg_avg_bytes / 1024).toFixed(1)} kB` : "--", "bandwidth: 4/3 * fps * size", stateCell(null)],
        ["Frames decoded / rejected", `${d.frames_ok} / ${d.frames_bad}`, "rejected < 1 %", stateCell(d.frames_ok ? d.frames_bad / (d.frames_ok + d.frames_bad) < 0.01 : null, "LOSSY")],
        ["Microphone", d.mic_enabled === false ? "disabled in this build (UART)" : (s.mic_ready === undefined ? "--" : (s.mic_ready ? "INMP441 ready" : "I2S init failed")), "enabled + ready", stateCell(d.mic_enabled === false ? false : (s.mic_ready === undefined ? null : !!s.mic_ready), d.mic_enabled === false ? "DISABLED" : "ERROR")],
        ["OLED display (I2C 0x3C, GPIO47/48)", s.oled_ack === undefined ? "--" : (s.oled_ack ? "responding" : "no I2C acknowledge - check VCC, GND, SDA, SCL"), "responding", stateCell(s.oled_ack === undefined ? null : !!s.oled_ack, "NOT FOUND")],
        ["Audio blocks received / lost (host)", `${d.audio_blocks_received} / ${d.audio_blocks_lost}`, "lost < 1 %", stateCell(d.audio_blocks_received ? d.audio_blocks_lost / (d.audio_blocks_received + d.audio_blocks_lost) < 0.01 : null, "LOSSY")],
        ["Audio queue overflows (node)", s.audio_drops === undefined ? "--" : String(s.audio_drops), "0", stateCell(s.audio_drops === undefined ? null : s.audio_drops === 0, "OVERFLOW")],
        ["Video source in use", sourceLabel(d.video_source), "ESP32-S3 for evaluation", stateCell(d.video_source === "ESP32_S3_CAM" ? true : (d.video_source === "LOCAL_CAMERA" ? false : null), "FALLBACK")],
        ["Webcam fallback", d.webcam_fallback_enabled ? "enabled" : "disabled", "disabled for evaluation (SONICVITALS_WEBCAM=0)", stateCell(!d.webcam_fallback_enabled, "ENABLED")],
        ["Last data from node", d.age_s == null ? "--" : `${d.age_s} s ago`, "< 2 s", stateCell(d.age_s == null ? null : d.age_s < 2, "STALE")]
    ];
    body.innerHTML = rows.map(r => `<tr><td>${r[0]}</td><td>${r[1]}</td><td>${r[2]}</td>${r[3]}</tr>`).join("");
}

async function initConfigView() {
    const body = document.getElementById("config-table-body");
    if (!body) return;
    try {
        const res = await fetch(API + "/api/config");
        if (!res.ok) return;
        const cfg = await res.json();
        const rows = [];
        const walk = (obj, prefix) => Object.entries(obj).forEach(([k, v]) => {
            if (v && typeof v === "object" && !Array.isArray(v)) walk(v, prefix + k + ".");
            else rows.push([prefix + k, Array.isArray(v) ? v.join(" - ") : String(v)]);
        });
        walk(cfg, "");
        body.innerHTML = rows.map(r => `<tr><td>${r[0]}</td><td>${r[1]}</td></tr>`).join("");
    } catch (e) {
        setTimeout(initConfigView, 3000);
    }
}

function writeLog(message) {
    const consoleBody = document.getElementById("console-logs");
    if (!consoleBody) return;
    const div = document.createElement("div");
    div.innerText = "[INFO] " + new Date().toISOString().slice(11, 23) + " - " + message;
    consoleBody.appendChild(div);
    consoleBody.scrollTop = consoleBody.scrollHeight;
}

// ================= 7. Recording sessions (raw data is written by the host) =================
async function toggleSession() {
    const btn = document.getElementById("btn-session");
    const subId = (document.getElementById("sub-id") || {}).value || "SUB_01";
    const condition = (document.getElementById("config-condition") || {}).value || "DEV";
    const notes = (document.getElementById("config-notes") || {}).value || "";
    const durationSelect = document.getElementById("config-duration");
    sessionDurationSec = parseInt(durationSelect ? durationSelect.value : "60") || 60;

    if (sessionActive) {
        finalizeSession();
        return;
    }
    try {
        const res = await fetch(API + "/api/session/start", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ participant: subId, condition, notes })
        });
        const info = await res.json();
        sessionBackendId = info.session_id;
        writeLog(`Recording ${info.session_id} -> ${info.dir}`);
    } catch (e) {
        alert("Could not start recording: host engine not reachable.");
        return;
    }

    sessionActive = true;
    sessionStartTime = Date.now();
    sessionRecordedData = [];
    btn.innerText = "STOP RECORDING";
    btn.classList.add("btn-active");
    btn.style.backgroundColor = "var(--terracotta)";
    const progress = document.getElementById("session-progress-container");
    if (progress) progress.style.display = "block";
    const statusEl = document.getElementById("exp-status");
    if (statusEl) { statusEl.innerText = "● RECORDING"; statusEl.style.color = "var(--emerald-green)"; }

    if (sessionTimerInterval) clearInterval(sessionTimerInterval);
    sessionTimerInterval = setInterval(() => {
        const elapsed = Math.floor((Date.now() - sessionStartTime) / 1000);
        const pct = Math.min(100, Math.floor((elapsed / sessionDurationSec) * 100));
        setText("exp-timer", `${String(Math.floor(elapsed / 60)).padStart(2, "0")}:${String(elapsed % 60).padStart(2, "0")}`);
        const bar = document.getElementById("session-progress-bar");
        if (bar) bar.style.width = pct + "%";
        setText("session-progress-pct", pct + "%");
        if (elapsed >= sessionDurationSec) finalizeSession();
    }, 500);
}

async function finalizeSession() {
    if (sessionTimerInterval) { clearInterval(sessionTimerInterval); sessionTimerInterval = null; }
    sessionActive = false;
    try { await fetch(API + "/api/session/stop", { method: "POST" }); } catch (e) { }

    const btn = document.getElementById("btn-session");
    if (btn) { btn.innerText = "START RECORDING SESSION"; btn.classList.remove("btn-active"); btn.style.backgroundColor = ""; }
    const statusEl = document.getElementById("exp-status");
    if (statusEl) { statusEl.innerText = "SESSION SAVED"; statusEl.style.color = "var(--emerald-green)"; }

    const subId = (document.getElementById("sub-id") || {}).value || "SUB_01";
    const condition = (document.getElementById("config-condition") || {}).value || "DEV";
    const mean = arr => { const v = arr.filter(x => x != null); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; };
    const sess = {
        id: sessionBackendId || "LOCAL_" + Date.now(),
        subject: subId, condition, duration: sessionDurationSec,
        sampleCount: sessionRecordedData.length,
        meanHr: mean(sessionRecordedData.map(d => d.hr)),
        meanRr: mean(sessionRecordedData.map(d => d.rr)),
        meanQuality: mean(sessionRecordedData.map(d => d.quality)),
        timestamp: new Date().toISOString(),
        samples: sessionRecordedData
    };
    savedSessions.unshift(sess);
    writeLog(`Session ${sess.id} saved (${sess.sampleCount} display updates). Raw data is in data/sessions/${sess.id}/.`);
}

function downloadJSON(obj, name) {
    const a = document.createElement("a");
    a.href = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(obj, null, 2));
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
}


function exportCSV() {
    if (!signalLogs.length) {
        alert("No display updates recorded yet.");
        return;
    }
    const header = "time_iso,hr_display_bpm,rr_display_brpm,rmssd_ms,hr_source,hr_optical_bpm,hr_acoustic_bpm,quality_pct,video_source";
    const csv = [header].concat(signalLogs.map(r => r.join(","))).join("\n");
    const a = document.createElement("a");
    a.href = "data:text/csv;charset=utf-8," + encodeURIComponent(csv);
    a.download = "SonicVitals_display_log_" + Math.floor(Date.now() / 1000) + ".csv";
    document.body.appendChild(a);
    a.click();
    a.remove();
    writeLog("Display log exported (for raw data use the host session recorder).");
}

// ================= 8. Colorimetric snapshot studio =================
let currentDiagnosticData = null;
let currentDiagView = "annotated_roi";
const RANGE_LABEL = { NORMAL: "IN RANGE", WARN: "BORDERLINE", ALERT: "OUT OF RANGE" };

const VIEW_METADATA = {
    annotated_roi: { tag: "REGIONS OF INTEREST", left: "FIVE REGIONS", right: "RELATIVE TO FACE BOX", cls: "hidden" },
    erythema_map: { tag: "R - G MAP", left: "LOW R-G", right: "HIGH R-G", cls: "" },
    jaundice_map: { tag: "CIELAB b* MAP", left: "LOW b*", right: "HIGH b* (YELLOWER)", cls: "inferno" },
    cyanosis_map: { tag: "B / R MAP", left: "LOW B/R", right: "HIGH B/R", cls: "cool" },
    raw: { tag: "RAW FRAME", left: "CAMERA FRAME", right: "AS CAPTURED", cls: "hidden" }
};
// Map colours are min-max normalized within each face, so they show relative
// differences inside one image only, not absolute or comparable values.

let isAutoCaptureEnabled = false;
let autoCaptureTriggeredForSubject = false;

function toggleAutoCapture(chk) {
    isAutoCaptureEnabled = chk ? chk.checked : false;
    writeLog(`Auto-capture on full face ${isAutoCaptureEnabled ? "enabled" : "disabled"}.`);
}

function showFaceAlert(msg, guidance) {
    const banner = document.getElementById("full-face-alert-banner");
    if (banner) {
        setText("full-face-alert-text", `${msg} ${guidance ? "(" + guidance + ")" : ""}`);
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
            const res = await fetch(API + "/api/best_moment_status");
            if (!res.ok) return;
            const data = await res.json();

            const fullFaceBadge = document.getElementById("badge-full-face");
            if (fullFaceBadge) {
                if (data.full_face_visible) {
                    fullFaceBadge.className = "badge-face ready";
                    fullFaceBadge.innerText = "● FULL FACE (GATE PASSED)";
                } else if (data.patient_detected) {
                    fullFaceBadge.className = "badge-face partial";
                    fullFaceBadge.innerText = "⚠ " + (data.face_guidance ? data.face_guidance.split(".")[0] : "ALIGN FACE").toUpperCase();
                } else {
                    fullFaceBadge.className = "badge-face searching";
                    fullFaceBadge.innerText = "SEARCHING SUBJECT...";
                }
            }

            const guidanceRow = document.getElementById("moment-guidance-row");
            if (guidanceRow) {
                if (!data.full_face_visible && data.patient_detected && data.face_guidance) {
                    setText("moment-guidance-txt", data.face_guidance);
                    guidanceRow.style.display = "flex";
                } else {
                    guidanceRow.style.display = "none";
                }
            }

            const badge = document.getElementById("moment-badge");
            const wsDot = document.getElementById("ws-status-dot");
            if (data.has_moment && data.full_face_visible) {
                if (badge) badge.className = "badge-moment";
                setText("moment-status-txt", "SNAPSHOT READY");
                setText("moment-clarity", "σ²=" + data.sharpness);
                if (wsDot) wsDot.className = "ws-status-dot ready";
                setText("ws-status-text", "READY | FULL FACE (SHARPEST FRAME IN 8 s)");
                if (isAutoCaptureEnabled && !autoCaptureTriggeredForSubject) {
                    autoCaptureTriggeredForSubject = true;
                    captureDiagnosticSnapshot();
                }
            } else {
                if (badge) badge.className = "badge-moment buffering";
                setText("moment-status-txt", data.patient_detected ? "ALIGNING FACE" : "WAITING");
                setText("moment-clarity", data.sharpness > 0 ? "σ²=" + data.sharpness : "σ²=--");
                if (wsDot) wsDot.className = data.patient_detected ? "ws-status-dot warning" : "ws-status-dot";
                setText("ws-status-text", data.patient_detected ? `ALIGNMENT REQUIRED | ${data.face_guidance || ""}` : "WAITING FOR SUBJECT");
            }
            if (!data.patient_detected) autoCaptureTriggeredForSubject = false;
        } catch (e) {
        } finally {
            isFetchingMoment = false;
        }
    }, 1000);
}

async function captureDiagnosticSnapshot() {
    const buttons = [document.getElementById("btn-capture-diag"), document.getElementById("btn-tab-capture")];
    buttons.forEach(b => { if (b) { b.dataset.html = b.dataset.html || b.innerHTML; b.innerHTML = '<span class="moment-pulse"></span> PROCESSING...'; b.style.opacity = "0.7"; } });
    try {
        const res = await fetch(API + "/api/capture_diagnostic");
        const data = await res.json();
        if (!data.success) {
            showFaceAlert(data.error || "Full face must be visible to capture a snapshot.", data.guidance);
            writeLog("Snapshot inhibited: " + (data.error || "full face not visible"));
            return;
        }
        dismissFaceAlert();
        currentDiagnosticData = data;
        renderDiagnosticResults(data);
        const activeNav = document.querySelector(".nav-btn.active");
        if (!activeNav || activeNav.getAttribute("data-tab") !== "diagnostics") {
            const diagNavBtn = document.getElementById("nav-diag-btn");
            if (diagNavBtn) diagNavBtn.click();
        }
        writeLog(`Snapshot ${data.frame_id} captured (clarity ${data.sharpness}, source ${sourceLabel(data.video_source)}).`);
    } catch (err) {
        showFaceAlert("Unable to reach the host engine. Check that the backend is running.");
    } finally {
        buttons.forEach(b => { if (b && b.dataset.html) { b.innerHTML = b.dataset.html; b.style.opacity = "1"; } });
    }
}

function renderDiagnosticResults(data) {
    const tsStr = new Date(data.timestamp * 1000).toTimeString().split(" ")[0];
    const meta = data.meta_strip || {};
    setText("ws-meta-frame", meta.frame_id || data.frame_id || "FRAME #-----");
    setText("ws-meta-roi", meta.roi_status || "--");
    setText("ws-meta-motion", meta.motion || "--");
    setText("ws-meta-quality", meta.quality || "--");
    setText("ws-meta-phase", meta.cardiac || "--");
    setText("ws-workflow-timestamp", `TS: ${tsStr} | ${sourceLabel(data.video_source)}`);
    setText("modal-meta-ts", `TS: ${tsStr}`);

    const st = data.structured_triage || {};
    const overallBadge = document.getElementById("triage-overall-badge");
    if (overallBadge) {
        overallBadge.innerText = st.flags_count ? `${st.flags_count} OF 5 OUT OF RANGE` : "ALL IN RANGE";
        overallBadge.className = `triage-overall-badge ${st.overall_status || "NORMAL"}`;
    }
    const interpBox = document.getElementById("tab-diag-interp-box");
    if (interpBox) interpBox.className = `triage-interpretation-box ${st.overall_status || "NORMAL"}`;
    setText("tab-diag-interp-text", data.clinical_summary || "");

    (st.observations || []).forEach(obs => {
        setText(`obs-val-${obs.id}`, obs.metric);
        const statEl = document.getElementById(`obs-status-${obs.id}`);
        if (statEl) { statEl.innerText = RANGE_LABEL[obs.status] || obs.status; statEl.className = `obs-status-badge ${obs.status}`; }
        setText(`obs-detail-${obs.id}`, obs.detail);
    });

    const rows = (data.biomarkers || []).map(b => `
        <tr>
            <td><strong>${b.name}</strong></td>
            <td><span class="val-metric">${b.value}</span><span class="val-unit">${b.unit}</span></td>
            <td><span class="ref-range">${b.reference}</span></td>
            <td><span class="status-badge ${b.status}">${RANGE_LABEL[b.status] || b.status}</span></td>
            <td><span class="finding-text">${b.finding}</span></td>
        </tr>`).join("");
    ["tab-diag-biomarkers-body", "diag-biomarkers-body"].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.innerHTML = rows;
    });

    const mo = data.metrics_overview || {};
    if (mo.clarity !== undefined) {
        setText("ov-val-clarity", mo.clarity.toFixed(1));
        const b = document.getElementById("ov-badge-clarity");
        if (b) { b.innerText = mo.clarity > 100 ? "ADEQUATE FOCUS" : "BLUR / MOTION"; b.className = mo.clarity > 100 ? "module-badge" : "module-badge warn"; }
    }
    if (mo.symmetry !== undefined) {
        setText("ov-val-symmetry", `${mo.symmetry}`);
        const b = document.getElementById("ov-badge-symmetry");
        if (b) { b.innerText = mo.symmetry < 5 ? "IN RANGE" : "OUT OF RANGE"; b.className = mo.symmetry < 5 ? "module-badge" : "module-badge warn"; }
    }
    if (mo.perfusion !== undefined) {
        setText("ov-val-perfusion", `${mo.perfusion}`);
        const b = document.getElementById("ov-badge-perfusion");
        const s = mo.perfusion_status || "NORMAL";
        if (b) { b.innerText = RANGE_LABEL[s]; b.className = s === "NORMAL" ? "module-badge" : "module-badge warn"; }
    }
    const fCount = mo.flags_count !== undefined ? mo.flags_count : (st.flags_count || 0);
    setText("ov-val-flags", `${fCount}`);
    const fb = document.getElementById("ov-badge-flags");
    if (fb) { fb.innerText = fCount === 0 ? "ALL IN RANGE" : "SEE TABLE"; fb.className = fCount === 0 ? "module-badge" : "module-badge warn"; }

    switchDiagView(currentDiagView || "annotated_roi");
}

function switchDiagView(viewKey) {
    if (!currentDiagnosticData) {
        captureDiagnosticSnapshot().then(() => { if (currentDiagnosticData) switchDiagView(viewKey); });
        return;
    }
    currentDiagView = viewKey;
    const meta = VIEW_METADATA[viewKey] || VIEW_METADATA.annotated_roi;
    document.querySelectorAll(".ws-view-btn, .btn-diag-tab").forEach(btn => {
        btn.classList.toggle("active", btn.getAttribute("data-view") === viewKey);
    });
    const imgSrc = (currentDiagnosticData.images || {})[viewKey] || "";
    const img = document.getElementById("tab-diag-main-img");
    const placeholder = document.getElementById("tab-diag-placeholder");
    const tag = document.getElementById("tab-diag-view-tag");
    if (img && imgSrc) { img.src = imgSrc; img.style.display = "block"; }
    if (placeholder && imgSrc) placeholder.style.display = "none";
    if (tag && imgSrc) { tag.innerText = meta.tag; tag.style.display = "block"; }

    const bar = document.getElementById("colormap-bar");
    if (bar) bar.className = "colormap-gradient " + meta.cls;
    setText("colormap-label-left", meta.left);
    setText("colormap-label-right", meta.right);
}

function closeDiagnosticModal() {
    const modal = document.getElementById("diagnostic-modal");
    if (modal) modal.classList.remove("active");
}

function exportDiagnosticJSON() {
    if (!currentDiagnosticData) {
        alert("No snapshot captured yet.");
        return;
    }
    downloadJSON({
        platform: "SonicVitals colorimetric snapshot (exploratory, not clinically validated)",
        export_timestamp: new Date().toISOString(),
        record: currentDiagnosticData
    }, `SonicVitals_snapshot_${Math.floor(Date.now() / 1000)}.json`);
    writeLog("Snapshot JSON exported.");
}
