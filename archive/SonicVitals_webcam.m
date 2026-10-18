function SonicVitals_webcam(varargin)
%SONICVITALS_WEBCAM  Contactless heart rate and breathing rate from a webcam (rPPG).
%
%   SonicVitals_webcam                    % default camera (MacBook camera on a Mac)
%   SonicVitals_webcam('Camera', 2)       % another camera (index; or a name with the webcam add-on)
%   SonicVitals_webcam('Video', 'face.mp4')  % process a recorded video instead of a webcam
%   SonicVitals_webcam('Record', true)    % also save a CSV of every frame and estimate
%
%   MATLAB port of the SonicVitals host pipeline (backend/vitals_dsp.py):
%     face detection -> five-test face gate -> forehead + cheek skin ROIs (frozen while
%     the face is still) -> timestamped mean R,G,B -> uniform 15 Hz grid -> CHROM ->
%     zero-phase band-pass 0.75-2.5 Hz -> Welch PSD (Hann 256, 50 %, nfft 4096) ->
%     parabolic peak with tracking -> HR, accepted only if de Haan SNR >= 0 dB.
%     RR from the green channel (0.15-0.40 Hz) after 15 s, accepted if the peak holds
%     >= 50 % of the 0.05-1 Hz power. Values that do not pass their gate are shown as "--".
%
%   Requirements: base MATLAB (R2019b+). For the live camera either the free
%   "MATLAB Support Package for USB Webcams" (Home > Add-Ons) or, on a Mac, ffmpeg
%   (brew install ffmpeg) is used; the first time, allow MATLAB to use the camera.
%   No toolbox is needed; if the Computer Vision Toolbox is installed its Viola-Jones
%   face detector is used, otherwise a skin-colour face finder.
%
%   Keys in the figure: q = quit, r = reset buffers. Closing the window also quits.
%   Tips: even frontal light, sit 50-80 cm away, look at the camera, keep still.

p = inputParser;
p.addParameter('Camera', []);
p.addParameter('Source', 'auto');       % 'auto' | 'webcam' (add-on) | 'ffmpeg' (Mac camera via ffmpeg)
p.addParameter('FfmpegInput', '');      % testing: replace the camera input arguments of ffmpeg
p.addParameter('Video', '');
p.addParameter('Record', false);
p.addParameter('Resolution', '');
p.addParameter('SelfTest', false);
p.addParameter('CheckImage', '');
p.parse(varargin{:});
opt = p.Results;

P = sv_params();
if opt.SelfTest, sv_selftest(P); return, end
if ~isempty(opt.CheckImage)                  % diagnose framing on one image: face box + gate result
    im = imread(opt.CheckImage);
    useCV = exist('vision.CascadeObjectDetector', 'class') == 8;
    det = []; if useCV, det = vision.CascadeObjectDetector('FrontalFaceCART', 'MergeThreshold', 4); end
    face = sv_detect_face(im, det, useCV);
    if isempty(face), fprintf('No face found in %s\n', opt.CheckImage); return, end
    [ok, msg] = sv_face_gate(im, face);
    fprintf('Image %dx%d, face box [%s], gate %d: %s\n', size(im, 2), size(im, 1), num2str(round(face)), ok, msg);
    return
end

% ------------------------------------------------------------------ source
useVideo = ~isempty(opt.Video);
srcType = 'video';
ffs = [];
if useVideo
    vr = VideoReader(opt.Video);
    srcName = sprintf('video %s', opt.Video);
else
    srcType = lower(opt.Source);
    if strcmp(srcType, 'auto')
        if ~isempty(which('webcam')), srcType = 'webcam'; else, srcType = 'ffmpeg'; end
    end
    if strcmp(srcType, 'webcam')
        if isempty(which('webcam'))
            error(['The webcam function is not available. Install the free "MATLAB Support Package ' ...
                   'for USB Webcams" (Home > Add-Ons), or run with ''Source'', ''ffmpeg''.']);
        end
        if isempty(opt.Camera), cam = webcam; else, cam = webcam(opt.Camera); end
        if ~isempty(opt.Resolution), cam.Resolution = opt.Resolution; end
        srcName = sprintf('webcam %s', cam.Name);
    else
        camIndex = 0; if isnumeric(opt.Camera) && ~isempty(opt.Camera), camIndex = opt.Camera; end
        ffs = sv_ffmpeg_open(camIndex, opt.FfmpegInput);
        ffCleanup = onCleanup(@() sv_ffmpeg_stop(ffs)); %#ok<NASGU>
        srcName = sprintf('camera %d via ffmpeg', camIndex);
    end
end

% ------------------------------------------------------------------ face detector
useCV = exist('vision.CascadeObjectDetector', 'class') == 8;
if useCV
    det = vision.CascadeObjectDetector('FrontalFaceCART', 'MergeThreshold', 4);
    detName = 'Viola-Jones (Computer Vision Toolbox)';
else
    det = [];
    detName = 'skin-colour face finder';
end

% ------------------------------------------------------------------ figure
S = sv_build_figure(srcName, detName);
state = sv_new_state();
if opt.Record
    recFile = fullfile(pwd, ['sonicvitals_' datestr(now, 'yyyymmdd_HHMMSS') '.csv']); %#ok<TNOW1,DATST>
    fid = fopen(recFile, 'w');
    fprintf(fid, 't,face,gated,R,G,B,hr,hr_ok,snr,rr,status\n');
    cleanupFile = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf('Recording to %s\n', recFile);
end

t0 = tic;
lastGated = false; lastBoxes = [];
lastUpdate = -inf;
frameTimes = [];
lockedExposure = false;

while ishandle(S.fig)
    switch srcType
        case 'video'
            if ~hasFrame(vr), break, end
            img = readFrame(vr); t = vr.CurrentTime;
        case 'webcam'
            img = snapshot(cam); t = toc(t0);
        otherwise
            [imgs, ts, ffs] = sv_ffmpeg_grab(ffs);
            if isempty(imgs), pause(0.005); continue, end
            % Older frames since the last loop: skin colour only, with the current skin boxes,
            % so the pulse is sampled at the camera rate even if drawing is slower.
            for k = 1:numel(imgs) - 1
                if lastGated && ~isempty(lastBoxes)
                    c = sv_pixels_mean(imgs{k}, state.skinIdx, lastBoxes);
                    if all(isfinite(c)) && (isempty(state.t) || ts(k) > state.t(end))
                        state.t(end+1) = ts(k); state.rgb(end+1, :) = c;
                    end
                end
            end
            img = imgs{end}; t = ts(end);
            frameTimes = [frameTimes, ts(1:end-1)]; %#ok<AGROW>   % count every camera frame
    end
    frameTimes(end+1) = t; %#ok<AGROW>
    frameTimes(frameTimes < t - 5) = [];

    % Freeze webcam auto exposure / white balance after 3 s if the driver allows it.
    if strcmp(srcType, 'webcam') && ~lockedExposure && t > 3
        lockedExposure = true;
        sv_try_set(cam, 'ExposureMode', 'manual');
        sv_try_set(cam, 'WhiteBalanceMode', 'manual');
    end

    [H, W, ~] = size(img);
    face = sv_detect_face(img, det, useCV);
    gated = false; rgb = [NaN NaN NaN]; boxes = [];
    if ~isempty(face)
        state.lastFaceT = t;
        state.faceRect = sv_smooth_face(state.faceRect, face);
        [gated, msg] = sv_face_gate(img, state.faceRect);
        state.guidance = msg;
        lockRect = sv_locked_rect(state, state.faceRect, P);
        state.lockedRect = lockRect;
        boxes = sv_rppg_rois(lockRect, W, H);
        if ~isequal(lockRect, state.skinRect)          % new position: choose the skin pixels again
            state.skinIdx = sv_skin_pixels(img, lockRect, boxes);
            state.skinRect = lockRect;
        end
        rgb = sv_pixels_mean(img, state.skinIdx, boxes);
        if gated && all(isfinite(rgb))
            if isempty(state.t) || t > state.t(end)
                state.t(end+1) = t;
                state.rgb(end+1, :) = rgb;
                keep = state.t >= state.t(end) - P.bufferS;
                state.t = state.t(keep);
                state.rgb = state.rgb(keep, :);
            end
        end
    elseif isempty(state.lastFaceT) || t - state.lastFaceT > P.maxGapS
        state = sv_new_state();
    end
    lastGated = gated; lastBoxes = boxes;

    % ---- estimates every 0.5 s
    if t - lastUpdate >= 0.5
        lastUpdate = t;
        if ~isempty(state.priorT) && t - state.priorT > 15, state.priorHR = []; end
        est = sv_estimate_optical(state.t, state.rgb, P, state.priorHR);
        alive = ~isempty(state.t) && t - state.t(end) <= P.maxGapS;
        if est.hrOk && alive
            state.priorHR = est.hr; state.priorT = t; state.lastOkT = t;
            state.recentHR = [state.recentHR(max(1, end-1):end), est.hr];
            m = median(state.recentHR);
            if isempty(state.dispHR), state.dispHR = m; else, state.dispHR = 0.8*state.dispHR + 0.2*m; end
            state.dispHRT = t;
        end
        if ~isempty(est.rr) && alive
            if isempty(state.dispRR), state.dispRR = est.rr; else, state.dispRR = 0.8*state.dispRR + 0.2*est.rr; end
            state.dispRRT = t;
        end
        if ~isempty(state.dispHRT) && t - state.dispHRT > 15, state.dispHR = []; end
        if ~isempty(state.dispRRT) && t - state.dispRRT > 15, state.dispRR = []; end
        state.est = est;
        state.status = sv_status(state, est, t, alive, P);
    end

    sv_draw(S, img, state, boxes, gated, t, frameTimes, P);

    if opt.Record
        e = state.est;
        fprintf(fid, '%.4f,%d,%d,%.4f,%.4f,%.4f,%s,%d,%s,%s,%s\n', t, ~isempty(face), gated, rgb, ...
            sv_num(e.hr), e.hrOk, sv_num(e.snr), sv_num(e.rr), state.status);
    end

    key = get(S.fig, 'UserData');
    if ~isempty(key)
        set(S.fig, 'UserData', '');
        if key == 'q', break; end
        if key == 'r', state = sv_new_state(); end
    end
end
if ishandle(S.fig), title(S.axVideo, 'Stopped'); end
end

% =====================================================================================
%                                   parameters / state
% =====================================================================================
function P = sv_params()
P.fs = 15;               % uniform analysis rate (Hz)
P.cardiac = [0.75 2.5];  % 45-150 beats/min
P.resp = [0.15 0.40];    % 9-24 breaths/min
P.maxGapS = 2.0;         % dropouts up to this long are bridged; longer ones restart
P.minCoverage = 0.8;
P.minSegHR = 10;  P.minSegRR = 15;
P.minSnrDb = 0;          % noise-only input passes this in < 5 % of 10-30 s windows
P.minQRR = 0.5;
P.nfft = 4096;
P.trackHalfBPM = 12;  P.trackRatio = 0.5;
P.bufferS = 30;
P.roiRelock = 0.05;      % skin ROIs stay fixed until the face moves > 5 % of its width
end

function s = sv_new_state()
s = struct('t', zeros(1, 0), 'rgb', zeros(0, 3), 'faceRect', [], 'lockedRect', [], ...
    'lastFaceT', [], 'priorHR', [], 'priorT', [], 'lastOkT', [], 'recentHR', [], 'skinIdx', [], 'skinRect', [], ...
    'dispHR', [], 'dispHRT', [], 'dispRR', [], 'dispRRT', [], 'guidance', 'Searching for a face...', ...
    'status', 'NO FACE', 'est', sv_empty_est());
end

function e = sv_empty_est()
e = struct('hr', [], 'hrOk', false, 'snr', [], 'quality', 0, 'rr', [], 'rrQ', 0, 'segS', 0, ...
    'coverage', 0, 'bvp', [], 'resp', [], 'freqs', [], 'psd', [], 'tracked', false);
end

function st = sv_status(state, est, t, alive, P)
recentOk = ~isempty(state.lastOkT) && t - state.lastOkT <= 15;
if isempty(state.faceRect)
    st = 'NO FACE';
elseif alive && est.segS >= P.minSegHR
    st = 'STABLE';
elseif recentOk
    st = 'REACQUIRING';
else
    st = 'CALIBRATING';
end
end

% =====================================================================================
%                                   face handling
% =====================================================================================
function face = sv_detect_face(img, det, useCV)
face = [];
if useCV
    bb = step(det, img);
    if ~isempty(bb)
        [~, k] = max(bb(:, 3) .* bb(:, 4));
        face = double(bb(k, :));
    end
    return
end
% Skin-colour face finder (no toolbox): YCbCr skin mask on a 4x downsampled image,
% then the dominant skin column/row run gives the face box.
k = 4;
sm = double(img(1:k:end, 1:k:end, :));
R = sm(:, :, 1); G = sm(:, :, 2); B = sm(:, :, 3);
Y  = 0.299*R + 0.587*G + 0.114*B;
Cb = 128 - 0.168736*R - 0.331264*G + 0.5*B;
Cr = 128 + 0.5*R - 0.418688*G - 0.081312*B;
% Skin is redder (Cr >= 140) and less blue (Cb <= 122) than beige walls and curtains
% (measured: curtain Cr 131-139 / Cb 113-127, wall Cr 127-134; skin Cr 141-167 / Cb 101-116).
mask = Cr >= 140 & Cr <= 175 & Cb >= 77 & Cb <= 122 & Y > 40;
% 3x3 erosion breaks thin bridges between the face and skin-coloured background.
mask = conv2(double(mask), ones(3), 'same') >= 9;
if nnz(mask) < 0.01 * numel(mask), return, end
cols = sum(mask, 1);
cRun = sv_longest_run(cols > 0.25 * max(cols));
if isempty(cRun), return, end
rows = sum(mask(:, cRun(1):cRun(2)), 2)';
rRun = sv_longest_run(rows > 0.25 * max(rows));
if isempty(rRun), return, end
% Skin coverage of the forehead and chin varies with hair, beard and light, so the box is
% built from the face width and the cheekbone row (the widest skin row) using the same
% proportions as a Viola-Jones face box: width = 1.3 x skin width, square, cheekbones at 50 %.
rs = conv(rows, ones(1, 3) / 3, 'same');
inRun = rRun(1):rRun(2);
wide = inRun(rs(inRun) >= 0.9 * max(rs(inRun)));
cy = median(wide);
ws = cRun(2) - cRun(1) + 1;
cx = (cRun(1) + cRun(2)) / 2;
w = 1.3 * ws;
face = k * [cx - w / 2 - 0.5, cy - 0.5 * w - 0.5, w, w] + [1 1 0 0];
end

function run = sv_longest_run(v)
run = [];
d = diff([0, v(:)', 0]);
s = find(d == 1); e = find(d == -1) - 1;
if isempty(s), return, end
[~, k] = max(e - s);
run = [s(k), e(k)];
end

function r = sv_smooth_face(prev, face)
% Heavy smoothing for detector jitter, faster following for real movement.
if isempty(prev), r = face; return, end
shift = max([abs(face(1)+face(3)/2 - prev(1)-prev(3)/2), abs(face(2)+face(4)/2 - prev(2)-prev(4)/2), ...
             abs(face(3)-prev(3)), abs(face(4)-prev(4))]) / max(prev(3), 1);
a = 0.4; if shift < 0.06, a = 0.05; end
r = (1 - a) * prev + a * face;
end

function r = sv_locked_rect(state, rect, P)
r = state.lockedRect;
if ~isempty(r)
    move = max([abs(rect(1)+rect(3)/2 - r(1)-r(3)/2), abs(rect(2)+rect(4)/2 - r(2)-r(4)/2), ...
                abs(rect(3)-r(3)), abs(rect(4)-r(4))]) / max(r(3), 1);
    if move <= P.roiRelock, return, end
end
r = round(rect);
end

function boxes = sv_rppg_rois(f, W, H)
% Forehead (below the hairline, above the brows) and both upper cheeks, [x y w h] rows.
rel = [0.22 0.10 0.56 0.14; 0.15 0.46 0.22 0.18; 0.63 0.46 0.22 0.18];
boxes = zeros(3, 4);
for i = 1:3
    x = max(1, round(f(1) + rel(i, 1) * f(3)));
    y = max(1, round(f(2) + rel(i, 2) * f(4)));
    w = max(2, min(W - x, round(rel(i, 3) * f(3))));
    h = max(2, min(H - y, round(rel(i, 4) * f(4))));
    boxes(i, :) = [x y w h];
end
end

function rgb = sv_roi_mean(img, boxes)
tot = zeros(1, 3); n = 0;
for i = 1:size(boxes, 1)
    b = boxes(i, :);
    patch = double(img(b(2):b(2)+b(4)-1, b(1):b(1)+b(3)-1, :));
    tot = tot + reshape(sum(sum(patch, 1), 2), 1, 3);
    n = n + b(3) * b(4);
end
if n == 0, rgb = [NaN NaN NaN]; else, rgb = tot / n; end
end

function idx = sv_skin_pixels(img, f, boxes)
% Skin pixels between the forehead and the upper lip, chosen by the person's own skin
% colour (median Cr/Cb of the forehead and cheek boxes), so eyebrows, eyes, beard, hair
% and background are left out. The set stays fixed until the face moves, so the average
% does not flicker as pixels enter and leave a threshold.
[H, W, ~] = size(img);
x0 = max(1, round(f(1) + 0.10 * f(3))); x1 = min(W, round(f(1) + 0.90 * f(3)));
y0 = max(1, round(f(2) + 0.06 * f(4))); y1 = min(H, round(f(2) + 0.72 * f(4)));
sub = double(img(y0:y1, x0:x1, :));
R = sub(:, :, 1); G = sub(:, :, 2); B = sub(:, :, 3);
Y  = 0.299*R + 0.587*G + 0.114*B;
Cb = 128 - 0.168736*R - 0.331264*G + 0.5*B;
Cr = 128 + 0.5*R - 0.418688*G - 0.081312*B;
ref = zeros(0, 3);
for i = 1:size(boxes, 1)
    b = boxes(i, :);
    bx = max(1, b(1) - x0 + 1):min(size(sub, 2), b(1) + b(3) - x0);
    by = max(1, b(2) - y0 + 1):min(size(sub, 1), b(2) + b(4) - y0);
    ref = [ref; [reshape(Y(by, bx), [], 1), reshape(Cb(by, bx), [], 1), reshape(Cr(by, bx), [], 1)]]; %#ok<AGROW>
end
idx = [];
if size(ref, 1) < 50, return, end
cbM = median(ref(:, 2)); crM = median(ref(:, 3));
m = abs(Cb - cbM) <= 8 & abs(Cr - crM) <= 10 & Y > 35 & Y < 240;   % <240: skip clipped pixels
m = conv2(double(m), ones(3), 'same') >= 9;                        % drop isolated / edge pixels
[r, c] = find(m);
if numel(r) < 400, return, end
idx = sub2ind([H W], r + y0 - 1, c + x0 - 1);
end

function rgb = sv_pixels_mean(img, idx, boxes)
% Mean R,G,B over the chosen skin pixels; falls back to the three boxes if none were found.
if isempty(idx), rgb = sv_roi_mean(img, boxes); return, end
n = numel(img(:, :, 1));
v = double(img([idx; idx + n; idx + 2*n]));
k = numel(idx);
rgb = [mean(v(1:k)), mean(v(k+1:2*k)), mean(v(2*k+1:end))];
end

function [ok, msg] = sv_face_gate(img, f)
% Five-test validity gate (edges, scale, aspect, ROIs inside, illumination).
[H, W, ~] = size(img);
ok = false;
mx = max(6, round(0.035 * W)); my = max(6, round(0.035 * H));
if f(1) < mx || f(1) + f(3) > W - mx || f(2) < my || f(2) + f(4) > H - my
    msg = 'Face touches the frame edge: centre your face.'; return
end
if f(3) < 0.20 * W || f(4) < 0.22 * H, msg = 'Too far: move closer.'; return, end
if f(3) > 0.88 * W || f(4) > 0.90 * H, msg = 'Too close: move back.'; return, end
asp = f(3) / max(1, f(4));
if asp < 0.65 || asp > 1.30, msg = 'Face turned: look at the camera.'; return, end
boxes = sv_rppg_rois(f, W, H);
if any(boxes(:, 1) < 2 | boxes(:, 2) < 2 | boxes(:, 1) + boxes(:, 3) > W - 2 | boxes(:, 2) + boxes(:, 4) > H - 2)
    msg = 'Skin region cut off: centre your face.'; return
end
lc = sv_roi_mean(img, boxes(2, :)); rc = sv_roi_mean(img, boxes(3, :));
l1 = mean(lc); l2 = mean(rc);
if l1 < 15 || l2 < 15, msg = 'Too dark: add frontal light.'; return, end
if abs(l1 - l2) / (l1 + l2 + 1e-5) > 0.45, msg = 'Uneven light on the face.'; return, end
ok = true; msg = 'Full face visible and centred';
end

function sv_try_set(obj, prop, val)
try
    if isprop(obj, prop), obj.(prop) = val; end
catch
end
end

% =====================================================================================
%                                   signal processing
% =====================================================================================
function e = sv_estimate_optical(t, rgb, P, priorHR)
e = sv_empty_est();
[tu, xu, cov] = sv_resample_uniform(t, rgb, P);
if numel(tu) < 25, if ~isempty(tu), e.segS = tu(end) - tu(1); end, return, end
fs = P.fs;
e.segS = tu(end) - tu(1);
e.coverage = cov;

pulse = sv_chrom(xu);
e.bvp = sv_standardize(sv_bandpass(pulse, fs, P.cardiac, 3));

if e.segS >= P.minSegHR
    % Drift below 0.6 Hz (light changes, slow movement) is removed first so it cannot leak
    % into the bottom of the cardiac band; the pulse harmonics stay in for the SNR.
    pulseHp = sv_highpass(pulse, fs, 0.6, 4);
    [f, pxx] = sv_welch(sv_standardize(pulseHp), fs, 256, P.nfft);
    [f0, tracked] = sv_tracked_peak(f, pxx, P.cardiac, priorHR, P);
    if ~isempty(f0)
        e.hr = 60 * f0;
        e.snr = sv_dehaan_snr(f, pxx, f0);
        e.quality = sv_concentration(f, pxx, f0, P.cardiac, 0.1);
        e.tracked = tracked;
        e.hrOk = isfinite(e.snr) && e.snr >= P.minSnrDb && cov >= P.minCoverage;
        e.freqs = f; e.psd = pxx;
    end
end

g = xu(:, 2) - mean(xu(:, 2));
e.resp = sv_standardize(sv_bandpass(g, fs, P.resp, 2));
if e.segS >= P.minSegRR
    gs = sv_standardize(g);
    [f, pxx] = sv_welch(gs, fs, numel(gs), P.nfft);
    fr = sv_band_peak(f, pxx, P.resp);
    if ~isempty(fr)
        e.rrQ = sv_concentration(f, pxx, fr, [0.05 1.0], 1 / e.segS);
        if e.rrQ >= P.minQRR, e.rr = 60 * fr; end
    end
end
end

function [tu, xu, cov] = sv_resample_uniform(t, x, P)
% Linear interpolation of the most recent gap-free run (gaps <= maxGapS bridged) onto P.fs.
tu = []; xu = []; cov = 0;
if numel(t) < 2, return, end
gaps = find(diff(t) > P.maxGapS);
s = 1; if ~isempty(gaps), s = gaps(end) + 1; end
t = t(s:end); x = x(s:end, :);
if numel(t) < 2 || t(end) - t(1) < 1 / P.fs, return, end
tu = (t(1):1/P.fs:t(end))';
xu = interp1(t(:), x, tu, 'linear');
missing = sum(max(0, diff(t) - 0.25));
cov = 1 - missing / (t(end) - t(1));
end

function h = sv_chrom(rgb)
% CHROM projection (de Haan & Jeanne 2013) with overlap-add.
N = size(rgb, 1);
L = min(45, max(12, floor(N / 2))); L = min(L, N);
h = zeros(N, 1);
for i = 1:(N - L + 1)
    seg = rgb(i:i+L-1, :);
    cn = seg ./ (mean(seg, 1) + 1e-9) - 1;
    X = 3 * cn(:, 1) - 2 * cn(:, 2);
    Y = 1.5 * cn(:, 1) + cn(:, 2) - 1.5 * cn(:, 3);
    a = 0; if std(Y) > 0, a = std(X) / std(Y); end
    s = X - a * Y;
    h(i:i+L-1) = h(i:i+L-1) + (s - mean(s));
end
end

function y = sv_bandpass(x, fs, band, order)
% Zero-phase Butterworth-magnitude band-pass applied in the frequency domain
% (|H|^2, equivalent to forward-backward filtering), with mirrored padding.
x = x(:);
N = numel(x);
if N < 4, y = x - mean(x); return, end
pad = min(N - 1, round(3 * fs));
xp = [flipud(x(2:pad+1)); x; flipud(x(end-pad:end-1))];
M = numel(xp);
nf = 2^nextpow2(M);
X = fft(xp - mean(xp), nf);
f = (0:nf-1)' * fs / nf;
f = min(f, fs - f);                                   % two-sided frequency magnitude
f(f == 0) = eps;
Hhp = (f / band(1)).^order ./ sqrt(1 + (f / band(1)).^(2*order));
Hlp = 1 ./ sqrt(1 + (f / band(2)).^(2*order));
yp = real(ifft(X .* (Hhp .* Hlp).^2));
y = yp(pad+1:pad+N);
end

function y = sv_highpass(x, fs, fc, order)
% Zero-phase Butterworth-magnitude high-pass (frequency domain, mirrored padding).
x = x(:);
N = numel(x);
if N < 4, y = x - mean(x); return, end
pad = min(N - 1, round(3 * fs));
xp = [flipud(x(2:pad+1)); x; flipud(x(end-pad:end-1))];
nf = 2^nextpow2(numel(xp));
X = fft(xp - mean(xp), nf);
f = (0:nf-1)' * fs / nf;
f = min(f, fs - f); f(f == 0) = eps;
H = (f / fc).^order ./ sqrt(1 + (f / fc).^(2*order));
yp = real(ifft(X .* H.^2));
y = yp(pad+1:pad+N);
end

function [f, pxx] = sv_welch(x, fs, nperseg, nfft)
% Welch PSD: Hann window, 50 % overlap, zero-padded FFT, one-sided density.
x = x(:) - mean(x);
nperseg = min(numel(x), nperseg);
nfft = max(nfft, nperseg);
w = 0.5 - 0.5 * cos(2 * pi * (0:nperseg-1)' / nperseg);    % periodic Hann
step = max(1, floor(nperseg / 2));
starts = 1:step:(numel(x) - nperseg + 1);
acc = zeros(nfft, 1);
for s = starts
    seg = x(s:s+nperseg-1);
    seg = seg - mean(seg);
    acc = acc + abs(fft(seg .* w, nfft)).^2;
end
pxx = acc / (numel(starts) * fs * sum(w.^2));
nh = floor(nfft / 2) + 1;
pxx = pxx(1:nh);
pxx(2:end-1) = 2 * pxx(2:end-1);
f = (0:nh-1)' * fs / nfft;
end

function [f0, pk] = sv_band_peak(f, pxx, band)
% Largest local maximum inside the band (a value at the band edge that keeps rising
% outside the band is the skirt of out-of-band power, not a peak).
f0 = []; pk = 0;
idx = find(f >= band(1) & f <= band(2));
idx = idx(idx > 1 & idx < numel(pxx));
if isempty(idx), return, end
isMax = pxx(idx) >= pxx(idx - 1) & pxx(idx) >= pxx(idx + 1);
idx = idx(isMax);
if isempty(idx), return, end
[pk, j] = max(pxx(idx));
k = idx(j);
off = 0;
if k > 1 && k < numel(pxx)
    a = pxx(k-1); b = pxx(k); c = pxx(k+1);
    den = a - 2*b + c;
    if den < 0, off = max(-0.5, min(0.5, 0.5 * (a - c) / den)); end
end
f0 = (k - 1 + off) * (f(2) - f(1));
end

function [f0, tracked] = sv_tracked_peak(f, pxx, band, priorHR, P)
% Global peak, or the peak within +-12 BPM of the last accepted HR if it has >= 50 % of its power.
[fg, pg] = sv_band_peak(f, pxx, band);
f0 = fg; tracked = false;
if isempty(fg) || isempty(priorHR), return, end
half = P.trackHalfBPM / 60;
lo = max(band(1), priorHR/60 - half); hi = min(band(2), priorHR/60 + half);
if lo >= hi, return, end
[fl, pl] = sv_band_peak(f, pxx, [lo hi]);
if ~isempty(fl) && pl >= P.trackRatio * pg && abs(fl - fg) > 1e-9
    f0 = fl; tracked = true;
end
end

function snr = sv_dehaan_snr(f, pxx, f0)
inb = f >= 0.5 & f <= 4.0;
sig = inb & (abs(f - f0) <= 0.1 | abs(f - 2*f0) <= 0.2);
noi = inb & ~sig;
ps = sum(pxx(sig)); pn = sum(pxx(noi));
if ps <= 0 || pn <= 0, snr = NaN; else, snr = 10 * log10(ps / pn); end
end

function q = sv_concentration(f, pxx, f0, band, half)
inb = f >= band(1) & f <= band(2);
tot = sum(pxx(inb));
if tot <= 0, q = 0; return, end
q = sum(pxx(inb & abs(f - f0) <= half)) / tot;
end

function z = sv_standardize(x)
x = x(:);
s = std(x);
if s > 0, z = (x - mean(x)) / s; else, z = x - mean(x); end
end

% =====================================================================================
%                                   display
% =====================================================================================
function S = sv_build_figure(srcName, detName)
S.fig = figure('Name', 'SonicVitals - webcam rPPG', 'NumberTitle', 'off', 'Color', [0.97 0.97 0.95], ...
    'Position', [80 80 1280 760], 'KeyPressFcn', @(f, ev) set(f, 'UserData', ev.Character));
tl = tiledlayout(S.fig, 3, 4, 'TileSpacing', 'compact', 'Padding', 'compact');
S.axVideo = nexttile(tl, 1, [2 2]);
S.img = image(S.axVideo, zeros(480, 640, 3, 'uint8'));
axis(S.axVideo, 'image', 'off');
title(S.axVideo, sprintf('Source: %s   |   Face: %s', srcName, detName), 'FontSize', 9, 'Interpreter', 'none');
hold(S.axVideo, 'on');
S.faceBox = rectangle(S.axVideo, 'Position', [1 1 1 1], 'EdgeColor', [0.1 0.8 0.3], 'LineWidth', 2, 'Visible', 'off');
for i = 1:3
    S.roiBox(i) = rectangle(S.axVideo, 'Position', [1 1 1 1], 'EdgeColor', [0.95 0.85 0.1], 'LineWidth', 1, 'Visible', 'off');
end
S.statusTxt = text(S.axVideo, 10, 18, '', 'Color', 'w', 'FontWeight', 'bold', 'FontSize', 11, ...
    'BackgroundColor', [0.06 0.42 0.29], 'Margin', 4, 'Interpreter', 'none');

S.axVals = nexttile(tl, 3, [2 2]);
axis(S.axVals, 'off');
labels = {'HEART RATE', 'RESPIRATORY RATE', 'SIGNAL SNR', 'SIGNAL QUALITY', 'ANALYSIS SEGMENT', 'FRAME RATE'};
units = {'BPM', 'br/min', 'dB', '%', 's', 'fps'};
for i = 1:6
    r = ceil(i / 2); c = mod(i - 1, 2);
    x0 = 0.02 + 0.5 * c; y0 = 1 - 0.33 * r + 0.04;
    rectangle(S.axVals, 'Position', [x0 y0 0.46 0.27], 'FaceColor', 'w', 'EdgeColor', [0.8 0.85 0.82]);
    text(S.axVals, x0 + 0.02, y0 + 0.22, labels{i}, 'FontSize', 9, 'FontWeight', 'bold', 'Color', [0.35 0.4 0.38]);
    S.val(i) = text(S.axVals, x0 + 0.02, y0 + 0.11, '--', 'FontSize', 26, 'FontWeight', 'bold', 'Color', [0.04 0.16 0.13]);
    text(S.axVals, x0 + 0.33, y0 + 0.09, units{i}, 'FontSize', 10, 'Color', [0.35 0.4 0.38]);
    S.sub(i) = text(S.axVals, x0 + 0.02, y0 + 0.03, '', 'FontSize', 8, 'Color', [0.35 0.4 0.38], 'Interpreter', 'none');
end
xlim(S.axVals, [0 1]); ylim(S.axVals, [0 1]);

S.axBvp = nexttile(tl, 9, [1 2]);
S.bvp = plot(S.axBvp, nan, nan, 'Color', [0.06 0.42 0.29], 'LineWidth', 1.2);
title(S.axBvp, 'Recovered pulse (CHROM, 0.75-2.5 Hz)', 'FontSize', 9); xlabel(S.axBvp, 'Time (s)'); ylabel(S.axBvp, 'z-score');
grid(S.axBvp, 'on');
S.axResp = nexttile(tl, 11);
S.resp = plot(S.axResp, nan, nan, 'Color', [0.72 0.33 0.19], 'LineWidth', 1.2);
title(S.axResp, 'Respiration (green, 0.15-0.40 Hz)', 'FontSize', 9); xlabel(S.axResp, 'Time (s)');
grid(S.axResp, 'on');
S.axPsd = nexttile(tl, 12);
S.psd = plot(S.axPsd, nan, nan, 'Color', [0.06 0.42 0.29], 'LineWidth', 1.2);
hold(S.axPsd, 'on');
S.psdPk = plot(S.axPsd, nan, nan, 'o', 'Color', [0.85 0.33 0.31], 'MarkerFaceColor', [0.85 0.33 0.31]);
title(S.axPsd, 'Pulse spectrum (Welch)', 'FontSize', 9); xlabel(S.axPsd, 'Hz'); ylabel(S.axPsd, 'dB');
xlim(S.axPsd, [0.5 3.5]); grid(S.axPsd, 'on');
end

function sv_draw(S, img, state, boxes, gated, t, frameTimes, P)
[H, W, ~] = size(img);
set(S.img, 'CData', img, 'XData', [1 W], 'YData', [1 H]);
set(S.axVideo, 'XLim', [0.5 W + 0.5], 'YLim', [0.5 H + 0.5]);
if ~isempty(state.faceRect)
    col = [0.1 0.8 0.3]; if ~gated, col = [1 0.55 0]; end
    set(S.faceBox, 'Position', state.faceRect, 'EdgeColor', col, 'Visible', 'on');
else
    set(S.faceBox, 'Visible', 'off');
end
for i = 1:3
    if ~isempty(boxes) && gated
        set(S.roiBox(i), 'Position', boxes(i, :), 'Visible', 'on');
    else
        set(S.roiBox(i), 'Visible', 'off');
    end
end

e = state.est;
switch state.status
    case 'STABLE'
        if e.hrOk, sig = sprintf('SNR %+.1f dB', e.snr); else, sig = 'LOW SIGNAL - HOLD STILL'; end
        msg = sprintf('FACE GATE PASSED | %.0f s | %s', e.segS, sig);
    case 'CALIBRATING'
        if gated
            msg = sprintf('CALIBRATING: %d s remaining', max(0, round(P.minSegHR - e.segS)));
        else
            msg = ['ALIGN FACE: ' state.guidance];
        end
    case 'REACQUIRING'
        msg = 'REACQUIRING: last value held';
    otherwise
        msg = 'NO FACE DETECTED';
end
set(S.statusTxt, 'String', msg);

fps = NaN; if numel(frameTimes) > 2, fps = (numel(frameTimes) - 1) / (frameTimes(end) - frameTimes(1)); end
vals = {state.dispHR, state.dispRR, e.snr, 100 * e.quality, e.segS, fps};
fmt = {'%.1f', '%.1f', '%+.1f', '%.0f', '%.0f', '%.1f'};
for i = 1:6
    v = vals{i};
    if isempty(v) || ~isfinite(v) || (i == 4 && isempty(e.hr)), s = '--'; else, s = sprintf(fmt{i}, v); end
    set(S.val(i), 'String', s);
end
subs = {sv_hr_sub(state, e, t), sv_rr_sub(e), 'gate: >= 0 dB', 'power at peak / band power', ...
        sprintf('coverage %.0f %%, %d skin px', 100 * e.coverage, numel(state.skinIdx)), sprintf('t = %.0f s', t)};
for i = 1:6, set(S.sub(i), 'String', subs{i}); end

if ~isempty(e.bvp)
    n = min(numel(e.bvp), round(10 * P.fs));
    tt = (-(n-1):0) / P.fs;
    set(S.bvp, 'XData', tt, 'YData', e.bvp(end-n+1:end));
    set(S.resp, 'XData', tt, 'YData', e.resp(end-n+1:end));
    xlim(S.axBvp, [tt(1) 0]); xlim(S.axResp, [tt(1) 0]);
end
if ~isempty(e.freqs)
    m = e.freqs >= 0.5 & e.freqs <= 3.5;
    db = 10 * log10(max(e.psd(m), 1e-12)); db = db - max(db);
    set(S.psd, 'XData', e.freqs(m), 'YData', db);
    set(S.psdPk, 'XData', e.hr / 60, 'YData', interp1(e.freqs(m), db, e.hr / 60));
else
    set(S.psd, 'XData', nan, 'YData', nan); set(S.psdPk, 'XData', nan, 'YData', nan);
end
drawnow limitrate
end

function s = sv_hr_sub(state, e, t)
if isempty(state.dispHR)
    if isempty(e.hr), s = 'needs 10 s of face'; else, s = sprintf('raw %.0f BPM rejected (SNR)', e.hr); end
elseif t - state.dispHRT > 3
    s = sprintf('held %.0f s', t - state.dispHRT);
else
    s = 'accepted';
end
end

function s = sv_rr_sub(e)
if isempty(e.rr)
    if e.segS < 15, s = 'needs 15 s segment'; else, s = sprintf('peak share %.2f < 0.50', e.rrQ); end
else
    s = sprintf('peak share %.2f', e.rrQ);
end
end

function s = sv_num(v)
if isempty(v) || ~isfinite(v), s = ''; else, s = sprintf('%.3f', v); end
end

% =====================================================================================
%                                   self-test (no camera needed)
% =====================================================================================
function sv_selftest(P)
% SonicVitals_webcam('SelfTest', true): checks the DSP on synthetic signals with known answers.
rng(1);
fprintf('SonicVitals MATLAB self-test\n');
for hrTrue = [52 72 110]
    [t, rgb] = sv_synthetic(hrTrue, 15, 30);
    e = sv_estimate_optical(t, rgb, P, []);
    fprintf('  synthetic %3d BPM / 15 br/min -> HR %.1f (SNR %+.1f dB, accepted %d), RR %s\n', ...
        hrTrue, e.hr, e.snr, e.hrOk, sv_num(e.rr));
    assert(abs(e.hr - hrTrue) <= 2 && e.hrOk, 'HR self-test failed');
end
assert(abs(e.rr - 15) <= 1.5, 'RR self-test failed');
% Pulse under strong slow drift (light changes, head sway): the peak must not snap to the band edge.
okD = 0; nD = 20;
for k = 1:nD
    [t, rgb] = sv_synthetic(72, 15, 30);
    drift = cumsum(randn(numel(t), 1)) * 0.15;
    rgb = rgb + drift .* [1 0.8 0.7];
    e = sv_estimate_optical(t, rgb, P, []);
    okD = okD + (~isempty(e.hr) && abs(e.hr - 72) <= 3);
end
fprintf('  72 BPM under strong drift: correct peak in %d of %d windows\n', okD, nD);
assert(okD >= 0.8 * nD, 'drift self-test failed');
acc = 0; n = 200;
for k = 1:n
    t = (0:240) / 8;
    e = sv_estimate_optical(t, 150 + randn(numel(t), 3), P, []);
    acc = acc + e.hrOk;
end
fprintf('  pure noise accepted as HR in %.1f %% of 30 s windows (target <= 6 %%)\n', 100 * acc / n);
assert(acc / n <= 0.06, 'noise gate self-test failed');
img = [];
here = fileparts(mfilename('fullpath'));
f = fullfile(here, '..', 'Report', 'images', 'anatomical_dashboard.png');
if exist(f, 'file')
    img = imread(f);
    img = img(round(0.30*end):round(0.82*end), 1:round(0.40*end), :);
    face = sv_detect_face(img, [], false);
    fprintf('  skin-colour face finder on a test image: box [%s]\n', num2str(round(face)));
    assert(~isempty(face), 'face finder self-test failed');
end
% Optional extra images (e.g. screenshots of the live camera) passed via SV_TEST_IMAGES.
extra = strsplit(getenv('SV_TEST_IMAGES'), pathsep);
for k = 1:numel(extra)
    if isempty(extra{k}) || ~exist(extra{k}, 'file'), continue, end
    im = imread(extra{k});
    if size(im, 3) == 1, im = repmat(im, 1, 1, 3); end
    face = sv_detect_face(im(:, :, 1:3), [], false);
    fprintf('  face finder on %s: box [%s]\n', extra{k}, num2str(round(face)));
    if ~isempty(face)
        b = round(face);
        x1 = max(1, b(1)); y1 = max(1, b(2));
        x2 = min(size(im, 2), b(1) + b(3)); y2 = min(size(im, 1), b(2) + b(4));
        im([y1:y1+2, y2-2:y2], x1:x2, 1) = 255; im([y1:y1+2, y2-2:y2], x1:x2, 2:3) = 0;
        im(y1:y2, [x1:x1+2, x2-2:x2], 1) = 255; im(y1:y2, [x1:x1+2, x2-2:x2], 2:3) = 0;
    end
    [~, nm] = fileparts(extra{k});
    imwrite(im(:, :, 1:3), fullfile(tempdir, ['sv_face_' nm '.png']));
end
fprintf('All self-tests passed.\n');
end

function [t, rgb] = sv_synthetic(hr, rr, dur)
% Irregular 25-35 fps timestamps, pulse (green strongest) and breathing-borne illumination.
dt = 1/35 + rand(1, round(dur * 35)) * (1/25 - 1/35);
t = cumsum(dt); t = t(t < dur);
pulse = 0.004 * sin(2 * pi * hr / 60 * t(:));
illum = 1 + 0.01 * sin(2 * pi * rr / 60 * t(:)) + 0.002 * randn(numel(t), 1);
rgb = (illum .* [180 120 100]) .* (1 + pulse .* [0.33 0.77 0.53]) + 0.1 * randn(numel(t), 3);
end

% =====================================================================================
%                     camera via ffmpeg (no add-on; macOS AVFoundation)
% =====================================================================================
function ffs = sv_ffmpeg_open(camIndex, inputOverride)
ff = '';
for c = {'/opt/homebrew/bin/ffmpeg', '/usr/local/bin/ffmpeg', '/usr/bin/ffmpeg'}
    if exist(c{1}, 'file'), ff = c{1}; break, end
end
if isempty(ff)
    error(['No camera access: install the "MATLAB Support Package for USB Webcams" (Home > Add-Ons) ' ...
           'or ffmpeg (brew install ffmpeg), then run again.']);
end
ffs.dir = fullfile(tempdir, sprintf('sv_cam_%d_%d', feature('getpid'), round(now * 1e5))); %#ok<TNOW1>
mkdir(ffs.dir);
ffs.fps = 30;
ffs.t0 = tic;
ffs.gotAny = false;
if isempty(inputOverride)
    % camera only (no audio); fps filter gives a constant 30 fps timeline, so frame n was captured at (n-1)/30 s
    inArgs = sprintf('-f avfoundation -framerate 30 -i "%d:none"', camIndex);
else
    inArgs = inputOverride;
end
cmd = sprintf('"%s" -hide_banner -loglevel error %s -vf "fps=30,scale=640:-2" -q:v 3 "%s/sv_%%06d.jpg" > "%s/ffmpeg.log" 2>&1 &', ...
    ff, inArgs, ffs.dir, ffs.dir);
system(cmd);
fprintf('Camera started (ffmpeg). If macOS asks, allow MATLAB to use the camera.\n');
end

function [imgs, ts, ffs] = sv_ffmpeg_grab(ffs)
% Returns the complete frames written since the last call (the newest file may still be
% being written) and their capture times; at most the last 15 are kept if MATLAB fell behind.
imgs = {}; ts = [];
d = dir(fullfile(ffs.dir, 'sv_*.jpg'));
if numel(d) < 2
    if ~ffs.gotAny && toc(ffs.t0) > 12
        logTxt = '';
        lf = fullfile(ffs.dir, 'ffmpeg.log');
        if exist(lf, 'file'), logTxt = strtrim(fileread(lf)); end
        error(['The camera did not deliver frames. On macOS open System Settings > Privacy & Security > ' ...
               'Camera, allow MATLAB, then restart MATLAB and run again. Close other apps using the camera ' ...
               '(FaceTime, Zoom, Photo Booth). ffmpeg said: %s'], logTxt);
    end
    return
end
names = sort({d.name});
complete = names(1:end-1);
use = complete(max(1, end-14):end);
for k = 1:numel(use)
    try
        imgs{end+1} = imread(fullfile(ffs.dir, use{k})); %#ok<AGROW>
        ts(end+1) = (sscanf(use{k}, 'sv_%d.jpg') - 1) / ffs.fps; %#ok<AGROW>
    catch
    end
end
if ~isempty(imgs), ffs.gotAny = true; end
for k = 1:numel(complete)
    delete(fullfile(ffs.dir, complete{k}));
end
end

function sv_ffmpeg_stop(ffs)
if isempty(ffs), return, end
system(sprintf('pkill -f "%s" > /dev/null 2>&1', ffs.dir));
pause(0.2);
try
    rmdir(ffs.dir, 's');
catch
end
end
