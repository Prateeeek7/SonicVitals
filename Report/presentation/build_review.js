// Builds SonicVitals_Final_Review.pptx (academic final-review format).
// Run: NODE_PATH=<dir with pptxgenjs> PPTX_SKILL=<pptx skill dir> node build_review.js
const path = require("path");
const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const fa = require("react-icons/fa");
const { applyTheme } = require(process.env.PPTX_SKILL + "/scripts/apply_theme.js");

const A = (f) => path.join(__dirname, "assets", f);
const OUT = path.join(__dirname, "SonicVitals_Final_Review.pptx");

const TITLE = "SonicVitals: A Low-Cost ESP32-S3 Platform for Synchronized Camera-Based Photoplethysmography and Acoustic Cardiac Sensing";
const TEAM = ["Pratik Kumar", "Uday Krishan Khandelwal", "Janvhee Dhote"];
const GUIDE = "Jeeva J. B.";
const SCHOOL = "School of Electronics Engineering (SENSE), Vellore Institute of Technology, Vellore";

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

async function icon(name, color = "FFFFFF") {
  const svg = ReactDOMServer.renderToStaticMarkup(React.createElement(fa[name], { color: "#" + color, size: 256 }));
  const buf = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}

(async () => {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
  pres.title = "SonicVitals Final Review";
  pres.author = TEAM.join(", ");
  pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
  const C = pres.SchemeColor;

  // ------------------------------------------------------------- layouts
  pres.defineSlideMaster({
    title: "TITLE_DARK",
    background: { color: C.text1 },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.7, y: 1.05, w: 7.0, h: 2.1, fontSize: 30, bold: true, color: C.background1, valign: "bottom", align: "left", margin: 0 }, text: "" } },
    ],
  });
  pres.defineSlideMaster({
    title: "CONTENT",
    background: { color: C.background1 },
    margin: [0.5, 0.6, 0.6, 0.6],
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.3, w: 12.1, h: 0.85, fontSize: 32, bold: true, color: C.text1, valign: "middle", align: "left", margin: 0 }, text: "" } },
      { text: { text: "SonicVitals · Final Review · SENSE, VIT Vellore", options: { x: 0.6, y: 7.02, w: 6, h: 0.3, fontSize: 10, color: C.accent5, margin: 0 } } },
    ],
    slideNumber: { x: 12.2, y: 7.0, w: 0.5, h: 0.3, fontSize: 10, color: C.accent5, align: "right" },
  });
  pres.defineSlideMaster({
    title: "CLOSING_DARK",
    background: { color: C.text1 },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.7, y: 0.55, w: 11.9, h: 0.9, fontSize: 36, bold: true, color: C.background1, align: "left", margin: 0 }, text: "" } },
    ],
  });

  // helpers ------------------------------------------------------------
  const card = (s, x, y, w, h, opts = {}) =>
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x, y, w, h, rectRadius: 0.1, fill: { color: opts.fill || C.background2 },
      line: { color: opts.line || opts.fill || C.background2, width: 0.75 },
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
  const bullets = (items, o = {}) => items.map((t, i) => ({
    text: t, options: { bullet: true, breakLine: i < items.length - 1, paraSpaceAfter: o.gap || 6 },
  }));
  const HDR = { bold: true, color: C.background1, fill: { color: C.accent1 } };
  const table = (s, head, rows, o) => s.addTable(
    [head.map((h) => ({ text: h, options: HDR })), ...rows],
    { fontSize: 12, color: C.text1, valign: "middle", border: { type: "solid", pt: 0.75, color: "D5E5DC" }, fill: { color: C.background1 }, margin: 0.06, ...o },
  );
  const content = (title, section) => {
    const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: section });
    s.addText(title, { placeholder: "title" });
    return s;
  };

  // =========================================================== 1 Title
  pres.addSection({ title: "Introduction" });
  let s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "Introduction" });
  text(s, "FINAL PROJECT REVIEW", { x: 0.7, y: 0.55, w: 7, h: 0.4, fontSize: 14, bold: true, color: C.accent2, charSpacing: 2 });
  s.addText(TITLE, { placeholder: "title" });
  text(s, "Team", { x: 0.7, y: 3.55, w: 3.4, h: 0.35, fontSize: 14, bold: true, color: C.accent6 });
  text(s, TEAM.join("\n"), { x: 0.7, y: 3.9, w: 3.6, h: 1.2, fontSize: 18, color: C.background1, paraSpaceAfter: 2 });
  text(s, "Faculty Guide", { x: 4.4, y: 3.55, w: 3.2, h: 0.35, fontSize: 14, bold: true, color: C.accent6 });
  text(s, GUIDE, { x: 4.4, y: 3.9, w: 3.3, h: 0.45, fontSize: 18, color: C.background1 });
  text(s, SCHOOL + "  ·  October 2026", { x: 0.7, y: 5.5, w: 7.0, h: 0.7, fontSize: 14, color: C.accent6 });
  card(s, 8.05, 1.9, 4.75, 2.55, { fill: C.background1 });
  s.addImage({ path: A("setup.png"), x: 8.2, y: 2.08, w: 4.45, h: 4.45 / 2.093 });
  text(s, "Bench prototype: ESP32-S3 + GC2145 camera + INMP441 microphones + SSD1306 OLED", { x: 8.05, y: 4.6, w: 4.75, h: 0.6, fontSize: 12, color: C.accent6 });
  s.addNotes("Introduce the team and the guide. One-line summary: a low-cost ESP32-S3 node that captures camera video and heart sounds on one clock, and a host pipeline that estimates heart rate and breathing without contact.");

  // =========================================================== 2 Outline
  s = content("Outline", "Introduction");
  const outline = ["Introduction", "Problem statement and motivation", "Literature survey", "Research gap and objectives",
    "System architecture", "Hardware and pin mapping", "Firmware design", "Methodology: optical rPPG",
    "Methodology: acoustic, respiration, fusion", "Software and dashboard", "Exploratory colour screening",
    "Results: system performance", "Results: algorithm verification", "Comparison with existing work",
    "Limitations and future work", "Conclusion and references"];
  outline.forEach((t, i) => {
    const col = Math.floor(i / 8), r = i % 8;
    const x = 0.6 + col * 6.15, y = 1.45 + r * 0.66;
    s.addShape(pres.shapes.OVAL, { x, y, w: 0.46, h: 0.46, fill: { color: col ? C.accent5 : C.accent1 }, line: { color: col ? C.accent5 : C.accent1 } });
    text(s, String(i + 1), { x, y, w: 0.46, h: 0.46, fontSize: 13, bold: true, color: C.background1, align: "center", valign: "middle" });
    text(s, t, { x: x + 0.65, y, w: 5.2, h: 0.46, fontSize: 17, color: C.text1, valign: "middle" });
  });
  s.addNotes("Walk through the structure briefly.");

  // =========================================================== 3 Introduction
  s = content("Introduction", "Introduction");
  text(s, bullets([
    "Heart rate (HR) and respiratory rate (RR) are the most frequently recorded vital signs.",
    "They are normally measured with contact sensors: ECG electrodes, finger PPG clips, chest belts.",
    "Contact sensing is reliable, but uncomfortable for long recordings, unsuitable for fragile or burned skin, and a cross-infection risk.",
    "This motivates contactless measurement using a camera and sound.",
  ], { gap: 10 }), { x: 0.6, y: 1.45, w: 6.0, h: 3.6, fontSize: 16, color: C.text1 });
  const concepts = [
    ["FaCamera", "Remote photoplethysmography (rPPG)", "Each heartbeat pushes blood into skin capillaries; haemoglobin absorbs green light, so skin colour changes by 0.1–1 %. Averaging thousands of skin pixels in video recovers the pulse."],
    ["FaStethoscope", "Phonocardiography (PCG)", "Heart valves closing produce the S1 (\"lub\") and S2 (\"dub\") sounds at 20–150 Hz; their period gives the heart rate."],
    ["FaBalanceScale", "Why combine both", "Camera and sound fail for different physical reasons (motion and light vs. noise), so they can check each other."],
  ];
  for (let i = 0; i < 3; i++) {
    const y = 1.45 + i * 1.8;
    card(s, 6.95, y, 5.75, 1.6, { fill: C.background2 });
    await circleIcon(s, concepts[i][0], 7.15, y + 0.25, 0.7);
    text(s, concepts[i][1], { x: 8.05, y: y + 0.15, w: 4.5, h: 0.35, fontSize: 15, bold: true, color: C.text1 });
    text(s, concepts[i][2], { x: 8.05, y: y + 0.52, w: 4.5, h: 1.05, fontSize: 12, color: C.accent5 });
  }
  card(s, 0.6, 5.35, 6.0, 1.35, { fill: C.accent1 });
  text(s, [
    { text: "Key idea: ", options: { bold: true, color: C.background1 } },
    { text: "one cheap node captures both signals on the same clock, and the host estimates and cross-checks the vital signs.", options: { color: C.accent6 } },
  ], { x: 0.85, y: 5.35, w: 5.55, h: 1.35, fontSize: 16, valign: "middle" });
  s.addNotes("Explain rPPG and PCG in one sentence each, and why combining them helps: they fail for different reasons.");

  // =========================================================== 4 Problem statement
  s = content("Problem statement and motivation", "Introduction");
  card(s, 0.6, 1.4, 12.1, 1.0, { fill: C.background2 });
  text(s, [
    { text: "Problem: ", options: { bold: true, color: C.accent1 } },
    { text: "Monitor HR and RR without touching the person, using low-cost hardware, and know when a reading cannot be trusted.", options: { color: C.text1 } },
  ], { x: 0.85, y: 1.4, w: 11.6, h: 1.0, fontSize: 18, valign: "middle" });
  const needs = [
    ["FaBed", "Elderly and bedridden", "People with dementia pull clips and straps off."],
    ["FaBaby", "Fragile skin", "Newborns and burn patients: adhesive sensors can injure skin."],
    ["FaUsers", "Shared screening", "Health rooms and kiosks without a shared finger clip."],
  ];
  text(s, "Who needs contactless monitoring", { x: 0.6, y: 2.7, w: 5.5, h: 0.4, fontSize: 16, bold: true, color: C.text1 });
  for (let i = 0; i < 3; i++) {
    const y = 3.2 + i * 1.15;
    await circleIcon(s, needs[i][0], 0.6, y, 0.65);
    text(s, needs[i][1], { x: 1.45, y: y - 0.03, w: 4.6, h: 0.35, fontSize: 15, bold: true, color: C.text1 });
    text(s, needs[i][2], { x: 1.45, y: y + 0.33, w: 4.6, h: 0.6, fontSize: 13, color: C.accent5 });
  }
  text(s, "What exists today", { x: 6.75, y: 2.7, w: 6, h: 0.4, fontSize: 16, bold: true, color: C.text1 });
  table(s, ["Option", "Cost", "Limitation"], [
    ["Finger pulse oximeter", "₹500–1,500", "Needs contact"],
    ["Smartwatch / band", "₹2,000+", "Must be worn and charged"],
    ["Face-scan phone apps", "App / licence", "Closed; someone holds the phone"],
    ["Radar / under-mattress", "₹10,000+", "Single purpose, closed"],
  ], { x: 6.75, y: 3.2, w: 5.95, colW: [2.3, 1.35, 2.3], rowH: 0.62, fontSize: 13 });
  s.addNotes("Be honest: for one healthy person an oximeter is better. Contactless matters where contact is the problem. Existing contactless options are closed apps or expensive radar devices.");

  // =========================================================== 5 Literature survey
  pres.addSection({ title: "Background" });
  s = content("Literature survey", "Background");
  table(s, ["Work", "Method", "Contribution", "Limitation"], [
    ["Verkruysse et al., 2008", "Green-channel rPPG, ambient light", "First pulse signal from a consumer camera", "Sensitive to motion and light changes"],
    ["Poh et al., 2010", "ICA blind source separation", "Automated webcam HR", "Needs a still subject"],
    ["de Haan & Jeanne, 2013", "CHROM chrominance projection", "Cancels motion/specular component", "Assumes standard skin-tone model"],
    ["Wang et al., 2017", "POS projection", "Unified algorithmic principles of rPPG", "Desktop processing; camera only"],
    ["Chen & McDuff, 2018", "DeepPhys CNN", "Learned motion-robust pulse", "Needs training data and a GPU"],
    ["Villarroel et al., 2019", "Video monitoring in NICU", "Clinical feasibility in neonates", "Costly camera setup"],
    ["Liang 1997; Springer 2016", "Shannon envelope; HSMM", "Robust S1/S2 heart-sound segmentation", "Needs a chest-contact stethoscope"],
    ["Mariakakis et al., 2017", "BiliScreen scleral colour", "Phone-based jaundice screening", "Needs a calibration accessory"],
    ["McDuff 2017; Nowara 2020", "Compression; skin-type meta-analysis", "Compression and darker skin lower rPPG SNR", "Known limits for low-cost cameras"],
  ], { x: 0.6, y: 1.4, w: 12.1, colW: [2.55, 3.0, 3.45, 3.1], rowH: 0.56, fontSize: 12 });
  s.addNotes("Optical methods progressed from green channel to ICA to CHROM/POS to deep learning, all camera-only and mostly desktop. Heart-sound processing assumes a chest stethoscope. Colour screening needs calibration. Compression and skin type limit low-cost cameras.");

  // =========================================================== 6 Gap + objectives
  s = content("Research gap and objectives", "Background");
  text(s, "Research gap", { x: 0.6, y: 1.4, w: 5.5, h: 0.4, fontSize: 18, bold: true, color: C.accent3 });
  text(s, bullets([
    "rPPG systems are camera-only: no independent check when motion or light corrupts the signal.",
    "Multimodal studies use separate devices with unsynchronised clocks, on desktop or GPU platforms.",
    "Few systems report when a reading is unreliable; many display a number regardless.",
    "Little documentation of what a very low-cost embedded camera can and cannot do.",
  ], { gap: 10 }), { x: 0.6, y: 1.9, w: 5.6, h: 4.8, fontSize: 15, color: C.text1 });
  text(s, "Objectives", { x: 6.75, y: 1.4, w: 5.5, h: 0.4, fontSize: 18, bold: true, color: C.accent1 });
  const objs = [
    "Design an ESP32-S3 node that captures video and audio with one microsecond time base.",
    "Stream both reliably to a host over Wi-Fi with integrity checks.",
    "Estimate HR and RR by CHROM rPPG with a face-validity gate.",
    "Estimate HR from heart sounds and fuse both with an agreement gate.",
    "Build a live dashboard with recording and exploratory colour screening.",
    "Verify algorithms and the link quantitatively; define a validation protocol.",
  ];
  objs.forEach((t, i) => {
    const y = 1.9 + i * 0.8;
    s.addShape(pres.shapes.OVAL, { x: 6.75, y, w: 0.45, h: 0.45, fill: { color: C.accent1 }, line: { color: C.accent1 } });
    text(s, String(i + 1), { x: 6.75, y, w: 0.45, h: 0.45, fontSize: 13, bold: true, color: C.background1, align: "center", valign: "middle" });
    text(s, t, { x: 7.35, y: y - 0.05, w: 5.35, h: 0.7, fontSize: 14, color: C.text1, valign: "middle" });
  });
  s.addNotes("The gap: camera-only, unsynchronised multimodal setups, and no reliability reporting. Our six objectives map directly onto the system we built.");

  // =========================================================== 7 Architecture
  pres.addSection({ title: "System design" });
  s = content("Proposed system architecture", "System design");
  card(s, 0.6, 1.35, 4.1, 5.4, { fill: C.background2 });
  text(s, "EDGE NODE · ESP32-S3", { x: 0.85, y: 1.5, w: 3.6, h: 0.35, fontSize: 14, bold: true, color: C.accent1 });
  const nodeCards = [
    ["FaCamera", "Camera task (core 1)", "GC2145 · 8 fps fixed rate\nsoftware JPEG · 3 s PSRAM ring"],
    ["FaMicrophone", "Audio task (core 0)", "INMP441 I²S 16 kHz\n63-tap FIR → 4 kHz"],
    ["FaDesktop", "SSD1306 OLED", "HR · RR · status · IP"],
  ];
  for (let i = 0; i < 3; i++) {
    const y = 2.0 + i * 1.3;
    card(s, 0.8, y, 3.7, 1.1, { fill: C.background1 });
    await circleIcon(s, nodeCards[i][0], 0.95, y + 0.25, 0.6);
    text(s, nodeCards[i][1], { x: 1.7, y: y + 0.12, w: 2.7, h: 0.35, fontSize: 14, bold: true, color: C.text1 });
    text(s, nodeCards[i][2], { x: 1.7, y: y + 0.47, w: 2.7, h: 0.6, fontSize: 12, color: C.accent5 });
  }
  text(s, "Each packet: µs timestamp + sequence no.", { x: 0.85, y: 6.0, w: 3.6, h: 0.5, fontSize: 12, italic: true, color: C.accent5 });
  card(s, 5.95, 1.35, 4.1, 5.4, { fill: C.background2 });
  text(s, "HOST · Python (Flask, OpenCV, SciPy)", { x: 6.2, y: 1.5, w: 3.7, h: 0.35, fontSize: 14, bold: true, color: C.accent1 });
  const hostCards = [
    ["Optical rPPG engine", "face gate · CHROM · Welch spectrum"],
    ["Acoustic PCG engine", "Shannon envelope · autocorrelation"],
    ["Fusion + quality gates", "agree ≤ 8 BPM · SNR ≥ 0 dB"],
    ["Session recorder", "CSV + WAV for offline evaluation"],
  ];
  for (let i = 0; i < 4; i++) {
    const y = 2.0 + i * 1.12;
    card(s, 6.15, y, 3.7, 0.95, { fill: C.background1 });
    text(s, hostCards[i][0], { x: 6.35, y: y + 0.1, w: 3.4, h: 0.35, fontSize: 14, bold: true, color: C.text1 });
    text(s, hostCards[i][1], { x: 6.35, y: y + 0.48, w: 3.4, h: 0.35, fontSize: 12, color: C.accent5 });
  }
  card(s, 11.0, 2.0, 1.7, 2.5, { fill: C.accent1 });
  await circleIcon(s, "FaDesktop", 11.5, 2.25, 0.7, C.accent2);
  text(s, "Web dashboard", { x: 11.1, y: 3.1, w: 1.5, h: 0.4, fontSize: 14, bold: true, color: C.background1, align: "center" });
  text(s, "video · vitals · waveforms · diagnostics", { x: 11.1, y: 3.5, w: 1.5, h: 0.9, fontSize: 11, color: C.accent6, align: "center" });
  arrow(s, 4.7, 2.65, 5.95, 2.65);
  text(s, "Wi-Fi TCP :3333", { x: 4.75, y: 2.2, w: 1.15, h: 0.4, fontSize: 11, bold: true, color: C.accent5, align: "center" });
  text(s, "video + audio", { x: 4.75, y: 2.73, w: 1.15, h: 0.3, fontSize: 11, color: C.accent5, align: "center" });
  arrow(s, 5.95, 4.85, 4.7, 4.85, { dash: "dash", color: C.accent2 });
  text(s, "VITALS every 1.5 s", { x: 4.75, y: 4.93, w: 1.15, h: 0.5, fontSize: 11, color: C.accent1, align: "center" });
  arrow(s, 10.05, 3.25, 11.0, 3.25);
  text(s, "HTTP JSON + MJPEG", { x: 10.05, y: 3.35, w: 0.95, h: 0.6, fontSize: 10, color: C.accent5, align: "center" });
  s.addNotes("Three tiers: node, host, browser. The node timestamps everything with one clock and streams over Wi-Fi TCP; the host processes and serves the dashboard and sends results back to the OLED every 1.5 s.");

  // =========================================================== 8 Hardware + pins
  s = content("Hardware components and pin mapping", "System design");
  table(s, ["Component", "Key specifications", "Role"], [
    ["ESP32-S3 (camera board)", "2 × Xtensa LX7 @ 240 MHz, 512 KB SRAM, 8 MB PSRAM, Wi-Fi", "Acquisition, timestamps, streaming"],
    ["GC2145 camera", "2 MP CMOS, DVP 8-bit, used at 240×160 RGB565", "Facial video for rPPG"],
    ["INMP441 microphone", "I²S MEMS, 24-bit, 61 dBA SNR", "Heart sounds (chest)"],
    ["SSD1306 OLED", "0.96\", 128×64, I²C 400 kHz", "Local readout of vitals and IP"],
    ["Host laptop", "Python 3, Flask, OpenCV, NumPy/SciPy", "Signal processing, dashboard"],
  ], { x: 0.6, y: 1.4, w: 7.3, colW: [2.0, 3.25, 2.05], rowH: 0.66, fontSize: 12 });
  table(s, ["Signal", "GPIO"], [
    ["Camera XCLK / PCLK", "15 / 13"],
    ["Camera VSYNC / HREF", "6 / 7"],
    ["Camera SCCB SDA / SCL", "4 / 5"],
    ["Camera D0–D7", "11, 9, 8, 10, 12, 18, 17, 16"],
    ["Mic I²S SCK / WS / SD", "43 / 44 / 0"],
    ["OLED SDA / SCL (0x3C)", "47 / 48"],
  ], { x: 8.3, y: 1.4, w: 4.4, colW: [2.3, 2.1], rowH: 0.56, fontSize: 12 });
  card(s, 0.6, 5.35, 12.1, 1.35, { fill: C.background2, line: C.accent4 });
  await circleIcon(s, "FaPlug", 0.85, 5.6, 0.8, C.accent4);
  text(s, [
    { text: "Pin conflict found during integration: ", options: { bold: true, color: C.text1 } },
    { text: "the mic's I²S lines (GPIO43/44) are also UART0, wired to the board's only USB-serial chip (CH340). With the mic on, the USB link dies, and GPIO0 is a boot-strapping pin. Solution: stream over Wi-Fi and use USB only for power and flashing.", options: { color: C.accent5 } },
  ], { x: 1.85, y: 5.4, w: 10.6, h: 1.25, fontSize: 14, valign: "middle" });
  s.addNotes("Components and their roles; camera pins follow the ESP32-S3-EYE map. The key hardware finding is the pin conflict between the mic and the USB-serial bridge, which forced Wi-Fi streaming.");

  // =========================================================== 9 Firmware
  s = content("Firmware design", "System design");
  text(s, "FreeRTOS tasks", { x: 0.6, y: 1.4, w: 6, h: 0.4, fontSize: 18, bold: true, color: C.accent1 });
  const tasks = [
    ["Core 0 · audio task", "I²S DMA read → 63-tap FIR anti-alias → decimate 16 → 4 kHz → queue (2 s)"],
    ["Core 1 · camera task", "Capture at fixed 8 fps → software JPEG (q 60) → 24-slot PSRAM ring (≈3 s)"],
    ["Main loop", "Send frames/audio, parse host commands, refresh OLED, OLED hot-plug check"],
  ];
  tasks.forEach((t, i) => {
    const y = 1.9 + i * 0.95;
    card(s, 0.6, y, 6.0, 0.8, { fill: C.background2 });
    text(s, t[0], { x: 0.8, y: y + 0.08, w: 5.6, h: 0.3, fontSize: 14, bold: true, color: C.text1 });
    text(s, t[1], { x: 0.8, y: y + 0.4, w: 5.7, h: 0.35, fontSize: 12, color: C.accent5 });
  });
  text(s, "Line protocol (v2)", { x: 0.6, y: 4.85, w: 6, h: 0.4, fontSize: 18, bold: true, color: C.accent1 });
  card(s, 0.6, 5.3, 6.0, 1.4, { fill: C.text1 });
  text(s, "<<HELLO:SonicVitals,2,wifi,mic,...>>\n<<FRAME_START:seq,t_us,len>> base64 JPEG <<FRAME_END>>\n<<AUDIO:seq,t_us,n,base64 PCM>>\n<<STAT:fps,frames,drops,...>>\nhost → node: <<VITALS:HR,RR,SpO2,Q,STATUS>>",
    { x: 0.8, y: 5.4, w: 5.7, h: 1.25, fontSize: 12, fontFace: "Courier New", color: C.accent6, valign: "middle" });
  text(s, "Engineering problems solved", { x: 7.0, y: 1.4, w: 5.7, h: 0.4, fontSize: 18, bold: true, color: C.accent1 });
  const fixes = [
    ["FaImage", "No hardware JPEG on GC2145", "Driver rejects JPEG mode → capture RGB565, compress in software"],
    ["FaSun", "Auto-exposure hides the pulse", "Lock exposure, gain, white balance after 3 s of settling"],
    ["FaWifi", "Hotspot throughput ≈ 70 kB/s", "8 fps target, audio decimated to 4 kHz, PSRAM buffer for stalls"],
    ["FaClock", "Uneven frame timing", "Fixed-rate capture task; timestamp taken at capture, not on send"],
    ["FaPlug", "Board reset while flashing", "Host never toggles DTR/RTS; Wi-Fi-only link mode"],
  ];
  for (let i = 0; i < fixes.length; i++) {
    const y = 1.9 + i * 0.97;
    await circleIcon(s, fixes[i][0], 7.0, y + 0.05, 0.6, i % 2 ? C.accent5 : C.accent1);
    text(s, fixes[i][1], { x: 7.8, y: y, w: 4.9, h: 0.35, fontSize: 14, bold: true, color: C.text1 });
    text(s, fixes[i][2], { x: 7.8, y: y + 0.36, w: 4.9, h: 0.5, fontSize: 12, color: C.accent5 });
  }
  s.addNotes("Two cores split audio and video so neither blocks the other. The text protocol carries sequence numbers and microsecond timestamps; the length field and sequence numbers detect corrupt or missing data. Five real problems and their fixes.");

  // =========================================================== 10 Optical methodology
  pres.addSection({ title: "Methodology" });
  s = content("Methodology I: optical rPPG", "Methodology");
  const W = 1.85, G = 0.2, X0 = 0.6;
  const steps = [
    ["Face gate", "Haar cascade + 5 checks"], ["Skin colour", "forehead + cheeks mean R,G,B"],
    ["Resample", "timestamps → 15 Hz grid"], ["CHROM", "S = X − αY cancels motion"],
    ["Band-pass", "0.75–2.5 Hz Butterworth, zero-phase"], ["HR", "Welch peak, tracked; shown if SNR ≥ 0 dB"],
  ];
  steps.forEach((st, i) => {
    const x = X0 + i * (W + G), last = i === steps.length - 1;
    card(s, x, 1.4, W, 1.25, { fill: last ? C.accent1 : C.background2 });
    text(s, st[0], { x: x + 0.12, y: 1.5, w: W - 0.24, h: 0.4, fontSize: 14, bold: true, color: last ? C.background1 : C.text1 });
    text(s, st[1], { x: x + 0.12, y: 1.9, w: W - 0.24, h: 0.7, fontSize: 11, color: last ? C.accent6 : C.accent5 });
    if (!last) arrow(s, x + W + 0.01, 2.02, x + W + G - 0.01, 2.02);
  });
  card(s, 0.6, 2.95, 5.9, 3.75, { fill: C.background2 });
  text(s, "CHROM (de Haan & Jeanne, 2013)", { x: 0.85, y: 3.1, w: 5.4, h: 0.4, fontSize: 16, bold: true, color: C.text1 });
  text(s, "Rₙ, Gₙ, Bₙ = channel ÷ its window mean\nX = 3Rₙ − 2Gₙ\nY = 1.5Rₙ + Gₙ − 1.5Bₙ\nS = X − α·Y,   α = σ(X) / σ(Y)\nHR = 60 · f₀  (Welch peak in 0.75–2.5 Hz)",
    { x: 0.85, y: 3.6, w: 5.4, h: 1.9, fontSize: 15, fontFace: "Cambria", color: C.accent1, paraSpaceAfter: 4 });
  text(s, "X and Y both carry the motion/specular term; subtracting αY cancels it and leaves the pulse.", { x: 0.85, y: 5.6, w: 5.4, h: 0.9, fontSize: 13, italic: true, color: C.accent5 });
  card(s, 6.8, 2.95, 5.9, 3.75, { fill: C.background2 });
  text(s, "Parameters and quality control", { x: 7.05, y: 3.1, w: 5.4, h: 0.4, fontSize: 16, bold: true, color: C.text1 });
  text(s, bullets([
    "Face gate: edge clearance, size 20–88 %, aspect 0.65–1.30, ROIs in frame, light ≥ 15 and balanced.",
    "Welch: 256-sample Hann segments, 50 % overlap, FFT 4096, parabolic peak interpolation.",
    "SNR (de Haan): power at f₀ and 2f₀ vs. rest of 0.5–4 Hz; gate 0 dB (noise passes ≈ 5 %).",
    "Warm-up 10 s, buffer 30 s, update 0.5 s; gaps ≤ 2 s bridged.",
    "Peak tracking ±12 BPM around last accepted HR.",
  ], { gap: 5 }), { x: 7.05, y: 3.6, w: 5.45, h: 3.0, fontSize: 13, color: C.text1 });
  s.addNotes("Explain the pipeline left to right, then CHROM. Mention resampling because Wi-Fi frames arrive unevenly, filtfilt for zero phase, Welch for a low-variance spectrum, and the SNR gate that shows '--' instead of noise.");

  // =========================================================== 11 Acoustic + fusion
  s = content("Methodology II: acoustic, respiration and fusion", "Methodology");
  const acs = [["Band-pass", "25–400 Hz, 4th order"], ["Resample", "to 1 kHz"], ["Shannon envelope", "−x² log x², 20 ms smoothing"], ["Autocorrelation", "lag τ in 0.4–1.33 s"], ["HR = 60/τ", "shown if ρ ≥ 0.3"]];
  text(s, "ACOUSTIC · heart sounds", { x: 0.6, y: 1.35, w: 6, h: 0.35, fontSize: 14, bold: true, color: C.accent1 });
  acs.forEach((st, i) => {
    const w = 2.25, x = 0.6 + i * (w + 0.21), last = i === acs.length - 1;
    card(s, x, 1.75, w, 1.0, { fill: last ? C.accent1 : C.background2 });
    text(s, st[0], { x: x + 0.12, y: 1.83, w: w - 0.24, h: 0.35, fontSize: 14, bold: true, color: last ? C.background1 : C.text1 });
    text(s, st[1], { x: x + 0.12, y: 2.2, w: w - 0.24, h: 0.5, fontSize: 12, color: last ? C.accent6 : C.accent5 });
    if (!last) arrow(s, x + w + 0.01, 2.25, x + w + 0.2, 2.25);
  });
  const boxes = [
    ["FaWind", "Respiration (camera)", "Green channel band-passed 0.15–0.40 Hz (9–24 breaths/min); Welch peak f_r → RR = 60·f_r. Needs a 15 s segment and ≥ 50 % of low-frequency power at the peak, else \"--\"."],
    ["FaHeartbeat", "HRV (heart sounds)", "S1 peaks on the Hilbert envelope → inter-beat intervals → RMSSD = √mean(ΔIBI²). Needs ≥ 20 clean intervals."],
    ["FaBalanceScale", "Quality-weighted fusion", "If |HR_cam − HR_snd| ≤ 8 BPM: HR = (w_cam·HR_cam + w_snd·HR_snd)/(w_cam + w_snd), w_cam = Q, w_snd = ρ. Otherwise use the better channel and flag a conflict."],
    ["FaShieldAlt", "Display stabilisation", "Median of last 3 fused values, then EMA; last value held ≤ 15 s while re-acquiring; \"--\" when no channel passes its gate."],
  ];
  for (let i = 0; i < 4; i++) {
    const x = 0.6 + (i % 2) * 6.15, y = 3.05 + Math.floor(i / 2) * 1.85;
    card(s, x, y, 5.95, 1.65, { fill: C.background2 });
    await circleIcon(s, boxes[i][0], x + 0.25, y + 0.3, 0.7);
    text(s, boxes[i][1], { x: x + 1.15, y: y + 0.15, w: 4.6, h: 0.35, fontSize: 15, bold: true, color: C.text1 });
    text(s, boxes[i][2], { x: x + 1.15, y: y + 0.52, w: 4.65, h: 1.1, fontSize: 12, color: C.accent5 });
  }
  s.addNotes("Shannon energy emphasises medium-intensity sounds; autocorrelation uses the periodicity of the whole window so it is robust to missed beats. Fusion only averages when both channels agree within 8 BPM.");

  // =========================================================== 12 Software + dashboard
  pres.addSection({ title: "Implementation" });
  s = content("Software implementation and dashboard", "Implementation");
  s.addImage({ path: A("dash_video.png"), x: 0.6, y: 1.35, w: 4.3, h: 4.3 / 1.186 });
  s.addImage({ path: A("dash_bvp.png"), x: 0.6, y: 5.1, w: 4.3, h: 4.3 / 3.18 });
  s.addImage({ path: A("psd.png"), x: 5.2, y: 1.35, w: 4.3, h: 4.3 / 2.271 });
  text(s, "Live camera view with face gate (green) and skin ROI; recovered pulse wave (below); pulse spectrum (right).", { x: 5.2, y: 3.35, w: 4.3, h: 0.8, fontSize: 12, italic: true, color: C.accent5 });
  card(s, 9.8, 1.35, 2.9, 5.35, { fill: C.background2 });
  text(s, "Modules", { x: 10.0, y: 1.5, w: 2.5, h: 0.35, fontSize: 16, bold: true, color: C.text1 });
  text(s, bullets([
    "usb_streamer.py: link, Flask API",
    "rppg_engine.py: face gate, ROI",
    "vitals_dsp.py: shared DSP",
    "acoustic_engine.py: PCG",
    "recorder.py: sessions",
    "evaluate.py: offline stats",
    "Frontend: HTML/JS + Plotly",
  ], { gap: 5 }), { x: 10.0, y: 1.95, w: 2.6, h: 3.2, fontSize: 12, color: C.text1 });
  text(s, "31 automated tests (pytest) + a node simulator", { x: 10.0, y: 5.6, w: 2.55, h: 0.9, fontSize: 12, bold: true, color: C.accent1 });
  const tabs = [["Dashboard", "live vitals, waveforms"], ["Signal analysis", "PSD, spectrogram, bands"], ["Diagnostics", "colour indices (exploratory)"], ["Experiments", "session recording"]];
  tabs.forEach((t, i) => {
    const y = 4.3 + i * 0.6;
    text(s, [{ text: t[0] + ": ", options: { bold: true, color: C.text1 } }, { text: t[1], options: { color: C.accent5 } }], { x: 5.2, y, w: 4.3, h: 0.5, fontSize: 13, valign: "middle" });
  });
  s.addNotes("The host software is modular; the same DSP code runs live and offline. The dashboard has four main tabs. Screenshots are from the prototype; a live demo is best here.");

  // =========================================================== 13 Colour screening
  s = content("Exploratory colour screening (Diagnostics Studio)", "Implementation");
  s.addImage({ path: A("rois.png"), x: 0.6, y: 1.35, w: 5.0, h: 5.0 / 1.33 });
  table(s, ["Index", "ROI", "Formula", "Indicates"], [
    ["Erythema EI", "Forehead", "100 (log R − log G)", "Perfusion"],
    ["Pallor PI", "Cheeks", "(G + B) / 2R", "Low haemoglobin"],
    ["Yellowness YI", "Eye band", "100 (R + G − 2B) / (R + G + B)", "Bilirubin (jaundice)"],
    ["Cyanosis CR", "Lips", "B / R", "Deoxygenation"],
    ["Symmetry HFI", "Both cheeks", "100 |G_L − G_R| / (G_L + G_R)", "Perfusion asymmetry"],
    ["Sharpness", "Whole frame", "Variance of Laplacian", "Frame selection"],
  ], { x: 5.95, y: 1.35, w: 6.75, colW: [1.45, 1.25, 2.55, 1.5], rowH: 0.55, fontSize: 12 });
  card(s, 5.95, 5.4, 6.75, 1.3, { fill: C.background1, line: C.accent4 });
  text(s, [
    { text: "Exploratory only. ", options: { bold: true, color: C.accent4 } },
    { text: "Uncalibrated RGB indices depend on lighting, white balance and skin tone (e.g. warm light raises YI). Reliable use needs a colour reference card and validation against blood tests.", options: { color: C.text1 } },
  ], { x: 6.15, y: 5.45, w: 6.4, h: 1.2, fontSize: 13, valign: "middle" });
  s.addNotes("The sharpest gated frame is analysed in five facial regions. These are screening indicators, not diagnoses; the main limitation is calibration.");

  // =========================================================== 14 Results: system
  pres.addSection({ title: "Results" });
  s = content("Results I: system performance", "Results");
  table(s, ["Configuration", "Host fps", "Jitter SD", "Frame loss", "Audio loss"], [
    ["Wi-Fi, first firmware (3-min session)", "5.1", "310 ms", "0 %", "0.66 %"],
    ["USB-serial 1 Mbaud, mic off", "7.4", "15.5 ms", "1.0 % rejected", "mic off"],
    [{ text: "Wi-Fi, fixed-rate capture (final, 30 s)", options: { bold: true } }, { text: "8.0", options: { bold: true } }, { text: "0.4 ms", options: { bold: true } }, { text: "0", options: { bold: true } }, { text: "0", options: { bold: true } }],
  ], { x: 0.6, y: 1.4, w: 7.4, colW: [3.2, 1.0, 1.1, 1.1, 1.0], rowH: 0.62, fontSize: 13 });
  card(s, 0.6, 4.2, 7.4, 2.5, { fill: C.background2 });
  text(s, "Frame-timing jitter (SD)", { x: 0.85, y: 4.32, w: 6, h: 0.35, fontSize: 14, bold: true, color: C.text1 });
  [["First Wi-Fi firmware", 310, C.accent5], ["USB-serial 1 Mbaud", 15.5, C.accent5], ["Fixed-rate capture", 0.4, C.accent2]].forEach(([lab, v, col], i) => {
    const y = 4.8 + i * 0.6, bw = Math.max(0.05, 4.0 * v / 310);
    text(s, lab, { x: 0.85, y, w: 1.9, h: 0.4, fontSize: 12, color: C.text1, valign: "middle" });
    s.addShape(pres.shapes.RECTANGLE, { x: 2.8, y: y + 0.04, w: bw, h: 0.32, fill: { color: col }, line: { color: col } });
    text(s, (v < 1 ? v.toFixed(1) : String(v)) + " ms", { x: 2.8 + bw + 0.1, y, w: 1.0, h: 0.4, fontSize: 13, bold: true, color: C.text1, valign: "middle" });
  });
  const stats = [["775×", "steadier frame timing", "310 ms → 0.4 ms"], ["8.0 fps", "evenly spaced at host", "> 5 fps Nyquist for 150 BPM"], ["0", "frames or audio blocks lost", "verified by sequence numbers"]];
  stats.forEach((st, i) => {
    const y = 1.4 + i * 1.8;
    card(s, 8.4, y, 4.3, 1.6, { fill: i === 0 ? C.accent1 : C.background2 });
    text(s, st[0], { x: 8.65, y: y + 0.15, w: 3.9, h: 0.7, fontSize: 34, bold: true, fontFace: "Cambria", color: i === 0 ? C.background1 : C.accent1 });
    text(s, st[1], { x: 8.65, y: y + 0.85, w: 3.9, h: 0.35, fontSize: 14, bold: true, color: i === 0 ? C.background1 : C.text1 });
    text(s, st[2], { x: 8.65, y: y + 1.18, w: 3.9, h: 0.35, fontSize: 12, color: i === 0 ? C.accent6 : C.accent5 });
  });
  s.addNotes("Measured on the real hardware. Moving capture into a fixed-rate task with timestamps at capture cut jitter from 310 ms to 0.4 ms. Final link: 8 fps evenly spaced, zero frames or audio blocks lost.");

  // =========================================================== 15 Results: algorithms
  s = content("Results II: algorithm verification", "Results");
  const ver = [
    ["±2 BPM", "Optical HR on synthetic signals", "52, 78 and 128 BPM with irregular 6–11 fps frame timing"],
    ["≈ 5 %", "Noise passing the SNR gate", "pure-noise test, 10–30 s windows; target ≤ 6 %"],
    ["16 → 6", "Buffer restarts in 3 min", "replay of a recorded session after 2 s gap bridging"],
    ["31 / 31", "Automated tests pass", "DSP, PCG, protocol, engine, server, recorder"],
  ];
  ver.forEach((v, i) => {
    const x = 0.6 + (i % 2) * 3.1, y = 1.4 + Math.floor(i / 2) * 1.95;
    card(s, x, y, 2.95, 1.8, { fill: C.background2 });
    text(s, v[0], { x: x + 0.2, y: y + 0.12, w: 2.6, h: 0.6, fontSize: 28, bold: true, fontFace: "Cambria", color: C.accent1 });
    text(s, v[1], { x: x + 0.2, y: y + 0.75, w: 2.6, h: 0.4, fontSize: 13, bold: true, color: C.text1 });
    text(s, v[2], { x: x + 0.2, y: y + 1.15, w: 2.6, h: 0.6, fontSize: 11, color: C.accent5 });
  });
  text(s, "Findings on real recordings", { x: 0.6, y: 5.4, w: 6, h: 0.35, fontSize: 15, bold: true, color: C.text1 });
  text(s, bullets([
    "First-firmware optical estimates had SNR −6 to −3 dB, i.e. at noise level, which motivated the SNR gate.",
    "Heart sounds through air were weak (ρ ≤ 0.18; 99.5 % of power < 25 Hz): the mic must touch the chest.",
  ], { gap: 4 }), { x: 0.6, y: 5.8, w: 6.0, h: 1.0, fontSize: 12, color: C.text1 });
  card(s, 6.95, 1.4, 5.75, 5.3, { fill: C.background1, line: C.accent4 });
  await circleIcon(s, "FaVial", 7.2, 1.6, 0.7, C.accent4);
  text(s, "Clinical validation: planned protocol", { x: 8.1, y: 1.72, w: 4.5, h: 0.45, fontSize: 17, bold: true, color: C.text1 });
  text(s, bullets([
    "References: chest-strap ECG (HR, R–R), finger pulse oximeter, metronome-paced breathing.",
    "Conditions C1–C5: rest, talking, small motion, low light, distance.",
    "30 s windows; development and test participants kept separate.",
    "Metrics: MAE, RMSE, Pearson r, Bland–Altman bias and 95 % limits (repeated measures).",
    "Acceptance: AAMI EC13, error ≤ 5 BPM or 10 %.",
    "Tooling ready: session recorder + analysis/evaluate.py.",
  ], { gap: 6 }), { x: 7.2, y: 2.5, w: 5.3, h: 3.4, fontSize: 13, color: C.text1 });
  text(s, "HR / RR accuracy against references has not been measured yet.", { x: 7.2, y: 6.0, w: 5.3, h: 0.5, fontSize: 13, bold: true, color: C.accent4 });
  s.addNotes("What is verified: algorithms on synthetic signals with known answers, the noise gate, and gap bridging. Clinical accuracy is not yet measured; the protocol and tools are ready. Do not claim accuracy numbers until the study is done.");

  // =========================================================== 16 Comparison
  s = content("Comparison with existing work", "Results");
  const Y = "✓", N = "✗", P = "~";
  table(s, ["System", "Contactless", "Heart sounds", "Synchronised single node", "Open source", "Quality gate shown", "Validated accuracy"], [
    ["Finger pulse oximeter", N, N, "—", N, P, Y],
    ["Smartwatch / chest strap", N, N, "—", N, P, Y],
    ["Face-scan phone apps", Y, N, N, N, P, "vendor claims"],
    ["rPPG research (CHROM, POS, DeepPhys)", Y, N, N, Y, P, "on datasets"],
    ["Electronic stethoscope", N, Y, "—", N, N, Y],
    [{ text: "SonicVitals (this work)", options: { bold: true, fill: { color: C.background2 } } }, ...[Y, Y, Y, Y, Y, "planned"].map((v) => ({ text: v, options: { bold: true, fill: { color: C.background2 } } }))],
  ], { x: 0.6, y: 1.4, w: 12.1, colW: [3.1, 1.4, 1.4, 1.9, 1.3, 1.5, 1.5], rowH: 0.62, fontSize: 13, align: "center" });
  text(s, "✓ yes   ✗ no   ~ partial   — not applicable", { x: 0.6, y: 5.85, w: 8, h: 0.35, fontSize: 12, color: C.accent5 });
  card(s, 0.6, 6.2, 12.1, 0.55, { fill: C.background2 });
  text(s, [{ text: "Positioning: ", options: { bold: true, color: C.accent1 } }, { text: "not a replacement for an oximeter, but a low-cost open platform for contactless, cross-checked monitoring.", options: { color: C.text1 } }],
    { x: 0.85, y: 6.2, w: 11.6, h: 0.55, fontSize: 14, valign: "middle" });
  s.addNotes("Our distinguishing features are the synchronised two-sensor node, openness and quality reporting. The honest weakness versus commercial devices is validated accuracy, which is our next step.");

  // =========================================================== 17 Limitations + future
  pres.addSection({ title: "Conclusion" });
  s = content("Limitations and future work", "Conclusion");
  const lim = [
    ["FaVial", "No reference validation yet", "ECG-strap study with Bland–Altman and AAMI EC13"],
    ["FaMoon", "Needs ambient light", "IR LED + IR-sensitive camera for night monitoring"],
    ["FaRunning", "Motion and lighting changes", "Landmark face tracking; ROI colour means on the node before JPEG"],
    ["FaStethoscope", "Weak heart sounds through air", "Contact or stethoscope-coupled microphone"],
    ["FaPalette", "Skin tone and uncalibrated colour", "Diverse participants; colour reference card"],
    ["FaMicrochip", "Processing on a laptop", "Edge processing on the ESP32 and battery power"],
  ];
  text(s, "LIMITATION", { x: 1.5, y: 1.35, w: 4.5, h: 0.3, fontSize: 12, bold: true, color: C.accent3 });
  text(s, "FUTURE WORK", { x: 6.9, y: 1.35, w: 5.5, h: 0.3, fontSize: 12, bold: true, color: C.accent1 });
  for (let i = 0; i < lim.length; i++) {
    const y = 1.75 + i * 0.85;
    await circleIcon(s, lim[i][0], 0.6, y + 0.05, 0.62, C.accent5);
    text(s, lim[i][1], { x: 1.5, y: y + 0.02, w: 4.5, h: 0.65, fontSize: 15, bold: true, color: C.text1, valign: "middle" });
    arrow(s, 6.1, y + 0.36, 6.7, y + 0.36, { color: C.accent2 });
    text(s, lim[i][2], { x: 6.9, y: y + 0.02, w: 5.8, h: 0.65, fontSize: 14, color: C.accent5, valign: "middle" });
  }
  s.addNotes("State the limitations before the panel does; each has a concrete next step.");

  // =========================================================== 18 Conclusion
  s = content("Conclusion", "Conclusion");
  const concl = [
    ["FaMicrochip", "Built a low-cost ESP32-S3 node that captures camera video and heart sounds on one microsecond clock and streams them over Wi-Fi with 0 frames or audio blocks lost."],
    ["FaWaveSquare", "Implemented CHROM rPPG (HR, RR) and Shannon-envelope PCG (HR, RMSSD) with a five-test face gate and quality-weighted fusion with an agreement gate."],
    ["FaShieldAlt", "Added honest quality gating: readings that do not clearly beat noise are shown as \"--\"."],
    ["FaChartLine", "Verified the link (8 fps, 0.4 ms jitter) and the algorithms (31 tests); the clinical validation protocol and tools are ready."],
  ];
  for (let i = 0; i < concl.length; i++) {
    const y = 1.45 + i * 1.3;
    await circleIcon(s, concl[i][0], 0.6, y + 0.1, 0.75);
    text(s, concl[i][1], { x: 1.6, y, w: 11.1, h: 1.0, fontSize: 17, color: C.text1, valign: "middle" });
  }
  s.addNotes("Summarise the four outcomes. Close with: next step is the ECG-referenced validation study.");

  // =========================================================== 19 References
  s = content("References", "Conclusion");
  const refs = [
    "W. Verkruysse, L. O. Svaasand, J. S. Nelson, \"Remote plethysmographic imaging using ambient light,\" Opt. Express, 2008.",
    "M.-Z. Poh, D. J. McDuff, R. W. Picard, \"Non-contact, automated cardiac pulse measurements using video imaging and blind source separation,\" Opt. Express, 2010.",
    "G. de Haan, V. Jeanne, \"Robust pulse rate from chrominance-based rPPG,\" IEEE Trans. Biomed. Eng., 2013.",
    "W. Wang, A. C. den Brinker, S. Stuijk, G. de Haan, \"Algorithmic principles of remote PPG,\" IEEE Trans. Biomed. Eng., 2017.",
    "W. Chen, D. McDuff, \"DeepPhys: Video-based physiological measurement using convolutional attention networks,\" ECCV, 2018.",
    "M. Villarroel et al., \"Non-contact physiological monitoring of preterm infants in the NICU,\" npj Digit. Med., 2019.",
    "H. Liang, S. Lukkarinen, I. Hartimo, \"Heart sound segmentation algorithm based on heart sound envelogram,\" Comput. Cardiol., 1997.",
    "D. B. Springer, L. Tarassenko, G. D. Clifford, \"Logistic regression-HSMM-based heart sound segmentation,\" IEEE Trans. Biomed. Eng., 2016.",
    "A. Mariakakis et al., \"BiliScreen: Smartphone-based scleral jaundice monitoring,\" Proc. ACM IMWUT, 2017.",
    "D. J. McDuff, E. B. Blackford, J. R. Estepp, \"The impact of video compression on remote cardiac pulse measurement,\" IEEE FG, 2017.",
    "E. M. Nowara, D. McDuff, A. Veeraraghavan, \"A meta-analysis of the impact of skin type and gender on non-contact PPG,\" CVPRW, 2020.",
    "P. Viola, M. Jones, \"Rapid object detection using a boosted cascade of simple features,\" CVPR, 2001.",
    "P. D. Welch, \"The use of FFT for the estimation of power spectra,\" IEEE Trans. Audio Electroacoust., 1967.",
    "J. M. Bland, D. G. Altman, \"Statistical methods for assessing agreement between two methods of clinical measurement,\" Lancet, 1986.",
    "AAMI EC13, \"Cardiac monitors, heart rate meters, and alarms.\"",
  ];
  text(s, refs.map((r, i) => ({ text: `[${i + 1}]  ${r}`, options: { breakLine: i < refs.length - 1, paraSpaceAfter: 3 } })),
    { x: 0.6, y: 1.3, w: 12.1, h: 5.5, fontSize: 12, color: C.text1 });
  s.addNotes("Full list in the project report.");

  // =========================================================== 20 Thank you
  s = pres.addSlide({ masterName: "CLOSING_DARK", sectionTitle: "Conclusion" });
  s.addText("Thank you", { placeholder: "title" });
  text(s, "Questions?", { x: 0.7, y: 1.5, w: 6, h: 0.8, fontSize: 30, bold: true, color: C.accent2, fontFace: "Cambria" });
  text(s, "Team", { x: 0.7, y: 3.0, w: 4, h: 0.35, fontSize: 14, bold: true, color: C.accent6 });
  text(s, TEAM.join("\n"), { x: 0.7, y: 3.4, w: 5, h: 1.3, fontSize: 18, color: C.background1 });
  text(s, "Faculty Guide", { x: 6.2, y: 3.0, w: 4, h: 0.35, fontSize: 14, bold: true, color: C.accent6 });
  text(s, GUIDE, { x: 6.2, y: 3.4, w: 5, h: 0.45, fontSize: 18, color: C.background1 });
  text(s, SCHOOL, { x: 0.7, y: 5.6, w: 11.9, h: 0.5, fontSize: 14, color: C.accent6 });
  s.addNotes("Thank the guide and panel; invite questions; offer a live demo.");

  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
})();
