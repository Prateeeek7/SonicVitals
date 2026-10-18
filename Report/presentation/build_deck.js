// Builds SonicVitals_Final.pptx. Run: NODE_PATH=<dir with pptxgenjs> node build_deck.js
const path = require("path");
const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const fa = require("react-icons/fa");
const { applyTheme } = require(process.env.PPTX_SKILL + "/scripts/apply_theme.js");

const A = (f) => path.join(__dirname, "assets", f);
const OUT = path.join(__dirname, "SonicVitals_Final.pptx");

const THEME = {
  name: "SonicVitals",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "0B2A21", lt1: "FFFFFF", dk2: "0F6A4A", lt2: "EAF4EE",
    accent1: "0F6A4A", accent2: "2BB673", accent3: "D9534F", accent4: "E89B2F",
    accent5: "3D5A50", accent6: "A8D5BA", hlink: "0F6A4A", folHlink: "3D5A50",
  },
};
const HEX = THEME.colors;

async function icon(name, color = "FFFFFF") {
  const svg = ReactDOMServer.renderToStaticMarkup(React.createElement(fa[name], { color: "#" + color, size: 256 }));
  const buf = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}

(async () => {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
  pres.title = "SonicVitals";
  pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
  const C = pres.SchemeColor;

  // ------------------------------------------------------------- layouts
  pres.defineSlideMaster({
    title: "TITLE_DARK",
    background: { color: C.text1 },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.7, y: 2.0, w: 6.2, h: 1.3, fontSize: 54, bold: true, color: C.background1, valign: "bottom", align: "left", margin: 0 }, text: "" } },
      { placeholder: { options: { name: "body", type: "body", x: 0.7, y: 3.45, w: 6.0, h: 1.3, fontSize: 20, color: C.accent6, valign: "top", align: "left", margin: 0 }, text: "" } },
    ],
  });
  pres.defineSlideMaster({
    title: "CONTENT",
    background: { color: C.background1 },
    margin: [0.5, 0.6, 0.6, 0.6],
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.35, w: 12.1, h: 0.85, fontSize: 34, bold: true, color: C.text1, valign: "middle", align: "left", margin: 0 }, text: "" } },
      { text: { text: "SonicVitals", options: { x: 0.6, y: 7.0, w: 3, h: 0.3, fontSize: 10, color: C.accent5, margin: 0 } } },
    ],
    slideNumber: { x: 12.2, y: 7.0, w: 0.5, h: 0.3, fontSize: 10, color: C.accent5, align: "right" },
  });
  pres.defineSlideMaster({
    title: "CLOSING_DARK",
    background: { color: C.text1 },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.7, y: 0.6, w: 11.9, h: 0.9, fontSize: 40, bold: true, color: C.background1, align: "left", margin: 0 }, text: "" } },
    ],
  });

  // helpers ------------------------------------------------------------
  const card = (s, x, y, w, h, opts = {}) =>
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x, y, w, h, rectRadius: 0.12, fill: { color: opts.fill || C.background2 },
      line: { color: opts.line || opts.fill || C.background2, width: 0.75 }, objectName: opts.name,
    });
  const circleIcon = async (s, name, x, y, d, fill = C.accent1) => {
    s.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fill }, line: { color: fill } });
    s.addImage({ data: await icon(name), x: x + d * 0.24, y: y + d * 0.24, w: d * 0.52, h: d * 0.52 });
  };
  const text = (s, t, o) => s.addText(t, { isTextBox: true, margin: 0, valign: "top", ...o });
  const arrow = (s, x1, y1, x2, y2, o = {}) =>
    s.addShape(pres.shapes.LINE, {
      x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1), h: Math.abs(y2 - y1),
      flipH: x2 < x1, line: { color: o.color || C.accent5, width: 2, endArrowType: "triangle", dashType: o.dash || "solid" },
    });

  // =========================================================== 1 Title
  pres.addSection({ title: "Introduction" });
  let s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "Introduction" });
  s.addText("SonicVitals", { placeholder: "title" });
  s.addText("Contactless heart-rate and breathing monitoring with a low-cost camera + microphone node", { placeholder: "body" });
  text(s, "ESP32-S3  ·  rPPG  ·  Heart sounds  ·  Sensor fusion", { x: 0.7, y: 5.0, w: 6.0, h: 0.4, fontSize: 16, color: C.background1 });
  text(s, "SEM 5 Project  ·  VIT  ·  October 2026", { x: 0.7, y: 5.5, w: 6.0, h: 0.4, fontSize: 14, color: C.accent6 });
  card(s, 7.25, 2.2, 5.55, 2.95, { fill: C.background1 });
  s.addImage({ path: A("setup.png"), x: 7.4, y: 2.42, w: 5.25, h: 5.25 / 2.093 });
  s.addNotes("Introduce the project in one line: we measure heart rate and breathing without touching the person, using a cheap ESP32 node with a camera and a microphone. The photo is the actual prototype: ESP32-S3 with GC2145 camera, INMP441 MEMS microphones and an OLED display.");

  // =========================================================== 2 Problem
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Introduction" });
  s.addText("Some people can't wear a sensor", { placeholder: "title" });
  const needs = [
    ["FaBed", "Elderly and bedridden patients", "People with dementia pull clips and straps off; nobody re-attaches them at night."],
    ["FaBaby", "Fragile skin", "Newborns and burn patients: adhesive sensors can injure the skin."],
    ["FaUsers", "Shared screening", "Health rooms and kiosks: quick checks for many people without a shared finger clip."],
  ];
  for (let i = 0; i < needs.length; i++) {
    const y = 1.5 + i * 1.45;
    await circleIcon(s, needs[i][0], 0.6, y, 0.75);
    text(s, needs[i][1], { x: 1.6, y: y - 0.02, w: 4.6, h: 0.4, fontSize: 18, bold: true, color: C.text1 });
    text(s, needs[i][2], { x: 1.6, y: y + 0.4, w: 4.6, h: 0.85, fontSize: 14, color: C.accent5 });
  }
  text(s, "What already exists", { x: 6.75, y: 1.45, w: 6, h: 0.4, fontSize: 18, bold: true, color: C.text1 });
  const hdr = { bold: true, color: C.background1, fill: { color: C.accent1 } };
  const rows = [
    [{ text: "Option", options: hdr }, { text: "Cost", options: hdr }, { text: "Limitation", options: hdr }],
    ["Finger pulse oximeter", "₹500–1,500", "Needs contact"],
    ["Smartwatch / band", "₹2,000+", "Must be worn and charged"],
    ["Face-scan phone apps", "App / licence", "Closed; someone holds the phone"],
    ["Radar / under-mattress", "₹10,000+", "Single purpose, closed"],
  ];
  s.addTable(rows, {
    x: 6.75, y: 1.95, w: 5.95, colW: [2.3, 1.35, 2.3], fontSize: 14, color: C.text1, valign: "middle",
    rowH: 0.52, border: { type: "solid", pt: 0.75, color: "D5E5DC" }, fill: { color: C.background1 },
  });
  card(s, 0.6, 5.85, 12.1, 0.85, { fill: C.background2 });
  text(s, [
    { text: "The gap: ", options: { bold: true, color: C.accent1 } },
    { text: "a cheap, open, fixed node that measures without contact and says when its reading can't be trusted.", options: { color: C.text1 } },
  ], { x: 0.85, y: 5.85, w: 11.6, h: 0.85, fontSize: 18, valign: "middle" });
  s.addNotes("Be honest: for one healthy person a ₹800 oximeter is better. Contactless matters when contact is the problem: people who won't or can't wear sensors, fragile skin, and shared screening. Existing contactless options are closed phone apps or expensive radar devices.");

  // =========================================================== 3 What we built
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Introduction" });
  s.addText("What we built", { placeholder: "title" });
  const built = [
    ["FaMicrochip", "Low-cost sensor node", "ESP32-S3 + GC2145 camera + INMP441 microphone + OLED, about ₹1,500 of parts, streaming over Wi-Fi."],
    ["FaClock", "Two sensors, one clock", "Every frame and audio block carries a microsecond timestamp from the same ESP32 clock, so camera and sound line up."],
    ["FaBalanceScale", "Fusion with an agreement check", "Camera HR and heart-sound HR are averaged by quality only if they agree within 8 BPM."],
    ["FaShieldAlt", "Honest quality gating", "A reading is shown only if its signal clearly beats noise; otherwise the display shows \"--\"."],
  ];
  for (let i = 0; i < 4; i++) {
    const x = 0.6 + (i % 2) * 6.15, y = 1.55 + Math.floor(i / 2) * 2.6;
    card(s, x, y, 5.95, 2.35, { fill: C.background2 });
    await circleIcon(s, built[i][0], x + 0.35, y + 0.35, 0.8);
    text(s, built[i][1], { x: x + 1.4, y: y + 0.4, w: 4.3, h: 0.5, fontSize: 20, bold: true, color: C.text1 });
    text(s, built[i][2], { x: x + 1.4, y: y + 0.95, w: 4.3, h: 1.3, fontSize: 17, color: C.accent5 });
  }
  s.addNotes("Four contributions. The algorithms themselves are published (CHROM, Welch, PCG envelopes); our contribution is the integration: a cheap synchronised two-sensor node, fusion with an agreement gate, and quality gating that refuses to show noise.");

  // =========================================================== 4 Architecture
  pres.addSection({ title: "System" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "System" });
  s.addText("System architecture", { placeholder: "title" });
  // node panel
  card(s, 0.6, 1.45, 4.1, 5.3, { fill: C.background2 });
  text(s, "EDGE NODE · ESP32-S3", { x: 0.85, y: 1.6, w: 3.6, h: 0.35, fontSize: 14, bold: true, color: C.accent1 });
  const nodeCards = [
    ["FaCamera", "Camera task (core 1)", "GC2145 · 8 fps fixed rate\nsoftware JPEG · 3 s PSRAM ring"],
    ["FaMicrophone", "Audio task (core 0)", "INMP441 I²S 16 kHz\n63-tap FIR → 4 kHz"],
    ["FaDesktop", "SSD1306 OLED", "HR · RR · status · IP"],
  ];
  for (let i = 0; i < 3; i++) {
    const y = 2.1 + i * 1.3;
    card(s, 0.8, y, 3.7, 1.1, { fill: C.background1 });
    await circleIcon(s, nodeCards[i][0], 0.95, y + 0.25, 0.6);
    text(s, nodeCards[i][1], { x: 1.7, y: y + 0.12, w: 2.7, h: 0.35, fontSize: 14, bold: true, color: C.text1 });
    text(s, nodeCards[i][2], { x: 1.7, y: y + 0.47, w: 2.7, h: 0.6, fontSize: 12, color: C.accent5 });
  }
  text(s, "Each packet: µs timestamp + sequence no.", { x: 0.85, y: 6.1, w: 3.6, h: 0.5, fontSize: 12, italic: true, color: C.accent5 });
  // host panel
  card(s, 5.95, 1.45, 4.1, 5.3, { fill: C.background2 });
  text(s, "HOST · Python (Flask, OpenCV, SciPy)", { x: 6.2, y: 1.6, w: 3.7, h: 0.35, fontSize: 14, bold: true, color: C.accent1 });
  const hostCards = [
    ["Optical rPPG engine", "face gate · CHROM · Welch spectrum"],
    ["Acoustic PCG engine", "Shannon envelope · autocorrelation"],
    ["Fusion + quality gates", "agree ≤ 8 BPM · SNR ≥ 0 dB"],
    ["Session recorder", "CSV + WAV for offline evaluation"],
  ];
  for (let i = 0; i < 4; i++) {
    const y = 2.1 + i * 1.12;
    card(s, 6.15, y, 3.7, 0.95, { fill: C.background1 });
    text(s, hostCards[i][0], { x: 6.35, y: y + 0.1, w: 3.4, h: 0.35, fontSize: 14, bold: true, color: C.text1 });
    text(s, hostCards[i][1], { x: 6.35, y: y + 0.48, w: 3.4, h: 0.35, fontSize: 12, color: C.accent5 });
  }
  // client
  card(s, 11.0, 2.1, 1.7, 2.5, { fill: C.accent1 });
  await circleIcon(s, "FaDesktop", 11.5, 2.35, 0.7, C.accent2);
  text(s, "Web dashboard", { x: 11.1, y: 3.2, w: 1.5, h: 0.4, fontSize: 14, bold: true, color: C.background1, align: "center" });
  text(s, "video · vitals · waveforms · diagnostics", { x: 11.1, y: 3.6, w: 1.5, h: 0.9, fontSize: 11, color: C.accent6, align: "center" });
  // arrows
  arrow(s, 4.7, 2.75, 5.95, 2.75);
  text(s, "Wi-Fi TCP :3333", { x: 4.75, y: 2.3, w: 1.15, h: 0.4, fontSize: 11, bold: true, color: C.accent5, align: "center" });
  text(s, "video + audio", { x: 4.75, y: 2.83, w: 1.15, h: 0.3, fontSize: 11, color: C.accent5, align: "center" });
  arrow(s, 5.95, 4.95, 4.7, 4.95, { dash: "dash", color: C.accent2 });
  text(s, "VITALS every 1.5 s", { x: 4.75, y: 5.03, w: 1.15, h: 0.5, fontSize: 11, color: C.accent1, align: "center" });
  arrow(s, 10.05, 3.35, 11.0, 3.35);
  text(s, "HTTP JSON + MJPEG", { x: 10.05, y: 3.45, w: 0.95, h: 0.6, fontSize: 10, color: C.accent5, align: "center" });
  s.addNotes("Three parts. The node captures at a fixed 8 fps on core 1 and audio on core 0, timestamps everything with the same clock and streams over Wi-Fi TCP. The host does all signal processing in Python and serves the dashboard; it also sends the result back to the OLED every 1.5 s.");

  // =========================================================== 5 Hardware decisions
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "System" });
  s.addText("Engineering the node: problems we hit", { placeholder: "title" });
  s.addImage({ path: A("setup.png"), x: 0.6, y: 1.55, w: 6.2, h: 6.2 / 2.093 });
  card(s, 0.6, 4.85, 6.2, 1.75, { fill: C.background2 });
  text(s, [
    { text: "ESP32-S3: ", options: { bold: true } }, { text: "2 cores at 240 MHz, 8 MB PSRAM, Wi-Fi", options: { breakLine: true } },
    { text: "GC2145: ", options: { bold: true } }, { text: "2 MP camera, used at 240×160", options: { breakLine: true } },
    { text: "INMP441: ", options: { bold: true } }, { text: "24-bit I²S MEMS microphone", options: { breakLine: true } },
    { text: "SSD1306: ", options: { bold: true } }, { text: "128×64 OLED over I²C", options: {} },
  ], { x: 0.85, y: 5.0, w: 5.8, h: 1.5, fontSize: 15, color: C.text1, paraSpaceAfter: 4, valign: "middle" });
  const fixes = [
    ["FaPlug", "Mic pins = USB-serial pins", "GPIO43/44 carry both → stream over Wi-Fi instead"],
    ["FaImage", "No hardware JPEG on GC2145", "Capture RGB565, compress in software, fixed 8 fps"],
    ["FaSun", "Auto-exposure hides the pulse", "Lock exposure, gain, white balance after 3 s"],
    ["FaWifi", "Hotspot gives only ~70 kB/s", "Audio 16 → 4 kHz (FIR), 3 s PSRAM frame buffer"],
  ];
  for (let i = 0; i < 4; i++) {
    const y = 1.55 + i * 1.3;
    await circleIcon(s, fixes[i][0], 7.2, y + 0.1, 0.7, i % 2 ? C.accent5 : C.accent1);
    text(s, fixes[i][1], { x: 8.1, y: y + 0.05, w: 4.6, h: 0.4, fontSize: 16, bold: true, color: C.text1 });
    text(s, fixes[i][2], { x: 8.1, y: y + 0.47, w: 4.6, h: 0.6, fontSize: 14, color: C.accent5 });
  }
  s.addNotes("Real problems from building it. The mic's I2S pins were the USB-serial pins, so USB streaming died with the mic on: we moved to Wi-Fi. The GC2145 has no JPEG encoder, so we compress in software at a fixed 8 fps. Auto-exposure changes are bigger than the 0.1-1% pulse, so we lock them. Bandwidth forced audio decimation and a PSRAM buffer.");

  // =========================================================== 6 Signal processing
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "System" });
  s.addText("From pixels and sound to heart rate", { placeholder: "title" });
  const W = 1.85, G = 0.2, X0 = 0.6;
  const row = (y, label, steps, fills) => {
    text(s, label, { x: X0, y, w: 6, h: 0.35, fontSize: 14, bold: true, color: C.accent1 });
    steps.forEach((st, i) => {
      if (!st[0]) return;
      const x = X0 + i * (W + G);
      card(s, x, y + 0.4, W, 1.15, { fill: fills[i] || C.background2 });
      text(s, st[0], { x: x + 0.12, y: y + 0.5, w: W - 0.24, h: 0.4, fontSize: 14, bold: true, color: fills[i] ? C.background1 : C.text1 });
      text(s, st[1], { x: x + 0.12, y: y + 0.9, w: W - 0.24, h: 0.62, fontSize: 11, color: fills[i] ? C.accent6 : C.accent5 });
      if (i < steps.length - 1 && steps[i + 1][0]) arrow(s, x + W + 0.01, y + 0.97, x + W + G - 0.01, y + 0.97);
    });
  };
  row(1.4, "OPTICAL · camera", [
    ["Face gate", "Haar cascade + 5 checks"], ["Skin colour", "forehead + cheeks mean R,G,B"],
    ["Resample", "timestamps → 15 Hz grid"], ["CHROM", "S = X − αY cancels motion"],
    ["Band-pass", "0.75–2.5 Hz (45–150 BPM)"], ["HR", "Welch peak, tracked\nshown if SNR ≥ 0 dB"],
  ], [null, null, null, null, null, C.accent1]);
  row(3.15, "ACOUSTIC · chest microphone", [
    ["Band-pass", "25–400 Hz heart sounds"], ["Resample", "1 kHz"], ["Envelope", "Shannon energy −x² log x²"],
    ["HR", "autocorrelation, 60/τ\nshown if ρ ≥ 0.3"], ["", ""], ["Breathing", "camera green 0.15–0.40 Hz → RR"],
  ], [null, null, null, C.accent1, null, C.accent5]);
  card(s, 0.6, 5.2, 12.1, 1.5, { fill: C.background2 });
  await circleIcon(s, "FaBalanceScale", 0.85, 5.55, 0.8);
  text(s, "Fusion", { x: 1.9, y: 5.35, w: 10.5, h: 0.4, fontSize: 18, bold: true, color: C.text1 });
  text(s, "If camera and sound agree within 8 BPM: HR = (w_cam·HR_cam + w_snd·HR_snd) / (w_cam + w_snd), weighted by signal quality. If they disagree, use the better channel and flag a conflict. Brief disturbances (≤ 2 s) are bridged; longer ones hold the last value for 15 s.", { x: 1.9, y: 5.75, w: 10.6, h: 0.9, fontSize: 14, color: C.accent5 });
  s.addNotes("Camera: each heartbeat changes skin colour by 0.1-1%. We average thousands of skin pixels, put samples on a uniform time grid, use CHROM to cancel motion and lighting, band-pass to the heart-rate range and pick the Welch spectral peak. Sound: band-pass the heart sounds, take the Shannon energy envelope and find its period by autocorrelation. Each channel has a quality gate; fusion averages them only when they agree.");

  // =========================================================== 7 Dashboard
  pres.addSection({ title: "Results" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Results" });
  s.addText("The live dashboard", { placeholder: "title" });
  s.addImage({ path: A("dash_video.png"), x: 0.6, y: 1.45, w: 4.4, h: 4.4 / 1.186 });
  s.addImage({ path: A("dash_bvp.png"), x: 0.6, y: 5.3, w: 4.4, h: 4.4 / 3.18 });
  s.addImage({ path: A("psd.png"), x: 5.45, y: 1.45, w: 7.25, h: 7.25 / 2.271 });
  const notes7 = [
    ["1", "Face gate + skin ROI", "Green box = face passed all 5 checks; yellow = skin patch used for the pulse."],
    ["2", "Recovered pulse wave", "Band-passed CHROM signal; each hump is one heartbeat."],
    ["3", "Pulse spectrum", "Highest peak in 0.75–2.5 Hz gives HR = 60 × f₀."],
  ];
  notes7.forEach((n, i) => {
    const x = 5.45 + i * 2.5;
    card(s, x, 4.85, 2.3, 1.85, { fill: C.background2 });
    s.addShape(pres.shapes.OVAL, { x: x + 0.15, y: 5.0, w: 0.42, h: 0.42, fill: { color: C.accent3 }, line: { color: C.accent3 } });
    text(s, n[0], { x: x + 0.15, y: 5.0, w: 0.42, h: 0.42, fontSize: 14, bold: true, color: C.background1, align: "center", valign: "middle" });
    text(s, n[1], { x: x + 0.65, y: 5.0, w: 1.55, h: 0.45, fontSize: 13, bold: true, color: C.text1, valign: "middle" });
    text(s, n[2], { x: x + 0.15, y: 5.55, w: 2.0, h: 1.1, fontSize: 12, color: C.accent5 });
  });
  s.addNotes("Screenshots from the prototype. Left: the camera view with the face box and the skin region, and the recovered pulse waveform. Right: the pulse spectrum; the highest peak in the heart-rate band gives HR. These screenshots are from an earlier build; the current one also shows SNR and displays '--' when the signal is weak. Best: show the live demo here.");

  // =========================================================== 8 Results
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Results" });
  s.addText("What we measured", { placeholder: "title" });
  // Bar chart drawn with shapes so it renders in both PowerPoint and Keynote.
  card(s, 0.6, 1.45, 6.4, 5.25, { fill: C.background2 });
  text(s, "Frame-timing jitter (SD) — lower is better", { x: 0.85, y: 1.65, w: 6.0, h: 0.4, fontSize: 16, bold: true, color: C.text1 });
  const bars = [["Wi-Fi, first firmware", 310, C.accent5], ["USB-serial 1 Mbaud (mic off)", 15.5, C.accent5], ["Wi-Fi, fixed-rate capture", 0.4, C.accent2]];
  bars.forEach(([lab, v, col], i) => {
    const y = 2.4 + i * 1.05;
    text(s, lab, { x: 0.85, y, w: 5.9, h: 0.3, fontSize: 13, color: C.text1 });
    const bw = Math.max(0.05, 4.6 * v / 310);
    s.addShape(pres.shapes.RECTANGLE, { x: 0.85, y: y + 0.35, w: bw, h: 0.42, fill: { color: col }, line: { color: col } });
    text(s, (v < 1 ? v.toFixed(1) : String(v)) + " ms", { x: 0.85 + bw + 0.12, y: y + 0.35, w: 1.2, h: 0.42, fontSize: 15, bold: true, color: C.text1, valign: "middle" });
  });
  text(s, [
    { text: "775× steadier ", options: { bold: true, color: C.accent1 } },
    { text: "after moving capture into a fixed-rate camera task with timestamps taken at capture.", options: { color: C.accent5 } },
  ], { x: 0.85, y: 5.65, w: 5.9, h: 0.85, fontSize: 14 });
  const stats = [
    ["8.0", "frames / s received", "evenly spaced, Wi-Fi"],
    ["0", "frames or audio blocks lost", "30 s run, checked by sequence no."],
    ["±2 BPM", "HR on synthetic signals", "at 52, 78 and 128 BPM"],
    ["≈5 %", "noise passing the gate", "pure-noise test, so \"--\" not fake HR"],
  ];
  stats.forEach((st, i) => {
    const x = 7.3 + (i % 2) * 2.75, y = 1.45 + Math.floor(i / 2) * 2.15;
    card(s, x, y, 2.6, 1.95, { fill: C.background2 });
    text(s, st[0], { x: x + 0.2, y: y + 0.15, w: 2.2, h: 0.75, fontSize: 36, bold: true, color: C.accent1, fontFace: "Cambria" });
    text(s, st[1], { x: x + 0.2, y: y + 0.92, w: 2.25, h: 0.5, fontSize: 13, bold: true, color: C.text1 });
    text(s, st[2], { x: x + 0.2, y: y + 1.4, w: 2.25, h: 0.5, fontSize: 11, color: C.accent5 });
  });
  card(s, 7.3, 5.85, 5.35, 0.85, { fill: C.background1, line: C.accent4 });
  text(s, [
    { text: "Not yet measured: ", options: { bold: true, color: C.accent4 } },
    { text: "HR accuracy against an ECG chest strap (planned study).", options: { color: C.text1 } },
  ], { x: 7.5, y: 5.85, w: 5.0, h: 0.85, fontSize: 14, valign: "middle" });
  s.addNotes("Engineering results we actually measured. Timing jitter fell from 310 ms with the first Wi-Fi firmware to 0.4 ms after moving capture into a fixed-rate task. 30 s run: 8.0 fps, no lost frames or audio. 31 automated tests: synthetic HR within 2 BPM; pure noise passes the quality gate about 5% of the time. Gap bridging cut buffer restarts from 16 to 6 on a recorded session. Clinical accuracy against an ECG strap is the next step; we do not claim a number we haven't measured.");

  // =========================================================== 9 Limitations
  pres.addSection({ title: "Conclusion" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Conclusion" });
  s.addText("Limitations and next steps", { placeholder: "title" });
  const lim = [
    ["FaVial", "No reference validation yet", "Compare with an ECG chest strap: Bland–Altman, AAMI ±5 BPM"],
    ["FaMoon", "Needs light", "Add an IR LED + IR-sensitive camera for night monitoring"],
    ["FaRunning", "Motion and lighting changes", "Landmark face tracking; colour means computed on the node before JPEG"],
    ["FaStethoscope", "Heart sounds weak through air", "Contact or stethoscope-coupled microphone on the chest"],
    ["FaPalette", "Colour indices uncalibrated", "Colour reference card and fixed lighting; exploratory only"],
  ];
  text(s, "LIMITATION", { x: 1.6, y: 1.4, w: 4.5, h: 0.3, fontSize: 12, bold: true, color: C.accent3 });
  text(s, "NEXT STEP", { x: 6.9, y: 1.4, w: 5.5, h: 0.3, fontSize: 12, bold: true, color: C.accent1 });
  for (let i = 0; i < lim.length; i++) {
    const y = 1.8 + i * 1.0;
    await circleIcon(s, lim[i][0], 0.6, y + 0.05, 0.7, C.accent5);
    text(s, lim[i][1], { x: 1.6, y: y + 0.05, w: 4.4, h: 0.7, fontSize: 16, bold: true, color: C.text1, valign: "middle" });
    arrow(s, 6.1, y + 0.4, 6.7, y + 0.4, { color: C.accent2 });
    text(s, lim[i][2], { x: 6.9, y: y + 0.05, w: 5.8, h: 0.7, fontSize: 15, color: C.accent5, valign: "middle" });
  }
  s.addNotes("Say the limitations before the examiners do. The biggest is that HR accuracy hasn't been validated against a reference yet. An ordinary camera needs light, so bedside night use needs IR. Motion, lighting and weak heart sounds through air are the other limits. Each has a concrete next step.");

  // =========================================================== 10 Conclusion
  s = pres.addSlide({ masterName: "CLOSING_DARK", sectionTitle: "Conclusion" });
  s.addText("Takeaways", { placeholder: "title" });
  const take = [
    ["FaHeartbeat", "Contactless HR and breathing from a ≈₹1,500 open node, with no phone or wearable."],
    ["FaClock", "Camera and heart-sound data on one clock, fused only when the two agree."],
    ["FaShieldAlt", "Quality gates show \"--\" instead of a confident wrong number."],
  ];
  for (let i = 0; i < 3; i++) {
    const y = 1.85 + i * 1.15;
    await circleIcon(s, take[i][0], 0.7, y, 0.75, C.accent1);
    text(s, take[i][1], { x: 1.75, y: y + 0.12, w: 10.5, h: 0.6, fontSize: 20, color: C.background1, valign: "middle" });
  }
  text(s, "Thank you  ·  Questions?", { x: 0.7, y: 5.6, w: 11.9, h: 0.9, fontSize: 36, bold: true, color: C.accent2, fontFace: "Cambria" });
  s.addNotes("Close with the three takeaways and invite questions. If there is time, run the live demo.");

  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
})();
