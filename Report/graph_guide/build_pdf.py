"""Builds Report/graph_guide/SonicVitals_Graphs_and_Methods.pdf (run make_figures.py first)."""
import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, 'figs')
OUT = os.path.join(HERE, 'SonicVitals_Graphs_and_Methods.pdf')

GREEN = colors.HexColor('#0F6A4A')
AMBER = colors.HexColor('#D98C00')
LIGHT = colors.HexColor('#EEF4F0')
GRID = colors.HexColor('#C9D3CC')

ss = getSampleStyleSheet()
H1 = ParagraphStyle('H1', parent=ss['Heading1'], fontSize=15, textColor=GREEN, spaceBefore=6, spaceAfter=6)
H2 = ParagraphStyle('H2', parent=ss['Heading2'], fontSize=11.5, textColor=GREEN, spaceBefore=8, spaceAfter=3)
H3 = ParagraphStyle('H3', parent=ss['Heading3'], fontSize=9.8, spaceBefore=6, spaceAfter=2)
BODY = ParagraphStyle('B', parent=ss['BodyText'], fontSize=8.8, leading=11.6, spaceAfter=3)
SMALL = ParagraphStyle('S', parent=BODY, fontSize=7.8, leading=10)
CELL = ParagraphStyle('C', parent=BODY, fontSize=7.6, leading=9.6, spaceAfter=0)
CELLB = ParagraphStyle('CB', parent=CELL, fontName='Helvetica-Bold')
CAP = ParagraphStyle('Cap', parent=SMALL, textColor=colors.HexColor('#555555'), alignment=TA_CENTER, spaceAfter=6)
TITLE = ParagraphStyle('T', parent=ss['Title'], fontSize=20, textColor=GREEN, leading=24)


def P(t, s=BODY):
    return Paragraph(t, s)


def fig(name, width_mm=170, caption=None):
    path = os.path.join(FIG, name)
    if not os.path.isfile(path):
        return []
    from reportlab.lib.utils import ImageReader
    w, h = ImageReader(path).getSize()
    W = width_mm * mm
    out = [Image(path, width=W, height=W * h / w)]
    if caption:
        out.append(P(caption, CAP))
    return out


def table(rows, widths, header=True):
    data = [[P(c, CELLB if (header and i == 0) else CELL) if isinstance(c, str) else c for c in r]
            for i, r in enumerate(rows)]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1 if header else 0)
    st = [('GRID', (0, 0), (-1, -1), 0.4, GRID), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
          ('LEFTPADDING', (0, 0), (-1, -1), 3), ('RIGHTPADDING', (0, 0), (-1, -1), 3),
          ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]
    if header:
        st.append(('BACKGROUND', (0, 0), (-1, 0), LIGHT))
    t.setStyle(TableStyle(st))
    return t


def graph(title, shows, computed, read, figure=None, caption=None, width=165):
    """One graph block: what it shows / how it is computed / how to read it."""
    rows = [['What it shows', shows], ['How it is computed', computed], ['How to read it', read]]
    t = Table([[P(a, CELLB), P(b, CELL)] for a, b in rows], colWidths=[30 * mm, 140 * mm])
    t.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 0.4, GRID), ('BACKGROUND', (0, 0), (0, -1), LIGHT),
                           ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('TOPPADDING', (0, 0), (-1, -1), 2),
                           ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]))
    block = [P(title, H3), t, Spacer(1, 3)]
    if figure:
        block += fig(figure, width, caption)
    return [KeepTogether(block)]


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont('Helvetica', 7)
    canvas.setFillColor(colors.HexColor('#777777'))
    canvas.drawString(20 * mm, 10 * mm, 'SonicVitals: dashboard graphs, computation and methods compared')
    canvas.drawRightString(190 * mm, 10 * mm, f'Page {doc.page}')
    canvas.restoreState()


def build():
    s = []
    # ------------------------------------------------------------------ title
    s += [Spacer(1, 30 * mm), P('SonicVitals', TITLE),
          P('Dashboard graphs: what they show, how they are calculated, and which methods and modes are compared',
            ParagraphStyle('st', parent=BODY, fontSize=12, leading=15, alignment=TA_CENTER)),
          Spacer(1, 8 * mm),
          P('Contactless heart rate and breathing from a camera (Mac webcam or ESP32-S3 + GC2145) with an INMP441 '
            'microphone channel. This guide follows the code in <i>backend/</i> and <i>Frontend/</i> as of 17 October 2026.',
            ParagraphStyle('c', parent=BODY, alignment=TA_CENTER)),
          Spacer(1, 10 * mm)]
    s += fig('pipeline.png', 175, 'Figure 1. Processing chain. Green: image stage; amber: signal stage; blue: deep '
             'models (comparison only); red: microphone; grey: fusion and display.')
    s += [Spacer(1, 4 * mm),
          P('<b>About the example figures.</b> The plots in this document are the dashboard\'s own telemetry, '
            'produced by replaying a 45 s webcam recording (16 Oct 2026) through the live engine. That recording '
            'has no reference pulse and most of its windows were <i>rejected</i> by the quality gate, so the figures '
            'show what the graphs look like and how a rejection appears, not a validated measurement.', SMALL),
          PageBreak()]

    # ------------------------------------------------------------------ contents
    s += [P('Contents', H1)]
    for line in ['1. The processing chain, step by step', '2. Dashboard tab graphs and cards',
                 '3. Signal Analysis dashboard: readouts and graphs', '4. Sessions tab (optical vs acoustic agreement)',
                 '5. Diagnostics Studio (colour indices)', '6. Modes and methods compared',
                 '7. Benchmark: evaluation modes and results (UBFC-rPPG)', '8. Formulas', '9. Limits to keep in mind']:
        s.append(P(line))
    s.append(Spacer(1, 6))

    # ------------------------------------------------------------------ 1. chain
    s += [P('1. The processing chain, step by step', H1),
          P('Every graph is a view of one stage of this chain. The camera path runs on every frame; the heart-rate '
            'estimate is recomputed every 2 s on the last 30 s of gated frames.')]
    s.append(table([
        ['#', 'Stage', 'What happens', 'Key settings'],
        ['1', 'Capture', 'Mac webcam frames (about 30 fps) or the ESP32-S3 node. The node computes skin-box '
         'colour sums on-board at 10 fps and streams JPEG video at 5 fps over Wi-Fi.',
         'Node exposure is metered on the skin (target level 165).'],
        ['2', 'Face detection and gate', 'Haar cascade on a copy at most 320 px wide; box smoothed. The full-face '
         'gate needs a frontal face of at least 20 % of frame width, fully inside the frame. Only gated frames '
         'enter the analysis buffer.', 'Box jitter under 6 % of the face size is ignored.'],
        ['3', 'Skin boxes', 'Four boxes relative to the face: forehead, left cheek, right cheek, nose. The boxes are '
         'locked and follow the face with sub-pixel phase correlation against a template taken at lock time, so '
         'the same skin stays in each box when the head drifts.', 'Re-lock when tracking fails for 8 frames or the '
         'face moves more than 25 % of its width.'],
        ['4', 'Skin mask and means', 'A YCrCb skin mask per box (computed once per lock) removes hair, brows and '
         'beard; the mean R, G, B of the remaining pixels gives one sample per box per frame.', 'Cr 133-180, '
         'Cb 77-135.'],
        ['5', 'Background reference', 'Mean colour of non-skin strips beside and above the face: it sees the room '
         'lighting but has no pulse.', 'Used only when it carries a real lighting change (>= 30 % of skin band RMS).'],
        ['6', 'Resampling and repair', 'Interpolate to a uniform 15 Hz grid; bridge gaps up to 2 s. Frame-to-frame '
         'jumps larger than 4 robust SDs (motion, re-lock) are zeroed in the log-derivative and re-integrated. '
         'After a movement only the still stretch since then is analysed (if at least 12 s).',
         'Segment >= 10 s for HR, >= 15 s for RR; coverage >= 80 %.'],
        ['7', 'Illumination rectification', 'Per colour channel, the skin trace is regressed on the background in '
         '0.6-3 Hz and the shared part (flicker, auto-exposure) is subtracted.', 'beta 0-1.5.'],
        ['8', 'Pulse extraction', 'Three classic projections of RGB to a pulse: CHROM (primary), POS and GREEN.',
         'CHROM windows of 3 s; POS windows of 1.6 s.'],
        ['9', 'Spectrum and peak', 'Welch power spectrum of the drift-removed pulse; the strongest peak in '
         '0.75-2.5 Hz (45-150 BPM), staying near the last accepted HR when that peak is at least half as strong. '
         'Peaks equally strong on the background are skipped as lighting.', 'NFFT 4096; 0.6 Hz high-pass.'],
        ['10', 'Quality gate', 'Accept only if de Haan SNR >= -2 dB, POS and GREEN both find the CHROM peak '
         'within 6 BPM, coverage >= 80 % and at most 15 % of frames repaired.', 'Thresholds set on synthetic data '
         'and own recordings, never on the test datasets.'],
        ['11', 'Ensemble + tracker', 'Spectra of 4 boxes x 3 extractors are normalised and median-fused; a Bayes '
         'filter on a 0.5 BPM grid tracks HR over time and reports a confidence (posterior mass within +-3 BPM).',
         'High confidence >= 0.8.'],
        ['12', 'Microphone', 'INMP441 at the node rate (16 kHz, or 4 kHz in older recordings): 25-400 Hz band-pass, Shannon-energy envelope, autocorrelation '
         'period gives PCG HR; S1 peak times give RMSSD.', 'Envelope peak rho >= 0.4, beat consistency >= 0.6.'],
        ['13', 'Fusion and display', 'Quality-weighted fusion of camera and mic when within 8 BPM, else the '
         'higher-quality one. The card value is steadied by the display stabilizer (section 6.1): it holds '
         'its value, flags jumps it cannot confirm, and cross-checks against the other methods.',
         'Jump > 8 BPM held; hold 15 s.'],
    ], [7, 27, 92, 44]))

    # ------------------------------------------------------------------ 2. dashboard
    s += [PageBreak(), P('2. Dashboard tab graphs and cards', H1)]
    s += graph('2.1 Primary vision stream (video with skin boxes)',
               'Live camera image with the face box and the four skin boxes (green when the full-face gate passes). '
               'A badge says FULL FACE (GATE PASSED), an alignment hint, or SEARCHING.',
               'Stages 2-3 above. The boxes are drawn at their motion-compensated position, so they should stay on '
               'the same patch of forehead, cheeks and nose while you move slightly.',
               'If the boxes slide onto hair, eyebrows or background, the signal will be poor. A camera-switch icon '
               'toggles Mac webcam / ESP32 camera.', 'roi.jpg', 'Figure 2. Skin boxes on a webcam frame.', width=95)
    s.append(P('2.2 Readout cards', H3))
    s.append(P('Each card shows one large value and one status badge (green = verified, amber = estimate, '
               'red = flag, grey = no value). The reason behind a badge is in the card\'s tooltip (hover), '
               'not in small text. A badge stays at least 4 s before it changes, except a red flag, which is '
               'raised at once.'))
    s.append(table([
        ['Card', 'Value', 'Badges and when they appear'],
        ['HEART RATE', 'Steadied average of the agreeing methods in the comparison table (section 6.1)',
         'N OF M METHODS AGREE | LOW CONFIDENCE | RAPID CHANGE - HELD | UNSTABLE READING | METHODS DISAGREE | '
         'CHANGE CONFIRMED | HOLDING LAST VALUE | ACQUIRING | NO SIGNAL'],
        ['BREATHING RATE', 'Steadied breaths/min from the green trace (0.15-0.40 Hz peak on >= 15 s)',
         'Same badges as heart rate; a jump of more than 4 br/min is held and flagged. STABLE when >= 50 % of '
         '0.05-1 Hz power lies at the peak, else LOW CONFIDENCE.'],
        ['HRV (RMSSD)', 'ms', 'FROM HEART SOUNDS (>= 20 clean PCG intervals) | EXPLORATORY (camera pulse peaks, '
         'only while the heart-rate card is STABLE) | NEEDS MIC ON CHEST | MIC OFFLINE'],
        ['SIGNAL QUALITY', '% (spectral concentration of the pulse)', 'GOOD (estimate accepted) | FAIR (SNR '
         'within 3 dB of the gate) | POOR (further below: red) | MEASURING | NO SIGNAL'],
        ['HR SOURCE', 'How many methods the heart rate averages (e.g. 5 METHODS)', 'ALL INCLUDED | N LEFT OUT '
         '(outliers; tooltip names them) | SINGLE METHOD (fewer than 3 available) | NONE'],
        ['SpO2', '--', 'NOT CALIBRATED: only the ratio R = (AC/DC red)/(AC/DC blue) is computed; a number needs '
         'calibration against a finger oximeter.'],
    ], [30, 45, 95]))
    s += graph('2.3 Microphone waveform (PCG)',
               'The last 4 s of the INMP441 signal from the ESP32 node.',
               'Node audio (16 kHz; 4 kHz in older recordings), 25-400 Hz Butterworth band-pass (heart-sound band), decimated to 1 kHz, min/max '
               'decimated to 600 points and normalised to +-1.',
               'With the mic on the chest, S1/S2 heart sounds appear as regular bursts. Off the chest it is noise, '
               'and the mic HR is withheld by the beat-consistency check.',
               'pcg_wave.png', 'Figure 2b. Node microphone, 4 s (14 Oct recording): noise, no heart sounds.')
    s += graph('2.4 Recovered pulse (CHROM, 0.75-2.5 Hz) and respiratory waveform',
               'Top: the blood-volume pulse recovered from skin colour. Bottom: the slow breathing oscillation.',
               'Pulse: CHROM projection of the 15 Hz skin RGB, band-passed 0.75-2.5 Hz (3rd-order Butterworth, '
               'zero phase), z-scored. Respiration: green channel band-passed 0.15-0.40 Hz, z-scored.',
               'A good pulse looks like a regular wave at your heart rate (about 1 cycle per second at 60 BPM). '
               'Irregular amplitude or several frequencies mixed means noise or motion dominate.',
               'pulse_resp.png', 'Figure 3. Pulse and respiration traces (replayed clip).')
    s += graph('2.5 Heart-rate history (last 5 min)',
               'Every second: the value shown on the heart-rate card (solid line), red triangles where the card '
               'raised a flag (rapid change, unstable, methods disagree), each camera estimate as an accepted '
               '(filled) or rejected (hollow) point, microphone HR (diamonds) and the tracked HR (dotted: green = '
               'high confidence, amber = low).',
               'Points come from the 2 s estimates (stage 9-10); the tracked line from stage 11. Hovering a '
               'rejected point shows why it was rejected.',
               'Accepted points and the green tracked line should sit on one level when you are still. Hollow points '
               'scattered widely mean the camera signal is not usable at that moment.',
               'hr_history.png', 'Figure 4. History on the replayed clip: windows rejected (hollow); tracker below high confidence (amber).')
    s += graph('2.6 Signal quality vs acceptance gate',
               'Pulse SNR over time (black), the gate threshold (dashed, -2 dB) and, on the right axis, how many of '
               'POS and GREEN agree with the CHROM peak (0, 1 or 2).',
               'SNR (de Haan & Jeanne 2013): power within +-0.1 Hz of the HR peak and +-0.2 Hz of its harmonic, '
               'divided by the rest of 0.5-4 Hz, in dB.',
               'An estimate is accepted only when the black line is above the dashed one <i>and</i> the amber '
               'step is at 2. On the replayed clip SNR stays below the gate, so nothing is accepted.',
               'quality.png', 'Figure 5. Quality against the gate (replayed clip).')
    s += graph('2.7 Method comparison (live, same face, same moment)',
               'A table and a dot chart with the heart rate from every method at the same moment, the median '
               '(dotted line) and the spread; AGREE when the spread is <= 6 BPM.',
               'SonicVitals, CHROM, POS, GREEN from the skin boxes every 2 s; TS-CAN, PhysNet, EfficientPhys on '
               'the last 30 s of 72 x 72 face crops every 12 s (needs >= 12 fps, so Mac webcam only); microphone '
               'from the node. Section 6 describes each method.',
               'Methods that share the same input but different algorithms should agree when the signal is good. '
               'A wide spread is itself a sign of a poor signal.')

    # ------------------------------------------------------------------ 3. analysis
    import json
    strip = json.load(open(os.path.join(FIG, 'strip.json')))
    s += [PageBreak(), P('3. Signal Analysis dashboard (laboratory graph view)', H1),
          P('The Signal Analysis tab is the engineering view of the camera pulse: one strip of six live readouts, '
            'six graphs in a 3 x 2 grid, and a CSV export button. Everything on it is refreshed from '
            '<i>/api/vitals</i> about every 0.5 s while the tab is open; the numbers come from the most recent 2 s '
            'estimate on the last 30 s of gated frames (stages 6-10 of the chain).'),
          P('3.1 Layout', H2)]
    s.append(table([
        ['Position', 'Element', 'Section'],
        ['Header', 'Title "SIGNAL ANALYSIS PIPELINE" and the EXPORT RECORDING (CSV) button', '3.9'],
        ['Top strip', 'Six readouts: cardiac peak, SNR, spectral concentration, respiration, methods agreeing | '
         'motion, video source and fps', '3.2'],
        ['Row 1', 'Left: rPPG power spectral density. Right: chest microphone spectrogram', '3.3, 3.4'],
        ['Row 2', 'Left: standardized pulse signal. Right: moving-average decomposition', '3.5, 3.6'],
        ['Row 3', 'Left: skin colour change (R, G, B). Right: method agreement CHROM vs POS vs green', '3.7, 3.8'],
    ], [22, 120, 28]))
    s += fig('analysis_overview.png', 170, 'Figure 6. The six Signal Analysis graphs in the tab\'s grid order '
             '(camera graphs: replayed webcam clip, 16 Oct; spectrogram: node microphone recording, 14 Oct).')

    s += [P('3.2 Telemetry strip (the six readouts)', H2),
          P('Values in the third column are what the strip showed at the end of the replayed clip. Its estimate '
            'was <b>' + ('accepted' if strip.get('accepted') else 'rejected') + '</b> by the gate.', SMALL)]
    s.append(table([
        ['Readout', 'How it is computed', 'Example', 'How to read it'],
        ['CARDIAC PEAK (f0)', 'Frequency of the chosen peak of the CHROM spectrum in 0.75-2.5 Hz (with peak '
         'tracking and lighting peaks skipped); BPM = 60 x f0. Shows "NEEDS 10 s SEGMENT" until 10 s of gated '
         'frames exist.', strip['CARDIAC PEAK (f0)'], 'The candidate heart rate before the gate; it is the dotted '
         'line in the spectrum.'],
        ['SNR (DE HAAN)', '10 log10 of power at f0 (+-0.1 Hz) and 2 f0 (+-0.2 Hz) over the rest of 0.5-4 Hz.',
         strip['SNR (DE HAAN)'], 'Accepted only at >= -2 dB. Around -5 dB the peak is barely above noise.'],
        ['SPECTRAL CONCENTRATION (Q)', 'Share of the 0.75-2.5 Hz power within +-0.1 Hz of f0, in %.',
         strip['SPECTRAL CONCENTRATION (Q)'], 'Higher = one dominant peak; a flat spectrum gives a few %. It is '
         'also the camera weight in fusion.'],
        ['RESPIRATION (fr)', 'Peak of the green-channel spectrum in 0.15-0.40 Hz on >= 15 s; shown only if >= 50 % '
         'of 0.05-1 Hz power lies at that peak.', strip['RESPIRATION (fr)'] +
         (f" (best guess {strip['rr_estimate']:.1f} BrPM, below the 50 % rule)" if strip.get('rr_estimate') else ''),
         'Breathing frequency in Hz and breaths/min.'],
        ['METHODS AGREEING | MOTION', 'How many of POS and GREEN find the CHROM peak within 6 BPM (0-2); share of '
         'frame pairs repaired by the artifact filter; seconds skipped before the latest still stretch.',
         strip['METHODS AGREEING | MOTION'], 'Needs 2/2 and <= 15 % repaired to be accepted.'],
        ['VIDEO SOURCE (MEASURED FPS)', 'HOST WEBCAM or ESP32-S3 CAMERA, and the frame rate actually processed.',
         'Mac webcam about 30 fps', 'Below about 10 fps the pulse is poorly sampled; deep models need >= 12 fps.'],
    ], [33, 62, 30, 45]))

    s += graph('3.3 rPPG power spectral density (Welch)  [row 1, left]',
               'Power of the pulse signal against frequency, with the cardiac band shaded (0.75-2.5 Hz) and the '
               'chosen peak marked (green = accepted, red = rejected) with its BPM.',
               'Welch periodogram (256-sample segments, NFFT 4096) of the 0.6 Hz high-passed CHROM pulse at 15 Hz, '
               'in dB relative to the maximum, shown 0.5-3.5 Hz.',
               'A clean recording has one sharp peak (and a smaller one at twice the frequency). Many peaks of '
               'similar height, as here, mean the window holds no dominant rhythm and the gate rejects it.',
               'psd.png', 'Figure 7. Spectrum of the replayed clip: several peaks of similar height.')
    s += graph('3.4 Chest microphone spectrogram (STFT, dB)  [row 1, right]',
               'Time-frequency picture of the last 4 s of node audio.',
               'Short-time Fourier transform with a Hamming window of about 32 ms (512 samples at 16 kHz, 128 at '
               '4 kHz), 75 % overlap, up to 2 kHz (or the Nyquist frequency), averaged into 60 time columns, dB '
               'relative to the maximum, colour range -60 to 0 dB.',
               'Heart sounds appear as short vertical stripes below about 200 Hz repeating at the heart rate. '
               'Broadband speckle across all frequencies, as in this recording, is background noise: no heart '
               'sounds are visible, which is what happens when the mic is not pressed on the chest.',
               'spectrogram.png', 'Figure 8. Node microphone, 4 s from the 14 Oct recording (4 kHz).')
    s += graph('3.5 Standardized pulse signal  [row 2, left]',
               'The recovered blood-volume pulse, larger than on the dashboard, for inspecting its shape.',
               'CHROM pulse band-passed 0.75-2.5 Hz (3rd-order Butterworth, zero phase) and z-scored (mean 0, SD 1); '
               'last part of the analysis buffer at 15 Hz.',
               'Look for a regular wave with one cycle per heartbeat and steady amplitude. Bursts of large '
               'amplitude (here around -6 s) are usually motion or lighting, not the heart.',
               'detrended.png', 'Figure 9. Standardized pulse (replayed clip).')
    s += graph('3.6 Moving-average decomposition  [row 2, right]',
               'Splits the pulse into a slow trend, the pulsatile part (signal minus trend) and the first '
               'difference.',
               'Trend = moving average over W = min(14, N/4) samples (about 1 s at 15 Hz); pulsatile = signal - '
               'trend; first difference = x[n] - x[n-1]. The pulsatile/trend energy ratio is reported as motion_ratio.',
               'A large trend means slow drift (lighting, posture); spikes in the first difference mark sudden '
               'changes such as motion.', 'decomp.png', 'Figure 10. Decomposition (replayed clip).')
    s += graph('3.7 Skin colour change (gated skin boxes, motion-suppressed)  [row 3, left]',
               'The raw input of the whole chain: percentage change of the mean red, green and blue of the skin '
               'boxes over the last 20 s.',
               'Box means (skin-masked, motion-compensated) after artifact repair and illumination rectification, '
               'divided by their mean, minus 1, x 100.',
               'The pulse is only about 0.3 % (mostly in green). The +-1-2 % drifts seen here come from head pose, '
               'shading and webcam auto-exposure; they are what pushes SNR below the gate.',
               'rgb.png', 'Figure 11. Skin colour change (replayed clip).')
    s += graph('3.8 Method agreement over time (CHROM vs POS vs green)  [row 3, right]',
               'Heart rate from each of the three extractors at every update over the last 5 min.',
               'Each extractor\'s pulse goes through the same spectrum and peak search (stage 9).',
               'The lines overlap when the pulse is real; noise gives method-specific peaks, which is why '
               'agreement is part of the gate. GREEN is the weakest method (it has no motion or lighting '
               'rejection).', 'methods_time.png', 'Figure 12. Extractor agreement (replayed clip).')
    s += [P('3.9 EXPORT RECORDING (CSV)', H3),
          P('Downloads the display log kept by the browser (one row per display update) with columns: '
            '<i>time_iso, hr_card_bpm, hr_card_state, rr_card_brpm, rr_card_state, hr_accepted_bpm, '
            'rr_accepted_brpm, rmssd_ms, hr_source, hr_optical_bpm, hr_acoustic_bpm, quality_pct, video_source</i>. Raw frames, colour traces and audio are saved separately by the '
            'host session recorder (<i>data/sessions/&lt;id&gt;/</i>: frames.csv, node_rgb.csv, estimates.csv, '
            'audio.wav).')]

    # ------------------------------------------------------------------ 4. sessions
    s += [PageBreak(), P('4. Sessions tab (optical vs acoustic agreement)', H1),
          P('A session records the camera HR and the microphone HR together for a fixed time (default 60 s) and '
            'compares them. Neither is a medical reference, so this measures <i>agreement</i>, not accuracy.')]
    s += graph('4.1 Bland-Altman plot',
               'For every paired update: x = mean of optical and acoustic HR, y = optical minus acoustic. Solid '
               'line = mean difference (bias); dashed lines = limits of agreement.',
               'Bias = mean(d); SD = standard deviation of d; limits = bias +- 1.96 SD. Also listed: MAE, RMSE and '
               'Pearson r of the pairs.',
               'Points close to 0 and narrow limits mean the two sensors agree; a trend of y with x means one '
               'channel over- or under-reads at high rates.')
    s += graph('4.2 Optical and acoustic HR trend',
               'Both heart rates against elapsed session time (2 s updates).',
               'Optical = accepted camera HR; acoustic = PCG HR (stage 12).',
               'The two lines should move together.')

    # ------------------------------------------------------------------ 5. diagnostics
    s += [P('5. Diagnostics Studio (colour indices)', H1),
          P('On CAPTURE SNAPSHOT, the sharpest recent frame with a full face is analysed in five regions relative to '
            'the face box (forehead, both cheeks, eye band, lips). The indices are computed from 8-bit camera '
            'values, are <b>uncalibrated</b>, and their ranges are software ranges, not clinical thresholds.')]
    s.append(table([
        ['Index', 'Formula (region means)', 'Meaning'],
        ['Erythema EI', '100 x (log10 R - log10 G), forehead', 'Redness of the skin.'],
        ['Pallor PI', '(G + B of both cheeks) / (2 x (R left + R right))', 'Paleness: less red relative to green/blue.'],
        ['Eye-band yellow YI', '100 x (R + G - 2B) / (R + G + B), eye band', 'Yellowness around the eyes.'],
        ['Lip B/R CR', 'B / R, lips', 'Blueness of the lips relative to red.'],
        ['Facial asymmetry HFI', '100 x |G left - G right| / (G left + G right)', 'Left/right colour difference '
         '(also flags uneven lighting).'],
    ], [33, 75, 62]))

    # ------------------------------------------------------------------ 6. methods
    s += [PageBreak(), P('6. Modes and methods compared', H1),
          P('6.1 Heart-rate card: how the value is kept steady and when it is flagged', H2),
          P('A resting heart rate measured over 30 s cannot jump by 20 BPM in 2 s, but a weak camera signal can '
            'make the estimate hop between spectral peaks. The display stabilizer (backend/display_stabilizer.py) '
            'turns the stream of 2 s readings into one steady value and a status. <b>Each reading is the '
            'robust average of the methods in the live comparison table</b> (SonicVitals, CHROM, POS, GREEN, '
            'TS-CAN, PhysNet, EfficientPhys, microphone): take the median of all available values, average the '
            'methods within 8 BPM of it (re-centred once), and leave the rest out as outliers. A plain mean is '
            'not used because one method locked onto a wrong peak (e.g. GREEN at 53 while the others read 78-81) '
            'would pull it by several BPM. The card and the table come from the same snapshot, and the table marks '
            'each row IN AVERAGE or OUTLIER, LEFT OUT. A value needs at least 3 agreeing methods and at least '
            'half of those available; it is green when at least 4 methods and 60 % agree, amber otherwise. Each '
            'optical estimate is counted once.')]
    s.append(table([
        ['Badge', 'Colour', 'When', 'What the value does'],
        ['ACQUIRING', 'grey', 'No value yet; waiting for 3 readings in a row within +-5 BPM.', '--'],
        ['N OF M METHODS AGREE', 'green / amber', 'Average of the agreeing methods, within 8 BPM of the shown '
         'value. Green: >= 4 methods and >= 60 % agree (or the strict gate passed); amber: 3 agree.',
         'Follows readings smoothly (EMA 0.3: at most 2.4 BPM per update).'],
        ['LOW CONFIDENCE', 'amber', 'Fewer than 3 methods available (e.g. deep models still loading): a single '
         'tracker or microphone estimate.', 'Same smoothing; number in amber.'],
        ['RAPID CHANGE - HELD', 'red', 'Reading more than 8 BPM from the shown value.', 'Held (grey). Only '
         'confident (green) readings can move it: 4 in a row agreeing within +-5 BPM.'],
        ['CHANGE CONFIRMED', 'green', 'Those 4 confident readings agreed on a new level.', 'Switches to the '
         'new level; badge kept 10 s.'],
        ['UNSTABLE READING', 'red', 'Readings scatter by more than 10 BPM, or jumped readings never settled for '
         '15 s.', 'Held, then withdrawn (--). A new value then needs 6 agreeing readings.'],
        ['METHODS DISAGREE', 'red', 'No 3 methods (and no half of them) agree within 8 BPM, e.g. two camps at '
         '47 and 80 BPM.', 'No new value; last value held, then withdrawn. The tooltip lists every method.'],
        ['HOLDING LAST VALUE', 'grey', 'No reading this update (face lost, buffer refilling).', 'Kept up to 15 s, '
         'then NO SIGNAL.'],
    ], [33, 14, 70, 53]))
    s += [P('Why the average of agreeing methods: on a live webcam test (21 Oct 2026, room lighting, glasses) '
            'the tracker alone repeatedly locked onto a peak near 47 BPM while CHROM, POS and the deep models '
            'agreed on about 78-85 BPM, so the card and the comparison table showed different numbers. With the '
            'consensus the card showed, for example, 81 BPM with all 7 methods between 78.7 and 82.6 BPM. There '
            'was no reference pulse in that test, so agreement between methods is not proof of accuracy.', SMALL)]
    s += [P('6.2 Methods in the live comparison', H2)]
    s.append(table([
        ['Method', 'Family', 'Input', 'Principle', 'Runs'],
        ['SonicVitals', 'Ours', '4 skin boxes, background', 'CHROM + POS + GREEN with artifact repair, '
         'illumination rectification, wall-peak rejection, SNR + consensus gate; ensemble spectrum + Bayes tracker '
         'for the continuous estimate.', 'Every 2 s, about 30 ms'],
        ['CHROM', 'Signal processing', 'Skin boxes', 'de Haan & Jeanne 2013: two chrominance signals X = 3R - 2G, '
         'Y = 1.5R + G - 1.5B; pulse = X - alpha Y with alpha = std X / std Y (cancels specular light and motion).',
         'Every 2 s'],
        ['POS', 'Signal processing', 'Skin boxes', 'Wang et al. 2017: projection on the plane orthogonal to skin '
         'tone: S1 = G - B, S2 = -2R + G + B; pulse = S1 + (std S1 / std S2) S2, 1.6 s windows.', 'Every 2 s'],
        ['GREEN', 'Signal processing', 'Skin boxes', 'Verkruysse et al. 2008: inverted green channel (haemoglobin '
         'absorbs green). No rejection of motion or lighting; a lower bound.', 'Every 2 s'],
        ['TS-CAN', 'Deep learning', '72 x 72 face crops, 30 Hz', 'Liu et al. 2020: two-branch temporal-shift '
         'convolutional attention network (appearance + motion). rPPG-Toolbox weights trained on PURE.',
         'Every 12 s, Apple GPU (MPS), about 2 s'],
        ['PhysNet', 'Deep learning', 'Same crops', 'Yu et al. 2019: 3-D convolutional encoder-decoder over '
         'space-time. Runs on the CPU on Macs because MPS lacks its 3-D layers.', 'Every 12 s, CPU, about 2-5 s'],
        ['EfficientPhys', 'Deep learning', 'Same crops', 'Liu et al. 2023: single-branch network with built-in '
         'normalisation, no separate preprocessing.', 'Every 12 s, MPS, about 1 s'],
        ['Microphone (PCG)', 'Acoustic', 'INMP441 node audio', 'Heart-sound envelope autocorrelation; needs the mic on '
         'the chest.', 'Continuous'],
    ], [24, 22, 27, 72, 25]))
    s += [P('The deep models are pretrained on PURE and never trained on your face or on the test datasets '
            '(cross-dataset). The spread and median across all rows are shown under the chart.', SMALL)]
    s += [P('6.3 Camera modes', H2)]
    s.append(table([
        ['', 'Mac webcam', 'ESP32-S3 + GC2145 node'],
        ['Frame rate', 'About 30 fps', 'Skin colour sums at 10 fps; video 5 fps (JPEG q65)'],
        ['Where colour is measured', 'Host computer', 'On the node (raw pixels, clipped and dark pixels excluded); '
         'host face gate decides which samples count'],
        ['Exposure', 'Webcam automatic', 'Skin-metered exposure control (registers P0:0x03/0x04)'],
        ['Deep models', 'Yes (>= 12 fps)', 'No (video too slow)'],
        ['Microphone', 'Node mic if the node is connected', 'Node mic'],
    ], [38, 55, 77]))

    # ------------------------------------------------------------------ 7. benchmark
    s += [PageBreak(), P('7. Benchmark: evaluation modes and results (UBFC-rPPG)', H1),
          P('The same code is evaluated offline on public datasets (Colab notebook, <i>benchmark/</i>). Reference: '
            'the contact PPG recorded with each video, processed exactly like the predictions. Windows of 30 s, '
            'step 10 s, plus whole-video estimates. Metrics: MAE, RMSE, MAPE, Pearson r, share within 5 BPM, '
            'coverage (share of windows with an output) and processing time per 30 s window.')]
    s.append(table([
        ['Evaluation mode', 'Meaning'],
        ['SonicVitals (raw)', 'Single-window estimate in every window, ignoring the gate.'],
        ['SonicVitals (gated)', 'Only windows that pass the gate; coverage reports how many.'],
        ['SonicVitals (display)', 'Replays the dashboard rules (2 s updates, confirmation, median, EMA, hold).'],
        ['SonicVitals (tracked) / (tracked, high conf.)', 'Ensemble spectrum + Bayes tracker, all windows / only '
         'confidence >= 0.8. Added after the 15 Oct run; numbers pending the next Colab run.'],
        ['GREEN, CHROM, POS', 'Standard baselines on the whole face box (and, as an ablation, on the SonicVitals skin boxes).'],
        ['TS-CAN, PhysNet, EfficientPhys [train -> test]', 'Pretrained rPPG-Toolbox weights, tested only on a '
         'dataset they were not trained on.'],
    ], [55, 115]))
    s += [Spacer(1, 4), P('Results: UBFC-rPPG, first 10 subjects, 30 s windows (Colab T4, 15 Oct 2026)', H3)]
    s.append(table([
        ['Method', 'Coverage', 'MAE', 'RMSE', 'r', 'Within 5 BPM', 'ms / 30 s'],
        ['GREEN', '100 %', '22.04', '34.21', '0.07', '47 %', '2.4'],
        ['CHROM', '100 %', '2.40', '6.48', '0.93', '86 %', '19.6'],
        ['POS', '100 %', '2.08', '5.41', '0.95', '86 %', '78.6'],
        ['SonicVitals (raw)', '100 %', '2.30', '4.92', '0.96', '89 %', '71.8'],
        ['<b>SonicVitals (gated)</b>', '81 %', '<b>1.56</b>', '<b>2.73</b>', '<b>0.99</b>', '<b>93 %</b>', '71.8'],
        ['SonicVitals (display)', '86 %', '2.45', '3.30', '0.98', '87 %', '71.8'],
        ['TS-CAN [PURE->UBFC]', '100 %', '1.68', '4.95', '0.96', '89 %', '278.5'],
        ['PhysNet [PURE->UBFC]', '100 %', '1.90', '5.00', '0.95', '86 %', '159.9'],
        ['EfficientPhys [PURE->UBFC]', '100 %', '3.88', '9.09', '0.88', '81 %', '141.9'],
    ], [50, 20, 17, 17, 15, 25, 26]))
    s += [P('MAE/RMSE in BPM, over covered windows only. The gated mode trades 19 % of windows for the lowest '
            'error; errors of raw and deep models include their difficult windows. PURE and VIPL-HR runs are still '
            'to be done.', SMALL)]

    # ------------------------------------------------------------------ 8. formulas
    s += [P('8. Formulas', H1)]
    s.append(table([
        ['Quantity', 'Formula'],
        ['CHROM pulse', 'Per 3 s window, Rn, Gn, Bn = channel / window mean - 1; X = 3Rn - 2Gn; '
         'Y = 1.5Rn + Gn - 1.5Bn; s = X - (std X / std Y) Y; windows overlap-added.'],
        ['POS pulse', 'Per 1.6 s window, C = channel / mean; S1 = G - B; S2 = -2R + G + B; '
         'p = S1 + (std S1 / std S2) S2; overlap-added.'],
        ['de Haan SNR', '10 log10 [ P(|f - f0| <= 0.1 Hz or |f - 2f0| <= 0.2 Hz) / P(rest of 0.5-4 Hz) ]'],
        ['Spectral concentration (SQI)', 'P(|f - f0| <= 0.1 Hz) / P(0.75-2.5 Hz)'],
        ['Illumination rectification', 'beta_c = <skin_c, bg_c> / <bg_c, bg_c> on 0.6-3 Hz relative traces, '
         'clipped to 0-1.5; skin_c -= beta_c bg_c (skipped if bg RMS < 0.3 x skin RMS).'],
        ['Artifact repair', 'd = diff(log RGB); frames with |d - median| > 4 x 1.4826 MAD set to 0; re-integrate.'],
        ['Bayes tracker', 'prior = posterior convolved with Gaussian (SD 3 BPM per 2 s), mixed 98/2 with uniform; '
         'posterior = prior x spectrum^1.5, normalised; HR = argmax; confidence = mass within +-3 BPM.'],
        ['PCG HR', 'Shannon energy E = -x^2 log x^2 (20 ms smoothing); HR = 60 / lag of the autocorrelation peak '
         'in 0.4-1.33 s.'],
        ['RMSSD', 'sqrt(mean(diff(IBI)^2)) over >= 20 clean inter-beat intervals (0.4-1.5 s, within 20 % of median).'],
        ['Fusion', 'If |HR_o - HR_a| <= 8: (w_o HR_o + w_a HR_a)/(w_o + w_a), w_o = SQI x gate, w_a = rho; '
         'else the higher-weight channel.'],
        ['SpO2 ratio', 'R = (AC_red / DC_red) / (AC_blue / DC_blue); SpO2 = A - B R only after calibration.'],
    ], [38, 132]))

    # ------------------------------------------------------------------ 9. limits
    lim = [P('9. Limits to keep in mind', H1)]
    for t in ['The camera pulse is about 0.3 % of skin brightness. Head-pose shading and webcam auto-exposure '
              'produce changes of several %; the chain removes much of this, but in a still, well-lit face SNR '
              'can still fall below the gate. The amber tracked value is a best guess, not a measurement.',
              'Live webcam values have no reference unless you count your pulse or use a finger oximeter at the same '
              'time. Accuracy claims rest on the UBFC benchmark only.',
              'SpO2 and the Diagnostics Studio indices are uncalibrated and not clinical.',
              'The microphone channel needs the INMP441 on the chest; held in the air it gives no heart rate.']:
        lim.append(P('&bull; ' + t))
    s.append(KeepTogether(lim))

    doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm, title='SonicVitals: graphs and methods', author='SonicVitals team')
    doc.build(s, onFirstPage=footer, onLaterPages=footer)
    print(OUT)


if __name__ == '__main__':
    build()
