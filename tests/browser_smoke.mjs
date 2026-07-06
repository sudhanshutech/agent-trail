// Browser smoke test: start the server, render the demo trail in headless
// Chrome, and assert the product actually draws. Needs puppeteer-core
// (npm i puppeteer-core) and CHROME_PATH pointing at a Chrome/Chromium binary.
import { spawn } from "node:child_process";
import puppeteer from "puppeteer-core";

const PORT = 7899;
const chrome = process.env.CHROME_PATH;
if (!chrome) {
  console.error("Set CHROME_PATH to a Chrome or Chromium binary");
  process.exit(2);
}

const root = new URL("..", import.meta.url).pathname;
const server = spawn("python3", ["server.py", "--port", String(PORT)], {
  cwd: root, stdio: "ignore",
});

let up = false;
for (let i = 0; i < 50 && !up; i++) {
  try { up = (await fetch(`http://127.0.0.1:${PORT}/api/sessions`)).ok; }
  catch { await new Promise((r) => setTimeout(r, 200)); }
}
if (!up) { server.kill(); console.error("server did not start"); process.exit(1); }

const browser = await puppeteer.launch({
  executablePath: chrome, args: ["--no-sandbox", "--disable-gpu"],
});
const page = await browser.newPage();
const pageErrors = [];
page.on("pageerror", (e) => pageErrors.push(String(e)));

await page.goto(`http://127.0.0.1:${PORT}/#s=demo.trail.jsonl`, { waitUntil: "domcontentloaded" });
await new Promise((r) => setTimeout(r, 2500));

const s = await page.evaluate(() => ({
  nodes: document.querySelectorAll(".node").length,
  edges: document.querySelectorAll(".edge").length,
  dead: document.querySelectorAll(".node.dead").length,
  prompts: document.querySelectorAll(".node.prompt .avatar").length,
  pivots: [...document.querySelectorAll(".badge")].filter((t) => t.textContent.includes("pivot")).length,
  scrubMax: +document.getElementById("scrub").max,
}));

await browser.close();
server.kill();

function fail(msg) {
  console.error("FAIL:", msg, "\nstate:", JSON.stringify(s));
  process.exit(1);
}
if (pageErrors.length) fail("page errors: " + pageErrors.join("; "));
if (s.nodes < 20) fail("expected at least 20 rendered nodes");
if (s.edges < s.nodes - 1) fail("expected an edge per non-root node");
if (s.dead < 1) fail("demo's abandoned attempt should render as a dead branch");
if (s.pivots < 1) fail("demo's convergence should render a pivot badge");
if (s.prompts < 1) fail("prompt node should render a user avatar");
if (s.scrubMax < 20) fail("replay scrubber should cover all events");
console.log("browser smoke OK:", JSON.stringify(s));
