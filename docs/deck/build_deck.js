// Builds docs/deck/Bloom_final_presentation.pptx from the repo's own artefacts (screenshots, eval results).
//   NODE_PATH=<dir with pptxgenjs> node docs/deck/build_deck.js
const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");

const ROOT = path.resolve(__dirname, "../..");
const IMG = path.join(__dirname, "img");
const RES = path.join(ROOT, "evals/results");

// ── data from the repo ──────────────────────────────────────────────
const load = (n) => (fs.existsSync(path.join(RES, n + ".json")) ? JSON.parse(fs.readFileSync(path.join(RES, n + ".json"))) : null);
const agg = (n, k) => { const r = load(n); if (!r) return null; const v = r.aggregate[k]; return v && typeof v === "object" ? v.mean : v; };
const golden = fs.readFileSync(path.join(ROOT, "evals/golden.jsonl"), "utf8").trim().split("\n").map(JSON.parse);
const byCat = {};
golden.forEach((g) => (byCat[g.category] = (byCat[g.category] || 0) + 1));
const FINAL = load("final") ? "final" : "claim_check";
// The final config was run 3 times (EVALS.md §5); run 1 was overwritten on disk, its aggregate is recorded there.
const FINAL_RUN1 = { citation_precision: 0.887, cost_per_query_usd: 0.00942 };
const finalMean = (k) => { const v = [FINAL_RUN1[k], agg("final", k), agg("final_repeat", k)].filter((x) => x != null); return v.reduce((a, b) => a + b, 0) / v.length; };
const pct = (x) => (x == null ? "—" : Math.round(x * 100) + "%");
const money = (x) => (x == null ? "—" : "$" + x.toFixed(4));

// ── design tokens (Bloom brand) ─────────────────────────────────────
const C = {
  dark: "1F2A24", ink: "2B2A28", muted: "6F6A62", white: "FFFFFF", line: "E6E1D8",
  sage: "7C9A82", sageTint: "EEF3EF", rose: "D8A7A0", roseTint: "FBF0EE", sand: "E3C9A0", sandTint: "FBF5EA",
  terra: "C47A5A", terraTint: "F9ECE5", s1: "138A72", s2: "D86A2E", s3: "8A5FB3",
};
const HEAD = "Cambria", BODY = "Calibri";

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9"; // 10 x 5.625 in
pres.author = "Damilya";
pres.title = "Bloom — cycle-aware, evidence-based health coach";

// helpers ─────────────────────────────────────────────────────────────
function title(s, text, sub, dark = false) {
  s.addText(text, { x: 0.5, y: 0.32, w: 9, h: 0.6, fontFace: HEAD, fontSize: 30, bold: true, color: dark ? C.white : C.ink, margin: 0, isTextBox: true });
  if (sub) s.addText(sub, { x: 0.5, y: 0.9, w: 9, h: 0.35, fontFace: BODY, fontSize: 14, color: dark ? "C9D3CC" : C.muted, margin: 0, isTextBox: true });
}
function logo(s, x, y, r) { // the Bloom motif: three overlapping circles
  s.addShape(pres.shapes.OVAL, { x: x + r * 0.55, y, w: r, h: r, fill: { color: C.rose, transparency: 10 }, line: { type: "none" } });
  s.addShape(pres.shapes.OVAL, { x, y: y + r * 0.8, w: r, h: r, fill: { color: C.sage, transparency: 10 }, line: { type: "none" } });
  s.addShape(pres.shapes.OVAL, { x: x + r * 1.1, y: y + r * 0.8, w: r, h: r, fill: { color: C.sand, transparency: 5 }, line: { type: "none" } });
}
function card(s, x, y, w, h, fill = C.white, line = C.line) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.12, fill: { color: fill }, line: { color: line, width: 0.75 } });
}
function dot(s, x, y, color, label, size = 0.42) {
  s.addShape(pres.shapes.OVAL, { x, y, w: size, h: size, fill: { color }, line: { type: "none" } });
  s.addText(label, { x, y, w: size, h: size, align: "center", valign: "middle", fontFace: BODY, fontSize: 12, bold: true, color: C.white, margin: 0, isTextBox: true });
}
// Horizontal bar chart from plain shapes: native pptx charts are dropped by Keynote and some PDF exports.
function hbars(s, x, y, w, h, heading, labels, values, colors, max, fmt = (v) => String(v)) {
  if (heading) s.addText(heading, { x, y, w, h: 0.3, fontFace: BODY, fontSize: 12, bold: true, color: C.ink, margin: 0, isTextBox: true });
  const top = heading ? y + 0.4 : y, labelW = w * 0.42, barMax = w - labelW - 0.55;
  const rowH = (h - (top - y)) / labels.length, barH = Math.min(0.32, rowH * 0.62);
  labels.forEach((l, i) => {
    const ry = top + i * rowH, by = ry + (rowH - barH) / 2;
    s.addText(l, { x, y: ry, w: labelW - 0.1, h: rowH, align: "right", valign: "middle", fontFace: BODY, fontSize: 10.5, color: C.ink, margin: 0, isTextBox: true });
    const bw = Math.max(0.03, (values[i] / max) * barMax);
    s.addShape(pres.shapes.RECTANGLE, { x: x + labelW, y: by, w: bw, h: barH, fill: { color: colors[i % colors.length] }, line: { type: "none" } });
    s.addText(fmt(values[i]), { x: x + labelW + bw + 0.06, y: ry, w: 0.5, h: rowH, valign: "middle", fontFace: BODY, fontSize: 10, bold: true, color: C.ink, margin: 0, isTextBox: true });
  });
}
function box(s, x, y, w, h, head, body, fill, headColor = C.ink, fs = 11) {
  card(s, x, y, w, h, fill, fill);
  s.addText([
    { text: head, options: { bold: true, fontSize: fs + 2, color: headColor, breakLine: true } },
    { text: body, options: { fontSize: fs, color: C.ink } },
  ], { x: x + 0.15, y: y + 0.1, w: w - 0.3, h: h - 0.2, fontFace: BODY, valign: "top", margin: 0, paraSpaceAfter: 3, isTextBox: true });
}
function img(s, file, x, y, w, h) {
  s.addImage({ path: path.join(IMG, file), x, y, w, h, rounding: false });
  s.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill: { type: "none" }, line: { color: C.line, width: 0.75 } });
}
function arrow(s, x1, y1, x2, y2, color = C.muted) {
  s.addShape(pres.shapes.LINE, { x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1) || 0.001, h: Math.abs(y2 - y1) || 0.001,
    flipH: x2 < x1, flipV: y2 < y1, line: { color, width: 1.25, endArrowType: "triangle" } });
}

// 1 ── Title ───────────────────────────────────────────────────────────
{
  const s = pres.addSlide(); s.background = { color: C.dark };
  logo(s, 0.7, 1.35, 0.55);
  s.addText("Bloom", { x: 0.65, y: 2.45, w: 8, h: 0.9, fontFace: HEAD, fontSize: 54, bold: true, color: C.white, margin: 0, isTextBox: true });
  s.addText("A cycle-aware, evidence-based health coach", { x: 0.65, y: 3.3, w: 8.5, h: 0.5, fontFace: HEAD, fontSize: 22, italic: true, color: C.sand, margin: 0, isTextBox: true });
  s.addText("All my health data in one place · an AI coach that knows my data, my cycle and the research", { x: 0.65, y: 3.85, w: 8.6, h: 0.4, fontFace: BODY, fontSize: 14, color: "C9D3CC", margin: 0, isTextBox: true });
  s.addText("Final project · LLM Engineering · Demo Day, 25 September 2026 · Damilya", { x: 0.65, y: 4.85, w: 8.6, h: 0.3, fontFace: BODY, fontSize: 11, color: "9FB0A5", margin: 0, isTextBox: true });
  s.addNotes("One sentence: Bloom brings my scale, gym, watch and food data into one place and adds a coach that answers from my data and from research it can cite, and knows when to send me to a doctor.");
}

// 2 ── Problem ─────────────────────────────────────────────────────────
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, "5 apps, 0 answers", "My health data is scattered, and the advice I get is generic and male-default");
  const src = [["Withings", "weight, body fat, muscle", C.s1], ["Kinetix · Tanita", "gym sessions, 1RM tests, scans", C.s2], ["Apple Watch", "workouts, cycle, sleep, HR", C.s3], ["Foodvisor", "calories & macros (no API)", C.terra], ["Weather", "can I run outside?", C.sage]];
  src.forEach(([n, d, col], i) => {
    const x = 0.5 + i * 1.82;
    card(s, x, 1.5, 1.66, 1.35, C.white);
    s.addShape(pres.shapes.OVAL, { x: x + 0.15, y: 1.65, w: 0.3, h: 0.3, fill: { color: col }, line: { type: "none" } });
    s.addText([{ text: n, options: { bold: true, fontSize: 13, breakLine: true } }, { text: d, options: { fontSize: 11, color: C.muted } }],
      { x: x + 0.15, y: 2.02, w: 1.4, h: 0.75, fontFace: BODY, color: C.ink, valign: "top", margin: 0, isTextBox: true });
  });
  box(s, 0.5, 3.2, 4.4, 1.85, "None of them talk to each other",
    "Weight trends live in one app, training in two others, food in a fourth. No app sees the menstrual cycle next to training and nutrition, so no one can say whether a bad week is the cycle, sleep or under-eating.", C.sageTint);
  box(s, 5.1, 3.2, 4.4, 1.85, "Advice ignores women and PCOS",
    "“Train fasted in the morning to burn fat”, “sync your training to your cycle”: popular claims, often from male-only studies or weak evidence. With PCOS, wrong advice (under-fuelling, crash diets) has real costs.", C.roseTint, C.terra);
  s.addNotes("Pain: 5 apps, manual screenshots and spreadsheets, and advice that isn't graded for evidence or adapted to female physiology.");
}

// 3 ── User ───────────────────────────────────────────────────────────
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, "Who it's for", "Built for one real user first: me");
  card(s, 0.5, 1.45, 9, 1.25, C.sandTint, C.sandTint);
  s.addText("“A woman with PCOS who strength-trains and runs in Brussels, and wants advice that fits her body, her data and the evidence.”",
    { x: 0.8, y: 1.55, w: 8.4, h: 1.05, fontFace: HEAD, fontSize: 19, italic: true, color: C.ink, valign: "middle", margin: 0, isTextBox: true });
  const cols = [["Today", "Screenshots, spreadsheets and 5 app dashboards; mental math to connect them.", C.muted], ["Pain", "Advice that isn't evidence-graded, ignores the cycle, and never says “see a doctor”.", C.terra], ["Bloom", "One timeline + a coach that cites research, uses my numbers and escalates red flags.", C.s1]];
  cols.forEach(([h, t, col], i) => {
    const x = 0.5 + i * 3.07;
    dot(s, x, 3.05, col, String(i + 1));
    s.addText([{ text: h, options: { bold: true, fontSize: 15, breakLine: true } }, { text: t, options: { fontSize: 12.5, color: C.ink } }],
      { x: x + 0.55, y: 2.98, w: 2.35, h: 1.6, fontFace: BODY, color: C.ink, valign: "top", margin: 0, isTextBox: true });
  });
  s.addNotes("Business value: a personal tool first; later the same product for women with PCOS who train (irregular cycles break every 'cycle syncing' app).");
}

// 4 ── Solution ───────────────────────────────────────────────────────
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, "The solution: one calm dashboard + a coach", "Next.js app · three personas: Fitness Coach, Nutritionist, Integrative Medicine");
  img(s, "today.jpg", 4.55, 1.45, 4.95, 2.99);
  const rows = [["One timeline", "Withings, Tanita, Apple Watch, Kinetix and Foodvisor on one chart, shaded by cycle phase", C.s1],
    ["Cited answers", "every research claim links to the passage, page and DOI it came from", C.s2],
    ["Safety first", "red-flag symptoms → doctor referral, never coaching", C.terra],
    ["Goals you approve", "the coach proposes, you approve or edit before anything is saved", C.s3]];
  rows.forEach(([h, t, col], i) => {
    const y = 1.5 + i * 0.78;
    s.addShape(pres.shapes.OVAL, { x: 0.5, y: y + 0.05, w: 0.28, h: 0.28, fill: { color: col }, line: { type: "none" } });
    s.addText([{ text: h, options: { bold: true, fontSize: 13.5, breakLine: true } }, { text: t, options: { fontSize: 11, color: C.muted } }],
      { x: 0.92, y, w: 3.45, h: 0.72, fontFace: BODY, color: C.ink, valign: "top", margin: 0, isTextBox: true });
  });
  s.addText("Screenshot: demo data", { x: 4.55, y: 4.5, w: 4.95, h: 0.25, fontFace: BODY, fontSize: 9, italic: true, color: C.muted, align: "right", margin: 0, isTextBox: true });
}

// 5 ── Demo ───────────────────────────────────────────────────────────
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, "Demo", "Live: bloom-production-4f69.up.railway.app (demo data, password on request)");
  const shots = [["coach_answer.jpg", "1 · Cited, evidence-graded answer", "“Should I avoid fasted morning workouts with PCOS?”"],
    ["coach_goal.jpg", "2 · Goal proposal, human approval", "“Set me a realistic body-fat goal for December”"],
    ["coach_doctor.jpg", "3 · Red flag → doctor referral", "“I fainted after my workout this morning…”"]];
  // tallest image fits a 2.9in-high frame; widths follow aspect ratios
  const frames = [[0.5, 1.4, 2.85, 3.14], [3.55, 1.4, 2.95, 1.53], [6.7, 1.4, 2.8, 1.52]];
  shots.forEach(([f, h, q], i) => {
    const [x, y, w, hh] = frames[i];
    img(s, f, x, y, w, hh);
    s.addText([{ text: h, options: { bold: true, fontSize: 12, breakLine: true } }, { text: q, options: { fontSize: 10.5, italic: true, color: C.muted } }],
      { x, y: y + hh + 0.08, w, h: 0.6, fontFace: BODY, color: C.ink, valign: "top", margin: 0, isTextBox: true });
  });
  card(s, 3.55, 3.75, 5.95, 1.35, C.sageTint, C.sageTint);
  s.addText([{ text: "Also in the demo", options: { bold: true, fontSize: 12, breakLine: true } },
    { text: "Data page: Withings OAuth sync · Apple Health ZIP · Mywellness ZIP · Foodvisor screenshot → vision extraction with consistency checks → confirm", options: { fontSize: 11 } }],
  { x: 3.7, y: 3.85, w: 5.65, h: 1.15, fontFace: BODY, color: C.ink, valign: "top", margin: 0, isTextBox: true });
  s.addNotes("Demo order (3 min): Today dashboard → Integrative Medicine: fasted cardio question, open a citation chip → Coach: body-fat goal, approve → Goals page → 'I fainted…' → Data page: Foodvisor screenshot. Show 'How I got here' under an answer and the matching LangSmith trace.");
}

// 6 ── Architecture ───────────────────────────────────────────────────
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, "Architecture", "Every box is replaceable by config; the data layer is deliberately shared");
  const B = (x, y, w, h, t, fill, fs = 10.5, bold = false) => { card(s, x, y, w, h, fill, fill); s.addText(t, { x, y, w, h, align: "center", valign: "middle", fontFace: BODY, fontSize: fs, bold, color: C.ink, margin: 0.04, isTextBox: true }); };
  B(0.5, 1.45, 1.75, 0.55, "Next.js frontend", C.sandTint, 11, true);
  B(0.5, 2.35, 1.75, 1.95, "Sources\nWithings OAuth\nApple Health ZIP\nMywellness ZIP\nFoodvisor screenshot\nOpen-Meteo", C.sandTint, 10);
  B(2.9, 1.45, 2.1, 0.55, "FastAPI · SSE", C.sageTint, 11, true);
  B(2.9, 2.35, 2.1, 1.95, "LangGraph agent\n14 nodes\nguards · triage · Skill\ncache · generate\ncitation loop · HITL", C.sageTint, 10);
  B(5.6, 1.45, 1.9, 0.9, "health-data MCP server\n9 tools", C.roseTint, 10.5, true);
  B(5.6, 2.55, 1.9, 0.75, "RAG: Qdrant +\nFlashRank rerank", C.roseTint, 10.5);
  B(5.6, 3.5, 1.9, 0.8, "OpenAI\ngpt-4.1 / 4.1-mini\n+ fallback, budget", C.roseTint, 10);
  B(8.0, 1.45, 1.5, 0.9, "SQLite\nhealth data", "F2F0EC", 10.5);
  B(8.0, 2.55, 1.5, 0.75, "14 research\npapers (PMC)", "F2F0EC", 10);
  B(8.0, 3.5, 1.5, 0.8, "LangSmith\ntraces · evals", "F2F0EC", 10);
  arrow(s, 2.25, 1.72, 2.9, 1.72); arrow(s, 3.95, 2.0, 3.95, 2.35); arrow(s, 5.0, 2.9, 5.6, 1.9);
  arrow(s, 5.0, 3.0, 5.6, 2.92); arrow(s, 5.0, 3.6, 5.6, 3.9); arrow(s, 7.5, 1.9, 8.0, 1.9); arrow(s, 7.5, 2.92, 8.0, 2.92);
  arrow(s, 2.25, 3.3, 2.9, 3.3); arrow(s, 7.5, 3.9, 8.0, 3.9);
  s.addText("Coupling by choice: the dashboard and the MCP tools call the same queries.py, so the coach quotes exactly the numbers on the charts. Claude Desktop/Code can use the same MCP server.",
    { x: 0.5, y: 4.55, w: 9, h: 0.55, fontFace: BODY, fontSize: 11, italic: true, color: C.muted, margin: 0, isTextBox: true });
  s.addNotes("Walk one request: SSE chat → input guard → triage (mini) → Skill → cache → MCP tools → multi-query retrieval + rerank → gpt-4.1 → per-claim citation check (loop) → output guard → final/interrupt.");
}

// 7 ── LangGraph ──────────────────────────────────────────────────────
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, "The agent: branches, a loop and a human in it", "LangGraph StateGraph · checkpointed so an approval can resume in a later HTTP request");
  const steps = ["Input guard", "Triage", "Skill router", "Cache", "MCP data", "Retrieve", "Generate", "Citation check", "Output guard"];
  steps.forEach((t, i) => {
    const x = 0.5 + i * 1.02, y = 1.55;
    const fill = t === "Triage" || t === "Citation check" ? C.roseTint : C.sageTint;
    card(s, x, y, 0.92, 0.62, fill, fill);
    s.addText(t, { x, y, w: 0.92, h: 0.62, align: "center", valign: "middle", fontFace: BODY, fontSize: 10, bold: true, color: C.ink, margin: 0.03, isTextBox: true });
    if (i < steps.length - 1) arrow(s, x + 0.92, y + 0.31, x + 1.02, y + 0.31);
  });
  box(s, 0.5, 2.5, 2.9, 1.6, "Branch: safety triage", "Red flags (chest pain, fainting, no period > 3 months, eating < 1,000 kcal, medication changes) → doctor referral with 112 for emergencies. Off-topic → polite decline.", C.terraTint, C.terra, 10.5);
  box(s, 3.55, 2.5, 2.9, 1.6, "Loop: citation verification", "Every cited sentence is checked against its passage; unsupported → targeted feedback → rewrite (max 2), then a visible “unverified” note.", C.roseTint, C.ink, 10.5);
  box(s, 6.6, 2.5, 2.9, 1.6, "Human-in-the-loop", "Goal requests → structured SMART goal → interrupt() → Approve / Edit / Not now → saved through the MCP save_goal tool.", C.sandTint, C.ink, 10.5);
  s.addText("Why LangGraph: explicit, testable control flow (bounded loop + durable interrupt), tested with fake LLMs. CrewAI hides the flow behind roles; Parlant is policy-centric rather than pipeline-centric.",
    { x: 0.5, y: 4.35, w: 9, h: 0.6, fontFace: BODY, fontSize: 11, italic: true, color: C.muted, margin: 0, isTextBox: true });
}

// 8 ── MCP + Skill ────────────────────────────────────────────────────
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, "Own MCP server + own Skill", "Why not just functions and a longer prompt?");
  card(s, 0.5, 1.45, 4.4, 3.6, C.sageTint, C.sageTint);
  s.addText([
    { text: "health-data MCP server · 9 tools", options: { bold: true, fontSize: 15, breakLine: true } },
    { text: "body-composition trend · latest metrics · strength progress (1RM) · cycle status · nutrition summary · workouts · weather · goals · save goal", options: { fontSize: 11.5, breakLine: true } },
    { text: " ", options: { fontSize: 6, breakLine: true } },
    { text: "Why MCP: ", options: { bold: true, fontSize: 11.5 } },
    { text: "the same tools serve the in-app agent and Claude Desktop/Code with zero glue; the tool schema is the contract the planner LLM reads. If the server is down the agent falls back to in-process tools.", options: { fontSize: 11.5 } },
  ], { x: 0.7, y: 1.6, w: 4.0, h: 3.3, fontFace: BODY, color: C.ink, valign: "top", margin: 0, isTextBox: true });
  card(s, 5.1, 1.45, 4.4, 3.6, C.roseTint, C.roseTint);
  s.addText([
    { text: "womens-health-evidence Skill (SKILL.md)", options: { bold: true, fontSize: 15, breakLine: true } },
    { text: "Evidence grading (Strong / Moderate / Limited / Expert opinion), cycle and PCOS nuances, fasted-training honesty, red flags, citation rules.", options: { fontSize: 11.5, breakLine: true } },
    { text: " ", options: { fontSize: 6, breakLine: true } },
    { text: "Why a Skill: ", options: { bold: true, fontSize: 11.5 } },
    { text: "versioned domain policy in one file, loaded only when the question triggers it (keywords + triage flag), so ~1.5k tokens aren't paid on unrelated questions. Works in Claude Code too.", options: { fontSize: 11.5 } },
  ], { x: 5.3, y: 1.6, w: 4.0, h: 3.3, fontFace: BODY, color: C.ink, valign: "top", margin: 0, isTextBox: true });
}

// 9 ── RAG + multimodal ───────────────────────────────────────────────
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, "RAG over research + vision for food logs", "Answers are only as good as what's retrieved, and what's read from a screenshot");
  const pipe = [["14 papers", "PCOS guideline 2023, ISSN, WHO, meta-analyses"], ["Parse", "PDF glyph-gap fix + JATS XML"], ["455 chunks", "section-aware, 450 tok, page kept"], ["Embed + Qdrant", "text-embedding-3-small"], ["Multi-query", "triage writes 1–3 sub-queries"], ["Rerank", "FlashRank per query → top 5"]];
  pipe.forEach(([h, t], i) => {
    const x = 0.5 + i * 1.53;
    card(s, x, 1.45, 1.4, 1.3, C.sageTint, C.sageTint);
    s.addText([{ text: h, options: { bold: true, fontSize: 12, breakLine: true } }, { text: t, options: { fontSize: 9.5, color: C.muted } }],
      { x: x + 0.08, y: 1.52, w: 1.24, h: 1.16, fontFace: BODY, color: C.ink, valign: "top", margin: 0, isTextBox: true });
    if (i < pipe.length - 1) arrow(s, x + 1.4, 2.1, x + 1.53, 2.1);
  });
  box(s, 0.5, 3.0, 4.4, 2.05, "Found by measuring",
    "6 of 12 PDFs lost their spaces (15–43 % glued words) → rebuilt words from glyph positions. Compound questions (“fasted cardio + women + PCOS”) retrieved only PCOS papers → multi-query with per-facet round-robin.", C.sandTint, C.ink, 10.5);
  box(s, 5.1, 3.0, 4.4, 2.05, "Multimodal: Foodvisor has no API",
    "The screenshot is the only data channel → vision model with a strict schema → Atwater check (kcal ≈ 4C + 4P + 9F) → user confirms. Caught a real misread: “122 Cal over” (vs goal) read as intake; now computed from macros (1,589 kcal).", C.roseTint, C.terra, 10.5);
}

// 10 ── Evals setup ───────────────────────────────────────────────────
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, "Evaluation: " + golden.length + " golden examples, 7 metrics", "Safety, groundedness and personal accuracy: the three ways a health coach fails");
  const cats = ["evidence", "data", "red_flag", "near_miss", "injection", "off_topic", "smalltalk", "goal"];
  const counts = cats.map((c) => byCat[c] || 0);
  hbars(s, 0.5, 1.45, 4.4, 3.5, "Golden set by category", cats.map((c) => c.replace("_", " ")), counts, [C.s1], Math.max(...counts));
  const m = [["route_correct", "deterministic", "red flags, near-misses, injections"], ["retrieval_hit", "deterministic", "expected paper in top-5"], ["numeric_accuracy", "deterministic", "true personal number in answer"], ["goal_proposed", "deterministic", "HITL reached (or correctly not)"], ["faithfulness", "LLM judge", "claims supported by evidence/data"], ["citation_precision", "LLM judge · custom", "cited passage supports its sentence"], ["key_point_recall", "LLM judge", "says what the literature says"]];
  const rows = [[{ text: "metric", options: { bold: true } }, { text: "type", options: { bold: true } }, { text: "catches", options: { bold: true } }], ...m.map((r) => r.map((t) => ({ text: t })))];
  s.addTable(rows, { x: 5.2, y: 1.45, w: 4.3, colW: [1.35, 1.05, 1.9], fontFace: BODY, fontSize: 9.5, color: C.ink, border: { type: "solid", color: C.line, pt: 0.75 }, fill: { color: C.white }, rowH: 0.36 });
  s.addText("Plus latency p50/p95, cost/query, rewrite rate · evals run on a seeded demo DB, cache off · A/B arms = config options, no code changes",
    { x: 5.2, y: 4.5, w: 4.3, h: 0.55, fontFace: BODY, fontSize: 9.5, italic: true, color: C.muted, margin: 0, isTextBox: true });
}

// 11 ── Results ───────────────────────────────────────────────────────
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, "What the experiments decided", "Citation precision by configuration (LLM judge: gpt-4.1) · single runs unless noted");
  const arms = [["baseline", "Baseline (judge v1)"], ["ab_mini", "gpt-4.1-mini writer"], ["ab_no_rerank", "No reranker"], ["ab_single_query", "Single query"], ["prompt_v1", "Prompt v1"], ["no_citation_loop", "No citation loop"], [FINAL, FINAL === "final" ? "Final (judge v2, mean of 3)" : "Judge v2 (per-claim)"]];
  const vals = arms.map(([k]) => Math.round(((k === FINAL ? finalMean("citation_precision") : agg(k, "citation_precision")) || 0) * 100));
  hbars(s, 0.5, 1.4, 5.2, 3.6, "Citation precision", arms.map((a) => a[1]), vals, [C.sage, C.sage, C.s2, C.sage, C.sage, C.sage, C.s1], 100, (v) => v + "%");
  const stats = [[pct(agg(FINAL, "route_correct")), "safety routing\n(red flags, injections)", C.s1], [pct(agg("baseline", "citation_precision")) + " → " + pct(finalMean("citation_precision")), "citation precision (mean of 3 runs;\nrun-to-run noise ≈ ±5 pts)", C.s2], [money(finalMean("cost_per_query_usd")), "mean cost per query\n(red flags ≈ $0.0003)", C.s3]];
  stats.forEach(([v, l, col], i) => {
    const y = 1.35 + i * 1.25;
    s.addText(v, { x: 5.95, y, w: 3.55, h: 0.62, fontFace: HEAD, fontSize: 30, bold: true, color: col, margin: 0, isTextBox: true });
    s.addText(l, { x: 5.95, y: y + 0.6, w: 3.55, h: 0.5, fontFace: BODY, fontSize: 10.5, color: C.muted, margin: 0, isTextBox: true });
  });
  s.addNotes("Decisions: keep gpt-4.1 as writer (mini is -0.04 precision at half the cost → it's the fallback). Keep the reranker (largest drop without it). Keep multi-query (fixes compound questions). Adopt the per-claim judge (+0.15). T=0.3 kept; hyperparameters matter less than architecture. Caveat: n=14–23 per metric, one example ≈ 0.05.");
}

// 11b ── Observability ───────────────────────────────────────────────
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, "Every request traced in LangSmith", "One trace per chat turn: graph nodes, LLM calls, retriever and MCP tools, tagged by persona and eval run");
  img(s, "langsmith.jpg", 0.5, 1.4, 5.15, 3.5);
  s.addText("Screenshot: LangSmith tracing project (1,293 traces in a day of evals and demos)", { x: 0.5, y: 4.95, w: 5.15, h: 0.25, fontFace: BODY, fontSize: 9, italic: true, color: C.muted, margin: 0, isTextBox: true });
  const notes = [["Debug", "Open a trace to see triage → retrieve → generate → citation_check, with each rewrite of the loop as its own span.", C.s1],
    ["Cost & latency", "Tokens and $ per LLM call; that's where the ≈ $0.009 per research answer comes from.", C.s2],
    ["Experiments", "Each eval config runs as a LangSmith experiment on the golden dataset (e.g. bloom-final), compared side by side.", C.s3]];
  notes.forEach(([h, t, col], i) => {
    const y = 1.4 + i * 1.2;
    s.addShape(pres.shapes.OVAL, { x: 5.95, y: y + 0.05, w: 0.26, h: 0.26, fill: { color: col }, line: { type: "none" } });
    s.addText([{ text: h, options: { bold: true, fontSize: 12.5, breakLine: true } }, { text: t, options: { fontSize: 10.5 } }],
      { x: 6.35, y, w: 3.15, h: 1.1, fontFace: BODY, color: C.ink, valign: "top", margin: 0, isTextBox: true });
  });
  s.addNotes("Live at the defense: open the bloom-production project, click the latest trace from the demo question, expand citation_check, then show the bloom-final experiment.");
}

// 12 ── Real data lessons ────────────────────────────────────────────
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, "What broke on real data, and what I learned", "Demo data passed every test; my own exports didn't");
  const L = [["Timezones", "Apple Health stamped everything +05:00 (the phone's zone at export) → workouts 4 h off, dedupe failed. Now one HOME_TZ for all sources.", C.s1],
    ["Same event, 3 apps", "Mywellness mirrors the Watch (66 walks) and Withings (220 readings); the Watch re-records gym visits (55). Cross-source dedupe after every import.", C.s2],
    ["Format drift", "Newer iOS writes VaginalBleeding* instead of MenstrualFlow*: 0 of 202 cycle records imported until fixed.", C.s3],
    ["Lenient self-check", "The in-graph citation judge passed 95 % of answers; the offline eval found 22 % unsupported citations → per-claim judge.", C.terra],
    ["Over-eager goals", "“How should I adjust training this week?” triggered goal approval → stricter triage + a negative golden example.", C.sage],
    ["Evidence ≠ popular belief", "“Fasted training is bad for women” is not settled in the literature; the Skill makes the coach say so.", C.rose]];
  L.forEach(([h, t, col], i) => {
    const x = 0.5 + (i % 2) * 4.55, y = 1.4 + Math.floor(i / 2) * 1.22;
    card(s, x, y, 4.45, 1.1, C.white);
    s.addShape(pres.shapes.OVAL, { x: x + 0.15, y: y + 0.17, w: 0.26, h: 0.26, fill: { color: col }, line: { type: "none" } });
    s.addText([{ text: h, options: { bold: true, fontSize: 12.5, breakLine: true } }, { text: t, options: { fontSize: 10, color: C.ink } }],
      { x: x + 0.55, y: y + 0.1, w: 3.75, h: 0.92, fontFace: BODY, color: C.ink, valign: "top", margin: 0, isTextBox: true });
  });
}

// 13 ── Conclusions ──────────────────────────────────────────────────
{
  const s = pres.addSlide(); s.background = { color: C.dark };
  logo(s, 8.35, 0.4, 0.38);
  title(s, "Conclusions", null, true);
  const cols = [["What works", "Safety routing 100 % on the golden set · cited, evidence-graded answers · real data from 4 sources in one timeline · goals only with approval · deployed behind a password on Railway"],
    ["Trade-offs I chose", "Quality over latency (citation loop, gpt-4.1 writer) · calendar-based cycle phases flagged low-confidence instead of guessing · local SQLite for privacy"],
    ["Next", "Harder red-flag cases (indirect, multilingual) · real users with PCOS · wearable temperature/LH for ovulation · per-user accounts"]];
  cols.forEach(([h, t], i) => {
    const x = 0.5 + i * 3.07;
    card(s, x, 1.3, 2.9, 3.0, "2B3A32", "2B3A32");
    s.addText([{ text: h, options: { bold: true, fontSize: 15, color: C.sand, breakLine: true } }, { text: t, options: { fontSize: 12, color: "E8EDE9" } }],
      { x: x + 0.2, y: 1.45, w: 2.5, h: 2.75, fontFace: BODY, valign: "top", margin: 0, paraSpaceAfter: 4, isTextBox: true });
  });
  s.addText("Thank you · Questions?", { x: 0.5, y: 4.6, w: 9, h: 0.45, fontFace: HEAD, fontSize: 20, italic: true, color: C.white, margin: 0, isTextBox: true });
}

const out = path.join(__dirname, "Bloom_final_presentation.pptx");
pres.writeFile({ fileName: out }).then(() => console.log("wrote " + out + " (results from: " + FINAL + ")"));
