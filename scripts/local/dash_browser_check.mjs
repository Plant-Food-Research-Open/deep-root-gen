// Drive the dashboard in a real headless Chrome with Playwright.
//
//   NODE_PATH=<dir containing playwright-core> node scripts/local/dash_browser_check.mjs \
//       http://127.0.0.1:18003 <output-dir>
//
// Uses only repository synthetic examples. Records the visible feedback text,
// downloads and screenshots in <output-dir>/browser-receipt.json.
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright-core");
const [base = "http://127.0.0.1:8000", outdir = "browser-check"] = process.argv.slice(2);
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "../..");
const example = (name) => path.join(root, "examples", name);
fs.mkdirSync(outdir, { recursive: true });

const sim = "simulation-root-system-page";
const dashId = (index, type) => `[id='${JSON.stringify({ index, type })}']`;
const receipt = [];
const record = (step, data) => { receipt.push({ step, ...data }); console.log(step, JSON.stringify(data)); };

const lastText = {};
async function toastText(page, id) {
  // The same toast element is reused; wait until it shows a new message.
  const toast = page.locator(`#${id}`);
  const deadline = Date.now() + 60000;
  let text = "";
  while (Date.now() < deadline) {
    if (await toast.isVisible()) {
      text = (await toast.innerText()).replace(/\s+/g, " ").trim();
      if (text && text !== lastText[id]) break;
    }
    await page.waitForTimeout(250);
  }
  lastText[id] = text;
  return text;
}

async function closeToast(page, id) {
  const close = page.locator(`#${id} .btn-close`);
  if (await close.count()) await close.first().click();
}

async function simulation(page) {
  await page.goto(`${base}/`, { waitUntil: "networkidle" });
  await page.locator(`${dashId(`${sim}-upload-param-file-button`, `${sim}-simulation`)} input[type=file]`)
    .setInputFiles(example("synthetic_minimal.json"));
  record("simulation.load", { toast: await toastText(page, `${sim}-load-toast`) });

  // Invalid: a fine-root fraction target without allocation controls.
  const ratio = page.locator(dashId(`${sim}-root-ratio-length-input`, `${sim}-parameters`));
  await ratio.fill("0.5");
  await page.getByRole("button", { name: "Check setup" }).click();
  record("simulation.invalid_target", { toast: await toastText(page, `${sim}-results-toast`) });
  await closeToast(page, `${sim}-results-toast`);
  await ratio.fill("");

  const before = await page.locator(".dash-spreadsheet tbody tr").count();
  await page.getByRole("button", { name: "Check setup" }).click();
  record("simulation.check_setup", { toast: await toastText(page, `${sim}-results-toast`) });
  await closeToast(page, `${sim}-results-toast`);
  record("simulation.no_row_after_check", {
    rows_before: before, rows_after: await page.locator(".dash-spreadsheet tbody tr").count(),
  });

  await page.getByRole("button", { name: "Run procedure" }).click();
  record("simulation.run", { toast: await toastText(page, `${sim}-results-toast`) });
  const row = page.locator(".dash-spreadsheet tbody tr").last();
  const deadline = Date.now() + 240000;
  let state = "";
  while (Date.now() < deadline) {
    state = (await row.innerText()).replace(/\s+/g, " ");
    if (/Completed|Failed|Crashed/.test(state)) break;
    await page.waitForTimeout(3000);
  }
  record("simulation.state_column", { row: state });
  await page.screenshot({ path: path.join(outdir, "simulation.png"), fullPage: true });
}

async function architecture(page) {
  await page.goto(`${base}/architecture-search`, { waitUntil: "networkidle" });
  await page.locator("#architecture-upload input[type=file]").setInputFiles(example("synthetic_minimal.json"));
  await page.locator("#architecture-model-status").filter({ hasText: "Schema 4" }).waitFor();
  record("architecture.load", { status: await page.locator("#architecture-model-status").innerText() });

  const row = page.locator("#architecture-controls tbody tr").filter({ hasText: "Primary root count" });
  for (const [column, value] of [["lower", "2"], ["upper", "4"]]) {
    await row.locator(`td[data-dash-column=${column}]`).click();
    await page.keyboard.type(value);
    await page.keyboard.press("Enter");
  }
  // Spreadsheet-style paste: tab-separated header and values.
  await page.locator("#architecture-targets").fill("statistic_name\tstatistic_value\nroot_number\t3\n");
  await page.locator("#architecture-trials").fill("5");
  await page.locator("#architecture-startup").fill("2");
  await page.getByRole("button", { name: "Check setup" }).click();
  await page.locator("#architecture-message").filter({ hasText: "Nothing was submitted" }).waitFor();
  record("architecture.check_setup", { message: await page.locator("#architecture-message").innerText() });

  await page.getByRole("button", { name: "Run search" }).click();
  await page.locator("#architecture-message").filter({ hasText: /Queued|Already queued|Prefect/ }).waitFor();
  record("architecture.run", { message: await page.locator("#architecture-message").innerText() });
  await page.locator("#architecture-state").filter({ hasText: /Completed|Failed|Crashed/ })
    .waitFor({ timeout: 240000 });
  record("architecture.state", { state: await page.locator("#architecture-state").innerText() });

  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Best configuration" }).click(),
  ]);
  const file = path.join(outdir, download.suggestedFilename());
  await download.saveAs(file);
  const best = JSON.parse(fs.readFileSync(file, "utf8"));
  record("architecture.best_download", {
    file: download.suggestedFilename(), primary_root_count: best.parameters.primary_root_count,
    random_seed: best.random_seed,
  });
  await page.screenshot({ path: path.join(outdir, "architecture-search.png"), fullPage: true });
}

async function deployments(page) {
  await page.goto(`${base}/deployments`, { waitUntil: "networkidle" });
  await page.locator("#deployments-root-system-page-service-status li").first().waitFor({ timeout: 60000 });
  record("deployments.status", { text: await page.locator("#deployments-root-system-page-service-status").innerText() });
  await page.screenshot({ path: path.join(outdir, "deployments.png"), fullPage: true });
}

const browser = await chromium.launch({ executablePath: "/usr/bin/google-chrome", headless: true });
const context = await browser.newContext({ acceptDownloads: true, viewport: { width: 1400, height: 1000 } });
const page = await context.newPage();
const errors = [];
page.on("response", (r) => { if (r.url().includes("_dash-update-component") && r.status() >= 500) errors.push(r.status()); });
const steps = (process.env.STEPS || "simulation,architecture,deployments").split(",");
try {
  for (const [name, fn] of [["simulation", simulation], ["architecture", architecture], ["deployments", deployments]]) {
    if (steps.includes(name)) {
      try { await fn(page); } catch (error) {
        record(`${name}.error`, { error: String(error.message).split("\n")[0] });
        await page.screenshot({ path: path.join(outdir, `${name}-error.png`), fullPage: true });
      }
    }
  }
} finally {
  record("callback_http_5xx", { count: errors.length });
  fs.writeFileSync(path.join(outdir, "browser-receipt.json"), JSON.stringify(receipt, null, 1));
  await browser.close();
}
