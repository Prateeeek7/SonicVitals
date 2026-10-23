// SonicVitals final presentation (light background).
// Titles live in layout placeholders; every other piece of text sits inside a filled shape (card, chip,
// stat, badge) - no free-floating text boxes. Charts are native PowerPoint charts.
// Run: NODE_PATH=./node_modules node build_deck.js  ->  ../SonicVitals_Final_Presentation.pptx
const path = require("path");
const fs = require("fs");
const pptxgen = require("pptxgenjs");
const React = require("react");
const RDS = require("react-dom/server");
const sharp = require("sharp");
const FA = require("react-icons/fa");
const { applyTheme } = require(path.join(
  "/Users/pratikkumar/Library/Application Support/Claude/local-agent-mode-sessions/skills-plugin/f60764cc-15a7-40dd-9c7a-d92c406e07b4/10c211b4-b59a-44b4-bd1a-2292c6919fbb/skills/pptx/scripts",
  "apply_theme.js"));

const HERE = __dirname;
const FIG = path.join(HERE, "figs");
const DI = path.join(HERE, "deck_img");
const IMG = path.join(path.dirname(HERE), "Images");
const OUT = path.join(path.dirname(HERE), "SonicVitals_Final_Presentation.pptx");
const shot = (stamp) => path.join(IMG, fs.readdirSync(IMG).find((n) => n.startsWith(`Screenshot 2026-10-22 at ${stamp}`)));

const HEX = { dk1: "1F2A24", lt1: "FFFFFF", dk2: "0F6A4A", lt2: "F6F7F2", green: "0F6A4A", amber: "D98C00",
  blue: "2E86C1", red: "B85430", grey: "6E6E66", purple: "7B5EA7", line: "E1E3DB" };
const THEME = {
  name: "SonicVitals Light", headFontFace: "Calibri", bodyFontFace: "Calibri",
  colors: { dk1: HEX.dk1, lt1: HEX.lt1, dk2: HEX.dk2, lt2: HEX.lt2, accent1: HEX.green, accent2: HEX.amber,
    accent3: HEX.blue, accent4: HEX.red, accent5: HEX.grey, accent6: HEX.purple, hlink: HEX.blue, folHlink: HEX.grey },
};

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5 in
pres.title = "SonicVitals";
pres.author = "Janhavee Dhote, Pratik Kumar, Uday Krishan Khandelwal";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
const C = pres.SchemeColor;
const COL = { green: C.accent1, amber: C.accent2, blue: C.accent3, red: C.accent4, grey: C.accent5, purple: C.accent6 };
const W = 13.33, H = 7.5;

// ------------------------------------------------------------------ icons (white, for coloured circles)
const ICON = {};
async function loadIcons(names) {
  for (const n of names) {
    const svg = RDS.renderToStaticMarkup(React.createElement(FA[n], { color: "#FFFFFF", size: 256 }));
    ICON[n] = "image/png;base64," + (await sharp(Buffer.from(svg)).png().toBuffer()).toString("base64");
  }
}

// ------------------------------------------------------------------ layouts
const num = { x: W - 1.0, y: H - 0.42, w: 0.55, h: 0.28, fontSize: 10, color: C.accent5, align: "right" };
pres.defineSlideMaster({
  title: "SV_COVER", background: { color: HEX.lt2 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.75, w: 7.4, h: 2.75, fontSize: 30, bold: true, align: "left",
      color: C.text2, valign: "bottom", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: 0.6, y: 3.7, w: 7.4, h: 0.9, fontSize: 15, align: "left",
      color: C.accent5, valign: "top", margin: 0 }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "SV_SECTION", background: { color: HEX.lt2 },
  objects: [
    { placeholder: { options: { name: "num", type: "body", x: 0.6, y: 1.6, w: 5.6, h: 1.6, fontSize: 96, bold: true, align: "left",
      color: C.accent2, valign: "bottom", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 3.3, w: 5.8, h: 1.3, fontSize: 38, bold: true, align: "left",
      color: C.text2, valign: "top", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "sub", type: "body", x: 0.6, y: 4.65, w: 5.8, h: 1.0, fontSize: 18, align: "left",
      color: C.accent5, valign: "top", margin: 0 }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "SV_CONTENT", background: { color: HEX.lt2 }, slideNumber: num,
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.3, w: W - 1.2, h: 0.8, fontSize: 26, align: "left",
      bold: true, color: C.text2, valign: "middle", margin: 0 }, text: "" } },
    { line: { x: 0.6, y: 1.13, w: 0.9, h: 0, line: { color: HEX.amber, width: 3 } } },
  ],
});

// ------------------------------------------------------------------ building blocks
const shadow = () => ({ type: "outer", color: "000000", blur: 8, offset: 2, angle: 90, opacity: 0.10 });
let objN = 0;
const nm = (p) => `${p} ${++objN}`;

function shapeText(s, runs, o) {
  s.addText(runs, {
    shape: o.shape || pres.shapes.ROUNDED_RECTANGLE, x: o.x, y: o.y, w: o.w, h: o.h,
    rectRadius: o.r === undefined ? 0.1 : o.r,
    fill: { color: o.fill || C.background1, transparency: o.t || 0 },
    line: o.line ? { color: o.line, width: o.lw || 1 } : { type: "none" },
    shadow: o.shadow ? shadow() : undefined,
    align: o.align || "left", valign: o.valign || "top", margin: o.margin === undefined ? [10, 10, 8, 8] : o.margin,
    fontSize: o.size || 12, color: o.color || C.text1, bold: o.bold, paraSpaceAfter: o.psa,
    objectName: nm(o.name || "card"),
  });
}
function iconCircle(s, icon, x, y, d, color) {
  s.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color }, line: { type: "none" }, objectName: nm("icon bg") });
  s.addImage({ data: ICON[icon], x: x + d * 0.24, y: y + d * 0.24, w: d * 0.52, h: d * 0.52, objectName: nm(icon) });
}
// card with an icon circle (left, or on top when vertical) and title + body text
function card(s, o) {
  const d = o.d || 0.55;
  const color = o.color || COL.green;
  const runs = [{ text: o.title, options: { bold: true, fontSize: o.ts || 15, color: C.text1, breakLine: !!o.body } }];
  if (o.body) runs.push({ text: o.body, options: { fontSize: o.bs || 12, color: C.text1 } });
  const top = o.vertical;
  shapeText(s, runs, { x: o.x, y: o.y, w: o.w, h: o.h, fill: o.fill, t: o.t, line: o.fill ? undefined : HEX.line,
    shadow: !o.fill, valign: o.valign || (top ? "top" : "middle"), psa: 3,
    margin: top ? [12, 10, 8, (0.2 + d + 0.12) * 72] : [(0.2 + d + 0.16) * 72, 10, 6, 6], name: o.name || "card" });
  if (o.icon) iconCircle(s, o.icon, o.x + 0.2, top ? o.y + 0.2 : o.y + (o.h - d) / 2, d, color);
}
// big number callout on a tinted panel
function stat(s, o) {
  const color = o.color || COL.green;
  shapeText(s, [
    { text: o.value, options: { bold: true, fontSize: o.vs || 34, color, breakLine: true } },
    { text: o.label, options: { fontSize: o.ls || 12, color: C.text1 } },
  ], { x: o.x, y: o.y, w: o.w, h: o.h, fill: color, t: 88, valign: "middle", margin: [14, 10, 6, 6], name: "stat", align: o.align });
}
function chip(s, text, o) {
  shapeText(s, text, { x: o.x, y: o.y, w: o.w, h: o.h, r: Math.min(0.3, o.h / 2), fill: o.fill || COL.green, t: o.t,
    color: o.color || C.background1, bold: o.bold !== false, size: o.size || 12, align: o.align || "center",
    valign: "middle", margin: o.margin || [8, 8, 2, 2], line: o.line, name: "chip" });
}
function numBadge(s, n, x, y, d, color) {
  shapeText(s, String(n), { shape: pres.shapes.OVAL, x, y, w: d, h: d, fill: color, color: C.background1, bold: true,
    size: Math.round(d * 26), align: "center", valign: "middle", margin: 0, name: "number" });
}
function arrow(s, x, y, w, h, color, dir = "right") {
  const shape = { right: pres.shapes.RIGHT_ARROW, down: pres.shapes.DOWN_ARROW, both: pres.shapes.LEFT_RIGHT_ARROW }[dir];
  s.addShape(shape, { x, y, w, h, fill: { color: color || C.accent5, transparency: 25 }, line: { type: "none" }, objectName: nm("arrow") });
}
function imgSize(file) {
  const buf = fs.readFileSync(file);
  if (buf.readUInt32BE(0) === 0x89504e47) return { w: buf.readUInt32BE(16), h: buf.readUInt32BE(20) };
  let i = 2;
  while (i < buf.length) {
    const m = buf.readUInt16BE(i); const len = buf.readUInt16BE(i + 2);
    if (m >= 0xffc0 && m <= 0xffc3) return { w: buf.readUInt16BE(i + 7), h: buf.readUInt16BE(i + 5) };
    i += 2 + len;
  }
  return { w: 4, h: 3 };
}
// image fitted into a box, on a white rounded frame with a soft shadow; returns the frame rectangle
function framed(s, file, box, align = "center") {
  const { w: iw, h: ih } = imgSize(file);
  const pad = 0.08;
  const sc = Math.min((box.w - 2 * pad) / iw, (box.h - 2 * pad) / ih);
  const w = iw * sc, h = ih * sc;
  const x = align === "left" ? box.x + pad : box.x + (box.w - w) / 2;
  const y = box.y + (box.h - h) / 2;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: x - pad, y: y - pad, w: w + 2 * pad, h: h + 2 * pad, rectRadius: 0.08,
    fill: { color: C.background1 }, line: { color: HEX.line, width: 0.75 }, shadow: shadow(), objectName: nm("frame") });
  s.addImage({ path: file, x, y, w, h, objectName: path.basename(file) });
  return { x: x - pad, y: y - pad, w: w + 2 * pad, h: h + 2 * pad };
}
function chartPanel(s, x, y, w, h) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.1, fill: { color: C.background1 },
    line: { color: HEX.line, width: 0.75 }, shadow: shadow(), objectName: nm("chart panel") });
}

function chartImg(s, file, x, y, w, h) {
  chartPanel(s, x, y, w, h);
  s.addImage({ path: path.join(DI, file), x: x + 0.06, y: y + 0.06, w: w - 0.12, h: h - 0.12, objectName: file });
}

let section = "Introduction";
function content(title) {
  const s = pres.addSlide({ masterName: "SV_CONTENT", sectionTitle: section });
  s.addText(title, { placeholder: "title" });
  return s;
}
function divider(n, title, sub, file) {
  section = title;
  pres.addSection({ title });
  const s = pres.addSlide({ masterName: "SV_SECTION", sectionTitle: section });
  s.addText(n, { placeholder: "num" });
  s.addText(title, { placeholder: "title" });
  s.addText(sub, { placeholder: "sub" });
  s.addShape(pres.shapes.OVAL, { x: 9.4, y: -1.2, w: 5.2, h: 5.2, fill: { color: HEX.green, transparency: 92 }, line: { type: "none" }, objectName: "deco circle" });
  s.addShape(pres.shapes.OVAL, { x: 6.6, y: 4.9, w: 3.4, h: 3.4, fill: { color: HEX.amber, transparency: 90 }, line: { type: "none" }, objectName: "deco circle 2" });
  framed(s, file, { x: 6.8, y: 1.2, w: 5.95, h: 5.1 });
  return s;
}
function team(s, y, h) {
  const people = [["Janhavee Dhote", "24BML0120"], ["Pratik Kumar", "24BML0027"], ["Uday Krishan Khandelwal", "24BML0012"]];
  const w = 2.86, g = 0.2;
  people.forEach(([n, r], i) => card(s, { x: 0.6 + i * (w + g), y, w, h, icon: "FaUserGraduate", d: 0.5, title: n, body: r, ts: 13, bs: 12 }));
  card(s, { x: 0.6 + 3 * (w + g), y, w: 12.13 - 3 * (w + g), h, icon: "FaChalkboardTeacher", d: 0.5, title: "Guide: Jeeva J. B.",
    body: "School of Electronics Engineering (SENSE), VIT", ts: 13, bs: 11, color: COL.amber });
}

// ------------------------------------------------------------------ slides
async function build() {
  await loadIcons(["FaUserGraduate", "FaChalkboardTeacher", "FaHandPaper", "FaHome", "FaShieldAlt", "FaArrowsAlt",
    "FaExclamationTriangle", "FaMicrochip", "FaLayerGroup", "FaSearch", "FaHeartbeat", "FaBalanceScale", "FaLungs",
    "FaEye", "FaCheckCircle", "FaCamera", "FaMicrophone", "FaTv", "FaCrosshairs", "FaMagic", "FaBolt", "FaSun",
    "FaWaveSquare", "FaTint", "FaUserCheck", "FaRobot", "FaLeaf", "FaRecycle", "FaArrowRight", "FaCogs", "FaFlask",
    "FaLaptopCode"]);

  // 1 ---------------------------------------------------------------- cover
  pres.addSection({ title: section });
  let s = pres.addSlide({ masterName: "SV_COVER", sectionTitle: section });
  s.addText("SonicVitals: Contactless Vital-Sign Sensing with a Low-Cost Optical–Acoustic Edge Node, Skin-Metered Exposure Control and Quality-Gated Remote Photoplethysmography", { placeholder: "title" });
  s.addText("Final project review  ·  October 2026", { placeholder: "body" });
  s.addShape(pres.shapes.OVAL, { x: 9.2, y: -1.5, w: 5.4, h: 5.4, fill: { color: HEX.green, transparency: 92 }, line: { type: "none" }, objectName: "deco circle" });
  const fr = framed(s, path.join(DI, "live_map.png"), { x: 8.55, y: 0.55, w: 4.2, h: 4.2 });
  chip(s, "Blood-flow map, captured live from a webcam", { x: fr.x + 0.25, y: fr.y + fr.h - 0.6, w: fr.w - 0.5, h: 0.42, size: 11 });
  team(s, 5.35, 1.35);

  // 2 ---------------------------------------------------------------- motivation
  s = content("Why measure vital signs without contact?");
  stat(s, { x: 0.6, y: 1.45, w: 3.9, h: 1.6, value: "0.1–0.5 %", label: "change in skin brightness with every heartbeat: invisible to the eye, measurable by a camera" });
  stat(s, { x: 4.715, y: 1.45, w: 3.9, h: 1.6, value: "≈ ₹2,150", label: "for the complete edge node: camera, microphone, display and microcontroller", color: COL.amber });
  stat(s, { x: 8.83, y: 1.45, w: 3.9, h: 1.6, value: "0 contact", label: "no electrodes, finger clips or chest straps on the person", color: COL.blue });
  card(s, { x: 0.6, y: 3.25, w: 3.9, h: 2.35, vertical: true, icon: "FaHandPaper", title: "Contact sensors have limits",
    body: "Electrodes and clips must be attached and cleaned, can irritate fragile skin (newborns, burns, elderly) and restrict movement.", ts: 16, bs: 13.5 });
  card(s, { x: 4.715, y: 3.25, w: 3.9, h: 2.35, vertical: true, icon: "FaHome", color: COL.amber, title: "Continuous and remote care",
    body: "Telehealth, home and elderly monitoring need checks that work without trained staff or consumables.", ts: 16, bs: 13.5 });
  card(s, { x: 8.83, y: 3.25, w: 3.9, h: 2.35, vertical: true, icon: "FaShieldAlt", color: COL.blue, title: "Readings must be trustworthy",
    body: "Camera methods break with motion and lighting. A usable system must know, and say, when a value cannot be trusted.", ts: 16, bs: 13.5 });
  shapeText(s, [{ text: "Our answer:  ", options: { bold: true, color: C.background1 } },
    { text: "one camera node measures heart rate, breathing, HRV, blood flow and liveness, and every value carries a trust badge.", options: { color: C.background1 } }],
    { x: 0.6, y: 5.85, w: 12.13, h: 1.0, fill: COL.green, size: 17, valign: "middle", margin: [22, 16, 6, 6], name: "answer" });

  // 3 ---------------------------------------------------------------- gap -> problem
  s = content("Research gap and problem statement");
  [["FaArrowsAlt", "Accuracy collapses with motion and light", "Most rPPG methods assume a still face under constant lighting."],
   ["FaExclamationTriangle", "Few systems report reliability", "A number is shown even when the spectrum holds no clear heartbeat."],
   ["FaMicrochip", "Low-cost edge hardware is rarely used", "Skin statistics before compression and skin-metered exposure are uncommon."],
   ["FaLayerGroup", "One vital sign, little explanation", "Heart rate alone, without breathing, HRV, liveness or a view of the signal."],
  ].forEach(([ic, t, b], i) => card(s, { x: 0.6, y: 1.45 + i * 1.37, w: 6.0, h: 1.22, icon: ic, title: t, body: b,
    color: [COL.red, COL.amber, COL.blue, COL.purple][i] }));
  arrow(s, 6.75, 3.7, 0.6, 0.6, COL.grey);
  shapeText(s, [
    { text: "PROBLEM STATEMENT", options: { bold: true, fontSize: 13, color: C.background1, breakLine: true, charSpacing: 2 } },
    { text: "Design a low-cost, contactless system that measures heart rate and breathing rate from face video in real time, on an embedded edge node or a webcam, rejects motion and lighting artifacts, reports how far each value can be trusted, and explains it on a clear dashboard.", options: { fontSize: 17, color: C.background1, breakLine: true } },
    { text: "Heart-rate accuracy validated on UBFC-rPPG against contact PPG.", options: { fontSize: 13, color: C.background1, italic: true } },
  ], { x: 7.5, y: 1.45, w: 5.23, h: 5.33, fill: COL.green, valign: "middle", margin: [26, 22, 18, 70], psa: 14, name: "problem" });
  s.addShape(pres.shapes.OVAL, { x: 7.8, y: 1.8, w: 0.62, h: 0.62, fill: { color: HEX.lt1, transparency: 80 }, line: { type: "none" }, objectName: "icon bg" });
  s.addImage({ data: ICON.FaSearch, x: 7.95, y: 1.95, w: 0.32, h: 0.32, objectName: "FaSearch" });

  // 4 ---------------------------------------------------------------- objectives
  s = content("Objectives");
  [["FaMicrochip", "Edge sensor node", "ESP32-S3 with camera, MEMS microphone and OLED, streaming time-synchronised data over Wi-Fi", COL.blue],
   ["FaHeartbeat", "Robust heart rate", "CHROM, POS and GREEN with motion compensation, artifact repair and a quality gate", COL.green],
   ["FaBalanceScale", "One trusted number", "Combine classic and three deep-learning models into a stabilised, flag-protected heart rate", COL.amber],
   ["FaLungs", "Breathing and HRV", "Four-source breathing rate with its pattern, and heart-rate variability from the camera", COL.red],
   ["FaEye", "Face insights", "Blood-flow map, perfusion index, liveness, blink rate, head steadiness and colour indices", COL.purple],
   ["FaCheckCircle", "Validation", "Benchmark heart rate on UBFC-rPPG against contact PPG and verify live operation", COL.green],
  ].forEach(([ic, t, b, c], i) => card(s, { x: 0.6 + (i % 3) * 4.115, y: 1.45 + Math.floor(i / 3) * 2.75, w: 3.9, h: 2.55,
    vertical: true, icon: ic, color: c, title: `0${i + 1}   ${t}`, body: b, ts: 17, bs: 14.5 }));

  // ================================================================ 01 System design
  divider("01", "System design", "Edge node, firmware, data link and architecture", path.join(FIG, "setup_labeled.png"));

  // 5 ---------------------------------------------------------------- architecture
  s = content("System architecture: three tiers");
  [{ x: 0.6, w: 3.55, color: COL.blue, head: "EDGE NODE  ·  ESP32-S3", items: ["GC2145 camera · 240 × 160, 10 fps", "Skin RGB sums on raw pixels (10 Hz)", "Skin-metered exposure control", "INMP441 microphone · I2S 16 kHz", "SSD1306 OLED shows the vitals"] },
   { x: 4.75, w: 4.3, color: COL.green, head: "PROCESSING ENGINE  ·  PYTHON", items: ["Face detection + full-face gate", "Motion-compensated skin tracking", "CHROM · POS · GREEN + SNR gate", "TS-CAN · PhysNet · EfficientPhys", "Robust consensus + display stabiliser", "Breathing fusion · camera HRV", "Face insights · colour indices"] },
   { x: 9.65, w: 3.08, color: COL.amber, head: "WEB DASHBOARD", items: ["Dashboard", "Signal Analysis", "Diagnostics Studio", "Sessions", "Device telemetry"] },
  ].forEach((t) => {
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: t.x, y: 1.45, w: t.w, h: 4.55, rectRadius: 0.14, fill: { color: t.color, transparency: 90 },
      line: { color: t.color, width: 1 }, objectName: nm("tier") });
    chip(s, t.head, { x: t.x + 0.15, y: 1.6, w: t.w - 0.3, h: 0.5, fill: t.color, size: 12 });
    const gh = (4.55 - 0.85) / t.items.length;
    t.items.forEach((it, i) => chip(s, it, { x: t.x + 0.15, y: 2.25 + i * gh, w: t.w - 0.3, h: gh - 0.1, fill: C.background1,
      color: C.text1, bold: false, size: 12, line: HEX.line }));
  });
  arrow(s, 4.18, 3.55, 0.54, 0.34, COL.grey, "both");
  arrow(s, 9.08, 3.55, 0.54, 0.34, COL.grey, "both");
  chip(s, "Wi-Fi TCP :3333  → video 5 fps, skin sums 10 Hz, audio 4 kHz, µs time stamps   ← ROI boxes, exposure, vitals",
    { x: 0.6, y: 6.2, w: 8.45, h: 0.6, fill: COL.blue, t: 85, color: C.text1, bold: false, size: 12 });
  chip(s, "REST API polled 4× per second", { x: 9.25, y: 6.2, w: 3.48, h: 0.6, fill: COL.amber, t: 85, color: C.text1, bold: false, size: 12 });

  // 6 ---------------------------------------------------------------- hardware
  s = content("Edge sensor node hardware");
  framed(s, path.join(FIG, "setup_labeled.png"), { x: 0.6, y: 1.4, w: 7.35, h: 3.6 });
  stat(s, { x: 0.6, y: 5.25, w: 2.35, h: 1.6, value: "10 fps", label: "240 × 160 camera frames", vs: 28 });
  stat(s, { x: 3.1, y: 5.25, w: 2.35, h: 1.6, value: "16 kHz", label: "microphone sampling (I2S)", vs: 28, color: COL.amber });
  stat(s, { x: 5.6, y: 5.25, w: 2.35, h: 1.6, value: "1 clock", label: "µs time stamps on video, skin sums and audio", vs: 28, color: COL.blue });
  [["FaMicrochip", "ESP32-S3", "Dual-core 240 MHz, PSRAM, Wi-Fi; two FreeRTOS tasks pinned to the two cores", COL.blue],
   ["FaCamera", "GC2145 camera", "2 MP CMOS, RGB565; skin sums computed on raw pixels before JPEG", COL.green],
   ["FaMicrophone", "INMP441 microphone", "24-bit I2S MEMS; 63-tap FIR, decimated to 4 kHz", COL.amber],
   ["FaTv", "SSD1306 OLED", "0.96 in, 128 × 64, I2C; shows heart rate, breathing and status", COL.purple],
  ].forEach(([ic, t, b, c], i) => card(s, { x: 8.2, y: 1.4 + i * 1.39, w: 4.53, h: 1.25, icon: ic, color: c, title: t, body: b, ts: 14, bs: 11.5 }));

  // 7 ---------------------------------------------------------------- exposure + link
  s = content("Skin-metered exposure and the data link");
  [["FaCrosshairs", "Host sends skin boxes"], ["FaMicrochip", "Node sums R, G, B on raw pixels"],
   ["FaSun", "Host meters skin brightness"], ["FaBalanceScale", "Compare with target 165 / 255"], ["FaCogs", "CAM:EXP sets sensor exposure"]]
    .forEach(([ic, t], i) => {
      const x = 0.6 + i * 2.5;
      card(s, { x, y: 1.45, w: 2.13, h: 1.85, vertical: true, icon: ic, d: 0.6, title: t, ts: 14, color: i % 2 ? COL.amber : COL.green });
      if (i < 4) arrow(s, x + 2.16, 2.2, 0.32, 0.36, COL.grey);
    });
  card(s, { x: 0.6, y: 3.6, w: 5.9, h: 3.2, icon: "FaSun", color: COL.amber, title: "Why meter the skin, not the frame?",
    body: "Normal auto-exposure follows the whole picture: a bright window leaves the face dark, a dark room clips it. Metering only the skin keeps the face inside the sensor’s linear range, where the 0.1–0.5 % pulse survives. Saturated and near-black pixels are left out of the sums.", ts: 16, bs: 14.5 });
  shapeText(s, [{ text: "Line protocol over TCP (port 3333)", options: { bold: true, fontSize: 15 } }],
    { x: 6.75, y: 3.6, w: 5.98, h: 3.2, line: HEX.line, shadow: true, margin: [16, 10, 8, 12] });
  [["FRAME", "JPEG video, 5 fps"], ["RGB", "skin sums, 10 Hz"], ["AUDIO", "sound blocks"], ["INFO", "heap, stack, exposure"]]
    .forEach(([k, v], i) => chip(s, `↑ ${k}  ·  ${v}`, { x: 7.0 + (i % 2) * 2.8, y: 4.25 + Math.floor(i / 2) * 0.62, w: 2.65, h: 0.5, fill: COL.blue, size: 11.5 }));
  [["ROI", "skin boxes"], ["CAM:EXP", "exposure"], ["VITALS", "for OLED"]]
    .forEach(([k, v], i) => chip(s, `↓ ${k} · ${v}`, { x: 7.0 + i * 1.84, y: 5.6, w: 1.74, h: 0.5, fill: COL.amber, size: 10.5 }));
  chip(s, "Newest frame sent first: a slow link drops frames instead of adding delay", { x: 7.0, y: 6.2, w: 5.5, h: 0.45, fill: COL.green, t: 85, color: C.text1, bold: false, size: 11 });

  // 8 ---------------------------------------------------------------- cost
  s = content("Low-cost prototype");
  const costRows = [["ESP32-S3 camera board (with GC2145)", "1,200"], ["INMP441 I2S MEMS microphone", "250"], ["SSD1306 0.96 in OLED", "250"],
    ["Breadboard", "100"], ["Jumper wires and harness", "100"], ["USB cable", "150"], ["Wire antenna, misc.", "100"]];
  const hdr = (t, al) => ({ text: t, options: { bold: true, color: HEX.lt1, fill: { color: HEX.green }, align: al } });
  const band = (i) => ({ color: i % 2 ? HEX.lt1 : "EEF3EF" });
  const tbl = [[hdr("Component"), hdr("Cost (₹)", "right")]]
    .concat(costRows.map(([a, b], i) => [{ text: a, options: { fill: band(i) } }, { text: b, options: { align: "right", fill: band(i) } }]))
    .concat([[{ text: "Total", options: { bold: true, fill: { color: "FBEFD9" } } }, { text: "2,150", options: { bold: true, align: "right", fill: { color: "FBEFD9" } } }]]);
  s.addTable(tbl, { x: 0.6, y: 1.5, w: 6.4, colW: [4.9, 1.5], rowH: 0.52, fontSize: 13, color: HEX.dk1, fontFace: "Calibri",
    border: { type: "solid", color: HEX.line, pt: 0.75 }, valign: "middle", margin: [0.04, 0.14, 0.04, 0.14], objectName: "cost table" });
  chartImg(s, "chart_cost.png", 7.3, 1.45, 5.43, 3.85);
  stat(s, { x: 7.3, y: 5.5, w: 2.62, h: 1.35, value: "₹2,150", label: "complete edge node", vs: 28, color: COL.amber });
  stat(s, { x: 10.11, y: 5.5, w: 2.62, h: 1.35, value: "₹0", label: "software: free and open source", vs: 28 });

  // ================================================================ 02 Signal processing
  divider("02", "Signal processing", "From skin colour to one trustworthy heart rate", shot("8.26.38"));

  // 9 ---------------------------------------------------------------- pipeline
  s = content("Processing pipeline: eight stages");
  [["Face and full-face gate", "Haar cascade every 3rd frame; size, centring and both eyes checked", COL.blue],
   ["Skin tracking", "Forehead, cheeks and nose follow the face by sub-pixel phase correlation", COL.blue],
   ["Artifact repair", "Jumps repaired in the derivative domain; still stretch after last movement", COL.blue],
   ["Illumination rectification", "Background strips remove shared lighting flicker (gated)", COL.blue],
   ["Pulse extraction", "CHROM, POS and GREEN on the 15 Hz skin RGB", COL.green],
   ["Spectrum and quality gate", "Welch spectrum, SNR ≥ −2 dB, methods agree within 6 BPM", COL.green],
   ["Consensus", "Classic + tracker + TS-CAN, PhysNet, EfficientPhys; median ± 8 BPM", COL.amber],
   ["Stabilised display", "Holds the value, flags rapid change; badges explain every reading", COL.amber],
  ].forEach(([t, b, c], i) => {
    const x = 0.6 + (i % 4) * 3.1, y = 1.45 + Math.floor(i / 4) * 2.5;
    shapeText(s, [{ text: t, options: { bold: true, fontSize: 15, breakLine: true } }, { text: b, options: { fontSize: 12 } }],
      { x, y, w: 2.75, h: 2.2, line: HEX.line, shadow: true, margin: [12, 10, 8, 66], psa: 4 });
    numBadge(s, i + 1, x + 0.2, y + 0.2, 0.6, c);
    if (i % 4 < 3) arrow(s, x + 2.78, y + 0.95, 0.29, 0.34, COL.grey);
  });
  chip(s, "1–4  Signal conditioning", { x: 0.6, y: 6.55, w: 2.6, h: 0.4, fill: COL.blue, size: 11 });
  chip(s, "5–6  Pulse and gate", { x: 3.35, y: 6.55, w: 2.3, h: 0.4, fill: COL.green, size: 11 });
  chip(s, "7–8  Fusion and display", { x: 5.8, y: 6.55, w: 2.6, h: 0.4, fill: COL.amber, size: 11 });

  // 10 --------------------------------------------------------------- motion compensation
  s = content("Motion compensation lifts the pulse above noise");
  stat(s, { x: 0.6, y: 1.45, w: 5.5, h: 1.55, value: "−4 … −9 dB", label: "pulse SNR before: skin boxes slid over hair and background", color: COL.grey });
  arrow(s, 3.05, 3.1, 0.6, 0.45, COL.green, "down");
  stat(s, { x: 0.6, y: 3.65, w: 5.5, h: 1.55, value: "−1 … +1.5 dB", label: "pulse SNR after, with a still head: above the −2 dB gate" });
  card(s, { x: 0.6, y: 5.45, w: 5.5, h: 1.4, icon: "FaCheckCircle", title: "Key fix", body: "The tracking template is copied before phase correlation, so it no longer decays frame by frame.", ts: 14 });
  [["FaCrosshairs", "Phase correlation", "96 × 96 Hann-windowed face template; sub-pixel shift every frame", COL.blue],
   ["FaSearch", "Incremental search", "Starts from the last shift; accepted when response ≥ 0.15 and jump ≤ 0.12 face widths", COL.green],
   ["FaMagic", "Automatic relock", "Face detected again after 8 missed frames or more than 25 % drift", COL.amber],
   ["FaBolt", "Fast enough for 30 fps", "Detection every 3rd frame, background every 2nd: 21 → 10.6 ms per frame", COL.purple],
  ].forEach(([ic, t, b, c], i) => card(s, { x: 6.45, y: 1.45 + i * 1.37, w: 6.28, h: 1.22, icon: ic, color: c, title: t, body: b, ts: 14 }));

  // 11 --------------------------------------------------------------- pulse extraction
  s = content("Pulse extraction: three projections of skin colour");
  [["CHROM", "X = 3R − 2G\nY = 1.5R + G − 1.5B\nS = X − (σX / σY)·Y", "3 s windows; cancels intensity and specular change", COL.green],
   ["POS", "S1 = G − B\nS2 = −2R + G + B\nP = S1 + (σS1 / σS2)·S2", "1.6 s windows; plane orthogonal to skin tone", COL.blue],
   ["GREEN", "detrended green channel", "Reference only: strongest pulse, no motion rejection", COL.grey],
  ].forEach(([t, f, b, c], i) => {
    shapeText(s, [{ text: t, options: { bold: true, fontSize: 18, color: c, breakLine: true } },
      { text: f, options: { fontSize: 14, fontFace: "Cambria", italic: true, breakLine: true } },
      { text: b, options: { fontSize: 12, color: C.accent5 } }], { x: 0.6 + i * 4.115, y: 1.45, w: 3.9, h: 2.35, line: HEX.line, shadow: true, margin: [16, 12, 10, 12], psa: 6 });
  });
  framed(s, path.join(DI, "psd.png"), { x: 0.6, y: 4.0, w: 5.6, h: 2.9 });
  shapeText(s, [{ text: "Spectrum and SNR", options: { bold: true, fontSize: 15, breakLine: true } },
    { text: "Welch spectrum of the pulse; heart-rate band 0.75–2.5 Hz (45–150 BPM); peak tracked near the last accepted value.", options: { fontSize: 12.5, breakLine: true } },
    { text: "SNR = 10·log10 [ P(f0 ± 0.1 Hz) + P(2f0 ± 0.2 Hz) ] / P(rest of 0.5–4 Hz)", options: { fontSize: 13, fontFace: "Cambria", italic: true, color: C.text2 } }],
    { x: 6.45, y: 4.0, w: 6.28, h: 2.9, fill: COL.green, t: 90, margin: [16, 14, 10, 14], psa: 8, valign: "middle" });

  // 12 --------------------------------------------------------------- quality gate
  s = content("Quality gate: show a number only when it is real");
  ["SNR ≥ −2 dB (de Haan)", "POS and GREEN agree with CHROM within 6 BPM", "≥ 80 % real frames, ≤ 15 % repaired", "≥ 10 s of full-face, gated frames", "Peak inside 45–150 BPM, lighting peaks rejected"]
    .forEach((t, i) => card(s, { x: 0.6, y: 1.45 + i * 0.83, w: 5.6, h: 0.7, icon: "FaCheckCircle", d: 0.42, title: t, ts: 13.5 }));
  stat(s, { x: 0.6, y: 5.75, w: 2.7, h: 1.15, value: "1.56 BPM", label: "MAE with the gate (2.30 without)", vs: 24 });
  stat(s, { x: 3.5, y: 5.75, w: 2.7, h: 1.15, value: "19 %", label: "hardest windows withheld, not shown wrong", vs: 24, color: COL.amber });
  framed(s, shot("8.26.06"), { x: 6.45, y: 1.4, w: 6.28, h: 4.55 });
  chip(s, "Live: pulse SNR (black) against the −2 dB gate (dashed); amber = methods agreeing", { x: 6.45, y: 6.2, w: 6.28, h: 0.55, fill: COL.grey, t: 85, color: C.text1, bold: false, size: 11.5 });

  // 13 --------------------------------------------------------------- consensus
  s = content("Robust consensus: seven methods, one heart rate");
  [["CHROM", COL.amber], ["POS", COL.amber], ["GREEN", COL.amber], ["Bayes tracker", COL.green]]
    .forEach(([t, c], i) => chip(s, t, { x: 0.6 + i * 1.55, y: 1.45, w: 1.45, h: 0.5, fill: c, size: 12 }));
  [["TS-CAN", COL.blue], ["PhysNet", COL.blue], ["EfficientPhys", COL.blue]]
    .forEach(([t, c], i) => chip(s, t, { x: 0.6 + i * 2.07, y: 2.05, w: 1.97, h: 0.5, fill: c, size: 12 }));
  arrow(s, 3.4, 2.65, 0.5, 0.4, COL.grey, "down");
  card(s, { x: 0.6, y: 3.12, w: 6.1, h: 0.9, icon: "FaBalanceScale", d: 0.5, title: "Median → keep methods within ± 8 BPM → average", ts: 14 });
  arrow(s, 3.4, 4.08, 0.5, 0.4, COL.grey, "down");
  chip(s, "≥ 3 methods and ≥ half agree → value shown", { x: 0.6, y: 4.55, w: 2.98, h: 0.75, fill: COL.amber, t: 82, color: C.text1, size: 11.5 });
  chip(s, "≥ 4 methods, 60 % + a deep model → CONFIRMED", { x: 3.72, y: 4.55, w: 2.98, h: 0.75, fill: COL.green, t: 82, color: C.text1, size: 11.5 });
  shapeText(s, [{ text: "76 BPM", options: { bold: true, fontSize: 36, color: C.background1, breakLine: true } },
    { text: "6 OF 7 METHODS AGREE  ·  TS-CAN LEFT OUT", options: { fontSize: 13, bold: true, color: C.background1 } }],
    { x: 0.6, y: 5.5, w: 6.1, h: 1.38, fill: COL.green, valign: "middle", align: "center", margin: 6 });
  framed(s, path.join(DI, "methods_table.png"), { x: 6.95, y: 1.4, w: 5.78, h: 4.6 });
  chip(s, "Live comparison on the same face, at the same moment", { x: 6.95, y: 6.25, w: 5.78, h: 0.55, fill: COL.blue, t: 85, color: C.text1, bold: false, size: 11.5 });

  // 14 --------------------------------------------------------------- stabiliser
  s = content("Display stabiliser: steady values, honest flags");
  [["STABLE", "≥ 4 methods agree incl. a deep model", COL.green], ["CHANGE CONFIRMED", "new level seen 4 times", COL.green], ["ACQUIRING", "collecting first estimates", COL.grey],
   ["LOW CONFIDENCE", "value shown, fewer methods agree", COL.amber], ["HOLDING LAST VALUE", "no fresh estimate, up to 15 s", COL.amber], ["NO SIGNAL", "no face or usable pulse", COL.grey],
   ["RAPID CHANGE – HELD", "jump > 8 BPM not yet confirmed", COL.red], ["UNSTABLE", "estimates scatter widely", COL.red], ["METHODS DISAGREE", "no majority within ± 8 BPM", COL.red],
  ].forEach(([t, b, c], i) => shapeText(s, [{ text: t, options: { bold: true, fontSize: 13, color: c, breakLine: true } }, { text: b, options: { fontSize: 11.5 } }],
    { x: 0.6 + (i % 3) * 2.15, y: 1.45 + Math.floor(i / 3) * 1.42, w: 2.03, h: 1.3, fill: c, t: 88, margin: [10, 8, 6, 6], valign: "middle", psa: 3 }));
  [["8 BPM", "jump threshold"], ["× 4", "confirmations"], ["15 s", "hold time"]]
    .forEach(([v, l], i) => stat(s, { x: 0.6 + i * 2.15, y: 5.82, w: 2.03, h: 1.05, value: v, label: l, vs: 22, ls: 11, color: COL.blue }));
  framed(s, shot("8.26.16"), { x: 7.15, y: 1.4, w: 5.58, h: 4.35 });
  chip(s, "Heart-rate history: card value, accepted (filled) and rejected (hollow) estimates, red flags", { x: 7.15, y: 5.95, w: 5.58, h: 0.75, fill: COL.grey, t: 85, color: C.text1, bold: false, size: 11.5 });

  // 15 --------------------------------------------------------------- breathing
  s = content("Breathing rate: four sources, one agreement");
  [["FaSun", "Skin brightness", "RIIV", COL.amber], ["FaWaveSquare", "Pulse height", "RIAV", COL.blue], ["FaHeartbeat", "Pulse rate", "RIFV", COL.red], ["FaArrowsAlt", "Head motion", "vertical sway", COL.purple]]
    .forEach(([ic, t, b, c], i) => card(s, { x: 0.6 + (i % 2) * 3.05, y: 1.45 + Math.floor(i / 2) * 1.12, w: 2.92, h: 1.0, icon: ic, color: c, title: t, body: b, d: 0.5, ts: 14, bs: 11 }));
  arrow(s, 3.31, 3.75, 0.55, 0.38, COL.grey, "down");
  shapeText(s, [{ text: "Agreement fusion", options: { bold: true, fontSize: 15, color: C.background1, breakLine: true } },
    { text: "Detrend 0.07 Hz · whiten · search 6–36 /min · ≥ 2 sources within 4 /min · ≥ 20 s of still data", options: { fontSize: 12.5, color: C.background1 } }],
    { x: 0.6, y: 4.2, w: 5.97, h: 1.3, fill: COL.green, valign: "middle", margin: [14, 12, 8, 8], psa: 4 });
  chip(s, "Pattern:  REGULAR  ·  IRREGULAR (CV > 30 %)  ·  PAUSE (≥ 8 s)", { x: 0.6, y: 5.7, w: 5.97, h: 0.5, fill: COL.amber, t: 82, color: C.text1, size: 12 });
  chip(s, "Live: card 18–19 /min vs 16–20 /min counted on the graph", { x: 0.6, y: 6.33, w: 5.97, h: 0.5, fill: COL.blue, t: 82, color: C.text1, size: 12 });
  chartImg(s, "chart_rr.png", 6.85, 1.45, 5.88, 3.55);
  framed(s, shot("8.51.11"), { x: 6.85, y: 5.15, w: 5.88, h: 1.8 });

  // 16 --------------------------------------------------------------- HRV
  s = content("Heart-rate variability from the camera");
  [["Beat times", "CHROM pulse at 30 Hz, band 0.7–3.5 Hz, spline × 8, peaks ≥ 0.6 beat apart"],
   ["Clean intervals", "Within ± 20 % of the median; ≥ 15 intervals and ≥ 80 % clean"],
   ["RMSSD", "√ mean of squared differences of successive intervals"],
   ["Shown only when", "≥ 20 fps, pulse SNR ≥ +1 dB, result 5–150 ms, HR within 8 BPM of the card"]]
    .forEach(([t, b], i) => {
      shapeText(s, [{ text: t, options: { bold: true, fontSize: 14, breakLine: true } }, { text: b, options: { fontSize: 12 } }],
        { x: 0.6, y: 1.45 + i * 1.37, w: 5.5, h: 1.2, line: HEX.line, shadow: true, margin: [66, 10, 6, 6], valign: "middle", psa: 2 });
      numBadge(s, i + 1, 0.8, 1.45 + i * 1.37 + 0.33, 0.55, [COL.blue, COL.green, COL.amber, COL.red][i]);
    });
  framed(s, path.join(FIG, "hrv_snr.png"), { x: 6.4, y: 1.4, w: 6.33, h: 3.15 });
  stat(s, { x: 6.4, y: 4.8, w: 3.05, h: 1.4, value: "11 ms", label: "RMSSD error at +1 dB pulse SNR", vs: 28 });
  stat(s, { x: 9.68, y: 4.8, w: 3.05, h: 1.4, value: "64 ms", label: "error at −2 dB: why HRV is gated", vs: 28, color: COL.red });
  chip(s, "Beat timing needs a clean pulse: noise shifts peaks by tens of ms", { x: 6.4, y: 6.4, w: 6.33, h: 0.45, fill: COL.grey, t: 85, color: C.text1, bold: false, size: 11.5 });

  // ================================================================ 03 Face insights & dashboard
  divider("03", "Face insights and dashboard", "Blood flow, liveness, blinks, head steadiness and the analysis views", path.join(DI, "map_rg.png"));

  // 17 --------------------------------------------------------------- insights overview
  s = content("Face insights from the same camera");
  framed(s, path.join(DI, "insights_cards.png"), { x: 0.6, y: 1.4, w: 8.4, h: 4.0 }, "left");
  framed(s, path.join(DI, "live_map.png"), { x: 9.05, y: 1.4, w: 3.68, h: 4.0 });
  [["FaTint", "Blood-flow map", "30 s still capture", COL.red], ["FaUserCheck", "Liveness", "pulse or blinks", COL.green],
   ["FaHeartbeat", "Perfusion index", "pulse strength %", COL.red], ["FaLungs", "Breathing pattern", "regular / pause", COL.blue],
   ["FaEye", "Blink rate", "eye aspect ratio", COL.purple], ["FaCrosshairs", "Head steadiness", "RMS movement", COL.amber]]
    .forEach(([ic, t, b, c], i) => card(s, { x: 0.6 + i * 2.045, y: 5.65, w: 1.93, h: 1.25, vertical: true, icon: ic, d: 0.42, color: c, title: t, body: b, ts: 12, bs: 10.5 }));

  // 18 --------------------------------------------------------------- perfusion map
  s = content("Blood-flow map and perfusion index");
  [["32 × 32 skin cells", "colour trace of every cell over a 30 s still capture"],
   ["Lock-in at the heart rate", "in-phase amplitude against the face-wide pulse"],
   ["Noise-referenced score", "z against off-frequency noise; z ≥ 2.5 coloured"],
   ["Robust capture", "restarts on > 3 % movement; coarser grid if coverage < 30 %"]]
    .forEach(([t, b], i) => {
      shapeText(s, [{ text: t, options: { bold: true, fontSize: 14, breakLine: true } }, { text: b, options: { fontSize: 12 } }],
        { x: 0.6, y: 1.45 + i * 1.37, w: 4.4, h: 1.22, line: HEX.line, shadow: true, margin: [62, 10, 6, 6], valign: "middle", psa: 2 });
      numBadge(s, i + 1, 0.78, 1.45 + i * 1.37 + 0.36, 0.5, COL.red);
    });
  framed(s, path.join(FIG, "synthetic_map.png"), { x: 5.25, y: 1.4, w: 3.6, h: 3.6 });
  framed(s, path.join(DI, "live_map.png"), { x: 9.13, y: 1.4, w: 3.6, h: 3.6 });
  chip(s, "Synthetic test face (validation)", { x: 5.4, y: 5.1, w: 3.3, h: 0.42, fill: COL.grey, size: 11 });
  chip(s, "Live capture from the webcam", { x: 9.28, y: 5.1, w: 3.3, h: 0.42, fill: COL.red, size: 11 });
  stat(s, { x: 5.25, y: 5.72, w: 2.4, h: 1.15, value: "94 %", label: "synthetic skin mapped", vs: 24, ls: 11, color: COL.grey });
  stat(s, { x: 7.79, y: 5.72, w: 2.4, h: 1.15, value: "7 → 46 %", label: "live skin mapped", vs: 24, ls: 11, color: COL.red });
  stat(s, { x: 10.33, y: 5.72, w: 2.4, h: 1.15, value: "PI = 2A", label: "× 100 %: pulsatile AC / DC", vs: 24, ls: 11, color: COL.amber });

  // 19 --------------------------------------------------------------- liveness, blinks, head
  s = content("Liveness, blinks and head steadiness");
  const head = (x, ic, t, b, c) => card(s, { x, y: 1.45, w: 3.9, h: 1.15, icon: ic, color: c, title: t, body: b, ts: 15, bs: 11.5 });
  head(0.6, "FaUserCheck", "Liveness", "Is a living face in front of the camera?", COL.green);
  head(4.715, "FaEye", "Blink rate", "MediaPipe Face Mesh, 478 landmarks", COL.purple);
  head(8.83, "FaCrosshairs", "Head steadiness", "Movement and pose of the head", COL.amber);
  stat(s, { x: 0.6, y: 2.85, w: 1.88, h: 1.5, value: "13/13", label: "photos → NO PULSE", vs: 26, ls: 11 });
  stat(s, { x: 2.62, y: 2.85, w: 1.88, h: 1.5, value: "5/5", label: "pulsing faces → LIVE", vs: 26, ls: 11 });
  shapeText(s, [{ text: "LIVE when", options: { bold: true, breakLine: true } }, { text: "skin pulses in phase (evidence ≥ 0.15) or ≥ 2 blinks in 30 s. NO PULSE needs evidence < 0.08 three times and no blinks.", options: {} }],
    { x: 0.6, y: 4.6, w: 3.9, h: 2.25, fill: COL.green, t: 90, size: 14, valign: "middle", margin: [16, 14, 8, 8], psa: 6 });
  shapeText(s, "EAR = ( |p2 − p6| + |p3 − p5| ) / 2|p1 − p4|", { x: 4.715, y: 2.85, w: 3.9, h: 0.75, fill: COL.purple, t: 88,
    size: 14, color: C.text1, align: "center", valign: "middle", margin: 4 });
  framed(s, shot("8.50.49"), { x: 4.715, y: 3.75, w: 3.9, h: 1.3 });
  stat(s, { x: 4.715, y: 5.25, w: 3.9, h: 1.6, value: "20 / 20", label: "detected blinks, checked frame by frame, were real (dip ≥ 35 % of median EAR, ≤ 0.5 s)", vs: 26, ls: 11, color: COL.purple });
  [["< 1.5 %", "STEADY", COL.green], ["1.5–4 %", "SLIGHT MOVEMENT", COL.amber], ["> 4 %", "MOVING", COL.red]]
    .forEach(([v, l, c], i) => shapeText(s, [{ text: v + "   ", options: { bold: true, fontSize: 18, color: c } }, { text: l, options: { bold: true, fontSize: 13 } }],
      { x: 8.83, y: 2.85 + i * 0.85, w: 3.9, h: 0.72, fill: c, t: 88, valign: "middle", margin: [14, 8, 4, 4] }));
  shapeText(s, [{ text: "How", options: { bold: true, breakLine: true } }, { text: "RMS of face movement over 10 s as % of face width; yaw, pitch and roll from solvePnP on mesh landmarks. Steadiness also decides when breathing and the map may use the data.", options: {} }],
    { x: 8.83, y: 5.45, w: 3.9, h: 1.4, line: HEX.line, shadow: true, size: 11.5, valign: "middle", margin: [14, 10, 6, 6], psa: 3 });

  // 20 --------------------------------------------------------------- dashboard tour
  s = content("Dashboard: live vitals with their evidence");
  const d = framed(s, shot("8.26.38"), { x: 0.6, y: 1.4, w: 7.75, h: 4.05 });
  [[0.0, 0.03], [0.5, 0.03], [0.0, 0.52], [0.5, 0.52]].forEach(([fx, fy], i) => numBadge(s, i + 1, d.x + fx * d.w + 0.12, d.y + fy * d.h + 0.05, 0.42, COL.amber));
  [["Recovered pulse", "CHROM, band-passed 0.75–2.5 Hz, z-scored"], ["Respiratory waveform", "fused breathing signal, 0.1–0.6 Hz"],
   ["Heart-rate history", "card value, accepted / rejected estimates, flags"], ["Quality vs gate", "pulse SNR against −2 dB, methods agreeing"]]
    .forEach(([t, b], i) => {
      shapeText(s, [{ text: t, options: { bold: true, fontSize: 14, breakLine: true } }, { text: b, options: { fontSize: 12 } }],
        { x: 8.6, y: 1.4 + i * 1.05, w: 4.13, h: 0.95, line: HEX.line, shadow: true, margin: [52, 8, 4, 4], valign: "middle", psa: 2 });
      numBadge(s, i + 1, 8.74, 1.4 + i * 1.05 + 0.26, 0.42, COL.amber);
    });
  [["HEART RATE", "consensus, BPM", COL.green], ["BREATHING", "fusion, /min", COL.blue], ["HRV", "RMSSD, ms", COL.red], ["QUALITY", "peak share, %", COL.amber], ["HR SOURCE", "methods used", COL.purple]]
    .forEach(([t, b, c], i) => shapeText(s, [{ text: t, options: { bold: true, fontSize: 12, color: c, breakLine: true } }, { text: b, options: { fontSize: 11 } }],
      { x: 0.6 + i * 1.58, y: 5.7, w: 1.48, h: 1.15, fill: c, t: 88, valign: "middle", margin: [10, 6, 4, 4], psa: 2 }));
  shapeText(s, [{ text: "Every card: ", options: { bold: true } }, { text: "one large value and one status badge (green verified, amber estimate, red flag, grey none); the reason is in the tooltip.", options: {} }],
    { x: 8.6, y: 5.7, w: 4.13, h: 1.15, fill: COL.green, t: 90, size: 12, valign: "middle", margin: [12, 10, 6, 6] });

  // 21 --------------------------------------------------------------- signal analysis
  s = content("Signal Analysis: the engineering view");
  framed(s, shot("8.28.48"), { x: 0.6, y: 1.4, w: 12.13, h: 3.55 });
  [["Cardiac peak f0", "CHROM spectrum peak; BPM = 60 × f0", COL.green], ["SNR (de Haan)", "f0 and 2f0 power vs rest, dB", COL.green],
   ["Spectral concentration", "share of band power at the peak", COL.blue], ["Respiration fr", "fused breathing rate / 60", COL.blue],
   ["Methods agreeing", "POS, GREEN vs CHROM; % repaired", COL.amber], ["Video source", "camera and measured fps", COL.amber]]
    .forEach(([t, b, c], i) => shapeText(s, [{ text: t, options: { bold: true, fontSize: 13, color: c, breakLine: true } }, { text: b, options: { fontSize: 11.5 } }],
      { x: 0.6 + i * 2.045, y: 5.2, w: 1.93, h: 1.15, fill: c, t: 88, valign: "middle", margin: [10, 6, 4, 4], psa: 2 }));
  chip(s, "Graphs: power spectrum · microphone spectrogram · standardized pulse · moving-average decomposition · skin colour change · method agreement",
    { x: 0.6, y: 6.5, w: 12.13, h: 0.42, fill: COL.grey, t: 85, color: C.text1, bold: false, size: 11.5 });

  // 22 --------------------------------------------------------------- diagnostics
  s = content("Diagnostics Studio: colour indices from one sharp frame");
  [["map_rg.png", "R − G  ·  redness", COL.red], ["map_b.png", "CIELAB b*  ·  yellowness", COL.amber], ["map_br.png", "B / R  ·  blueness", COL.blue]]
    .forEach(([f, l, c], i) => {
      framed(s, path.join(DI, f), { x: 0.6 + i * 2.82, y: 1.4, w: 2.7, h: 3.35 });
      chip(s, l, { x: 0.6 + i * 2.82, y: 4.9, w: 2.7, h: 0.42, fill: c, size: 11 });
    });
  ["Sharpest frame (8 s)", "5 face regions", "Colour means", "Indices", "Range check"].forEach((t, i) => {
    chip(s, t, { x: 0.6 + i * 1.7, y: 5.6, w: 1.5, h: 0.6, fill: COL.green, t: i ? 82 : 0, color: i ? C.text1 : C.background1, size: 10.5 });
    if (i < 4) arrow(s, 0.6 + i * 1.7 + 1.51, 5.78, 0.18, 0.24, COL.grey);
  });
  chip(s, "Exploratory, uncalibrated software ranges: not a diagnosis", { x: 0.6, y: 6.4, w: 8.2, h: 0.45, fill: COL.grey, t: 85, color: C.text1, bold: false, size: 11.5 });
  [["Erythema EI", "100 (log10 R − log10 G), forehead · 8–23"], ["Pallor PI", "(G + B) / 2R, both cheeks · < 0.72"],
   ["Eye-band yellow YI", "100 (R + G − 2B) / (R + G + B) · < 12"], ["Lip blue/red CR", "B / R, lips · < 0.76"],
   ["Asymmetry HFI", "100 |G left − G right| / sum · < 5 %"]]
    .forEach(([t, b], i) => shapeText(s, [{ text: t, options: { bold: true, fontSize: 13, color: C.text2, breakLine: true } }, { text: b, options: { fontSize: 11.5 } }],
      { x: 9.05, y: 1.4 + i * 1.1, w: 3.68, h: 0.98, line: HEX.line, shadow: true, valign: "middle", margin: [12, 8, 4, 4], psa: 2 }));

  // ================================================================ 04 Results
  divider("04", "Results", "Benchmark accuracy, live operation and impact", shot("8.25.48"));

  // 23 --------------------------------------------------------------- UBFC
  s = content("Heart-rate accuracy on UBFC-rPPG");
  [["1.56", "BPM mean absolute error", COL.green], ["2.73", "BPM root-mean-square error", COL.blue], ["0.99", "Pearson correlation r", COL.amber], ["93 %", "of windows within 5 BPM", COL.purple]]
    .forEach(([v, l, c], i) => stat(s, { x: 0.6 + (i % 2) * 2.95, y: 1.45 + Math.floor(i / 2) * 1.75, w: 2.8, h: 1.6, value: v, label: l, color: c, vs: 36 }));
  card(s, { x: 0.6, y: 5.0, w: 5.75, h: 1.85, icon: "FaFlask", title: "Protocol", body: "10 subjects, 30 s windows, contact PPG as reference. The quality gate withholds the 19 % hardest windows; about 72 ms of processing per window.", bs: 12.5 });
  chartImg(s, "chart_benchmark.png", 6.6, 1.45, 6.13, 5.4);

  // 24 --------------------------------------------------------------- live operation
  s = content("Live operation");
  [["27 fps", "processed (was 16.4)", COL.green], ["10.6 ms", "per frame (was 21.4)", COL.blue], ["6–7 of 7", "methods agree, 76–83 BPM", COL.amber], ["18–19", "br/min vs 16–20 counted", COL.purple]]
    .forEach(([v, l, c], i) => stat(s, { x: 0.6 + i * 3.075, y: 1.45, w: 2.9, h: 1.45, value: v, label: l, color: c, vs: 30 }));
  chartImg(s, "chart_fps.png", 0.6, 3.15, 5.95, 3.7);
  chartImg(s, "chart_ms.png", 6.78, 3.15, 5.95, 3.7);

  // 25 --------------------------------------------------------------- tools
  s = content("Tools and technology");
  [["FaMicrochip", "Firmware", ["Arduino framework", "PlatformIO", "FreeRTOS, two cores", "ESP32 camera driver"], COL.blue],
   ["FaWaveSquare", "Signal processing", ["Python 3.10", "NumPy, SciPy", "OpenCV", "Welch, Butterworth"], COL.green],
   ["FaRobot", "AI models", ["PyTorch", "rPPG-Toolbox weights", "TS-CAN, PhysNet, EfficientPhys", "MediaPipe Face Mesh"], COL.purple],
   ["FaLaptopCode", "Web dashboard", ["Flask REST API", "HTML, CSS, JavaScript", "Plotly.js", "4 updates per second"], COL.amber]]
    .forEach(([ic, t, items, c], i) => {
      const x = 0.6 + i * 3.075;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.45, w: 2.9, h: 5.4, rectRadius: 0.14, fill: { color: c, transparency: 90 }, line: { color: c, width: 1 }, objectName: nm("tool column") });
      iconCircle(s, ic, x + 1.05, 1.7, 0.8, c);
      chip(s, t, { x: x + 0.2, y: 2.7, w: 2.5, h: 0.55, fill: c, size: 14 });
      items.forEach((it, j) => chip(s, it, { x: x + 0.2, y: 3.5 + j * 0.8, w: 2.5, h: 0.62, fill: C.background1, color: C.text1, bold: false, size: 12, line: HEX.line }));
    });

  // 26 --------------------------------------------------------------- work plan
  s = content("Work plan and team");
  s.addShape(pres.shapes.LINE, { x: 0.9, y: 2.65, w: 11.55, h: 0, line: { color: HEX.green, width: 3 }, objectName: "timeline" });
  [["Jul", "Problem, literature, plan"], ["Aug", "Design, components"], ["Sep", "MATLAB rPPG prototype"], ["Early Oct", "Edge node, firmware, Wi-Fi"],
   ["Mid Oct", "Exposure control, UBFC benchmark"], ["Late Oct", "Consensus, breathing, HRV, insights"], ["Oct", "Testing, report, viva"]]
    .forEach(([m, t], i) => {
      const x = 0.6 + i * 1.75;
      numBadge(s, i + 1, x + 0.58, 2.4, 0.5, i < 3 ? COL.blue : i < 6 ? COL.green : COL.amber);
      shapeText(s, [{ text: m, options: { bold: true, fontSize: 13, color: C.text2, breakLine: true } }, { text: t, options: { fontSize: 11 } }],
        { x, y: i % 2 ? 3.05 : 1.3, w: 1.65, h: 0.98, line: HEX.line, shadow: true, align: "center", valign: "middle", margin: 4, psa: 1 });
    });
  [["Janhavee Dhote", "24BML0120", "Literature survey, UBFC-rPPG benchmark, result analysis, documentation", COL.blue],
   ["Pratik Kumar", "24BML0027", "Signal-processing engine, fusion, breathing, HRV, face insights, dashboard, integration", COL.green],
   ["Uday Krishan Khandelwal", "24BML0012", "Edge node hardware, ESP32-S3 firmware, camera and microphone interfacing, testing", COL.amber]]
    .forEach(([n, r, b, c], i) => card(s, { x: 0.6 + i * 4.115, y: 4.45, w: 3.9, h: 2.4, vertical: true, icon: "FaUserGraduate", color: c, title: `${n}  ·  ${r}`, body: b, ts: 14, bs: 12 }));

  // 27 --------------------------------------------------------------- impact
  s = content("Social and environmental impact");
  [["3", "Good health and well-being", "Low-cost contactless screening for homes, clinics and remote care", "4C9F38"],
   ["9", "Industry, innovation and infrastructure", "Open hardware and software built from commodity parts", "FD6925"],
   ["10", "Reduced inequalities", "No specialised medical equipment: a ₹2,150 node and a laptop", "DD1367"]]
    .forEach(([n, t, b, c], i) => {
      const x = 0.6 + i * 4.115;
      shapeText(s, [{ text: `SDG ${n}`, options: { bold: true, fontSize: 30, color: HEX.lt1, breakLine: true } }, { text: t, options: { bold: true, fontSize: 14, color: HEX.lt1 } }],
        { x, y: 1.45, w: 3.9, h: 1.7, fill: c, valign: "middle", margin: [16, 10, 8, 8] });
      shapeText(s, b, { x, y: 3.25, w: 3.9, h: 1.0, line: HEX.line, shadow: true, size: 12.5, valign: "middle", margin: [14, 10, 6, 6] });
    });
  [["FaRecycle", "No consumables", "No electrodes, gel or probe covers to throw away"],
   ["FaLeaf", "Low power", "USB-powered node; reuses an existing laptop"],
   ["FaCogs", "Repairable", "Modular parts can be replaced or reused individually"]]
    .forEach(([ic, t, b], i) => card(s, { x: 0.6 + i * 4.115, y: 4.6, w: 3.9, h: 2.25, vertical: true, icon: ic, title: t, body: b, ts: 17, bs: 15 }));

  // 28 --------------------------------------------------------------- conclusion
  s = content("Conclusion and future work");
  shapeText(s, [{ text: "What we achieved", options: { bold: true, fontSize: 16, color: C.background1 } }], { x: 0.6, y: 1.45, w: 5.95, h: 0.6, fill: COL.green, valign: "middle", margin: [14, 8, 4, 4] });
  ["A complete low-cost contactless system: edge node, quality-gated engine, explainable dashboard",
   "Most accurate method on UBFC-rPPG: MAE 1.56 BPM, r = 0.99",
   "Real time at about 30 fps with seven methods in consensus",
   "Breathing, HRV, blood-flow map, liveness, blinks and colour indices from one camera"]
    .forEach((t, i) => card(s, { x: 0.6, y: 2.2 + i * 1.17, w: 5.95, h: 1.05, icon: "FaCheckCircle", d: 0.45, title: t, ts: 13 }));
  shapeText(s, [{ text: "Next steps", options: { bold: true, fontSize: 16, color: C.background1 } }], { x: 6.78, y: 1.45, w: 5.95, h: 0.6, fill: COL.amber, valign: "middle", margin: [14, 8, 4, 4] });
  ["Full UBFC, PURE and VIPL-HR benchmark; validation against ECG and oximeter across skin tones",
   "Stethoscope coupling and validation of the acoustic channel",
   "Calibrated SpO₂ and infrared illumination for low light",
   "Faster edge video for camera HRV and deep models on the node"]
    .forEach((t, i) => card(s, { x: 6.78, y: 2.2 + i * 1.17, w: 5.95, h: 1.05, icon: "FaArrowRight", d: 0.45, color: COL.amber, title: t, ts: 13 }));

  // 29 --------------------------------------------------------------- thank you
  s = pres.addSlide({ masterName: "SV_COVER", sectionTitle: section });
  s.addText("Thank you", { placeholder: "title" });
  s.addText("Questions and discussion", { placeholder: "body" });
  s.addShape(pres.shapes.OVAL, { x: 9.2, y: -1.5, w: 5.4, h: 5.4, fill: { color: HEX.green, transparency: 92 }, line: { type: "none" }, objectName: "deco circle" });
  framed(s, path.join(FIG, "setup_labeled.png"), { x: 6.9, y: 0.8, w: 5.85, h: 4.2 });
  team(s, 5.35, 1.35);

  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log(OUT);
}

build().catch((e) => { console.error(e); process.exit(1); });
