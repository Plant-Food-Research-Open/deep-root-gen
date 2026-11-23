// Drive the dashboard in a real headless Chrome with Playwright.
//
//   NODE_PATH=<dir containing playwright-core> node scripts/local/dash_browser_check.mjs \
//       http://127.0.0.1:18003 <output-dir>
//
// Uses only repository synthetic examples. Records the visible feedback text,
// downloads and screenshots in <output-dir>/browser-receipt.json.
// Set STEPS to select journeys. DRG_SNPE_TARGETS can supply synthetic values
// matching a different served schema. DRG_SNPE_REQUESTS_URL can point to an
// isolated test service's GET endpoint returning its recorded prediction bodies.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";

const require = createRequire(import.meta.url);
const [base = "http://127.0.0.1:8000", outdir = "browser-check"] = process.argv.slice(2);
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "../..");
const example = (name) => path.join(root, "examples", name);
fs.mkdirSync(outdir, { recursive: true });

const sim = "simulation-root-system-page";
const deploymentsPage = "deployments-root-system-page";
const dashId = (index, type) => `[id='${JSON.stringify({ index, type })}']`;
const receipt = [];
const record = (step, data) => { receipt.push({ step, ...data }); console.log(step, JSON.stringify(data)); };

async function visit(page, route) {
  const response = await page.goto(`${base}${route}`, { waitUntil: "networkidle" });
  assert(response?.ok(), `Page ${route} returned HTTP ${response?.status()}`);
}

async function visibleText(locator, expected, timeout = 30000) {
  const matching = locator.filter({ hasText: expected });
  await matching.waitFor({ timeout });
  return (await matching.innerText()).replace(/\s+/g, " ").trim();
}

async function closeToast(page, id) {
  await page.locator(`#${id} .btn-close`).click();
  await page.locator(`#${id}`).waitFor({ state: "hidden" });
}

function readCsv(file, columns) {
  const text = fs.readFileSync(file, "utf8");
  const field = /(?:"((?:[^"]|"")*)"|([^,"\r\n]*))(,|\r?\n|$)/y;
  const parsed = [];
  let row = [];
  while (field.lastIndex < text.length) {
    const match = field.exec(text);
    assert(match, `Malformed CSV in ${file}`);
    row.push(match[1]?.replaceAll('""', '"') ?? match[2]);
    if (match[3] !== ",") {
      parsed.push(row);
      row = [];
    }
  }
  if (row.length) parsed.push([...row, ""]);
  const [header, ...rows] = parsed;
  assert(header?.length && rows.length, `CSV ${file} has no data rows`);
  assert(columns.every((name) => header.includes(name)), `CSV ${file} missing columns: ${columns.join(", ")}`);
  assert(rows.every((values) => values.length === header.length), `CSV ${file} has incomplete rows`);
  return { header, rows };
}

async function saveDownload(page, button) {
  const [download] = await Promise.all([
    page.waitForEvent("download", { timeout: 135000 }),
    button.click(),
  ]);
  const file = path.join(outdir, download.suggestedFilename());
  await download.saveAs(file);
  return { file, filename: download.suggestedFilename() };
}

function numeric(value) {
  return Boolean(value?.trim()) && Number.isFinite(Number(value));
}

async function simulation(page) {
  await visit(page, "/");
  const result = page.locator(`#${sim}-results-toast`);
  const table = page.locator(".dash-spreadsheet tbody tr");
  await page.locator(`${dashId(`${sim}-upload-param-file-button`, `${sim}-simulation`)} input[type=file]`)
    .setInputFiles(example("synthetic_minimal.json"));
  record("simulation.load", {
    toast: await visibleText(page.locator(`#${sim}-load-toast`), "Loaded synthetic_minimal.json"),
  });

  // Invalid: a fine-root fraction target without allocation controls.
  const ratio = page.locator(dashId(`${sim}-root-ratio-length-input`, `${sim}-parameters`));
  await ratio.fill("0.5");
  await page.getByRole("button", { name: "Check setup" }).click();
  record("simulation.invalid_target", {
    toast: await visibleText(result, /Check the form\. Nothing was submitted\..*allocation_controls/s),
  });
  await closeToast(page, `${sim}-results-toast`);
  await ratio.fill("");

  const before = await table.count();
  await page.getByRole("button", { name: "Check setup" }).click();
  record("simulation.check_setup", { toast: await visibleText(result, "Setup is valid. Nothing was submitted.") });
  await closeToast(page, `${sim}-results-toast`);
  const after = await table.count();
  record("simulation.no_row_after_check", { rows_before: before, rows_after: after });
  assert.equal(after, before, "Check setup added a run row");

  await page.getByRole("button", { name: "Run procedure" }).click();
  const toast = await visibleText(result, /(?:Already queued|Queued): simulation run [a-f0-9-]{36}/i);
  record("simulation.run", { toast });
  const runId = toast.match(/simulation run ([a-f0-9-]{36})/i)[1];
  const row = table.filter({ hasText: runId });
  const state = await visibleText(row, /\b(?:Completed|Failed|Crashed|Cancelled)\b/, 240000);
  record("simulation.state_column", { row: state });
  assert.match(state, /\bCompleted\b/, `Simulation did not complete: ${state}`);
  await page.screenshot({ path: path.join(outdir, "simulation.png"), fullPage: true });
}

async function architecture(page) {
  await visit(page, "/architecture-search");
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
  await page.locator("#architecture-message").filter({ hasText: "Setup is valid. Nothing was submitted." }).waitFor();
  record("architecture.check_setup", { message: await page.locator("#architecture-message").innerText() });

  await page.getByRole("button", { name: "Run search" }).click();
  await page.locator("#architecture-message").filter({ hasText: /(?:Queued|Already queued).*run [a-f0-9-]{36}/i }).waitFor();
  record("architecture.run", { message: await page.locator("#architecture-message").innerText() });
  const state = await visibleText(page.locator("#architecture-state"), /Completed|Failed|Crashed|Cancelled/, 240000);
  record("architecture.state", { state });
  assert.match(state, /^Completed ·/, `Architecture Search has no completed results: ${state}`);

  const { file, filename } = await saveDownload(page, page.getByRole("button", { name: "Best configuration" }));
  const best = JSON.parse(fs.readFileSync(file, "utf8"));
  assert(best.parameters.primary_root_count >= 2 && best.parameters.primary_root_count <= 4);
  assert([0, 1].includes(best.random_seed));
  record("architecture.best_download", {
    file: filename, primary_root_count: best.parameters.primary_root_count,
    random_seed: best.random_seed,
  });
  const trialsFile = await saveDownload(page, page.getByRole("button", { name: "Trial table" }));
  const trials = readCsv(trialsFile.file, ["trial", "state", "loss", "primary_root_count"]);
  assert.equal(trials.rows.length, 5);
  assert(trials.rows.some((values) => numeric(values[trials.header.indexOf("loss")])));
  record("architecture.trials_download", { file: trialsFile.filename, rows: trials.rows.length });
  await page.screenshot({ path: path.join(outdir, "architecture-search.png"), fullPage: true });
}

async function deployments(page) {
  await visit(page, "/deployments");
  const status = page.locator(`#${deploymentsPage}-service-status li`);
  await status.nth(4).waitFor({ timeout: 60000 });
  const statuses = await status.allInnerTexts();
  record("deployments.status", { statuses });
  assert.equal(statuses.length, 5, "Expected five model service status rows");
  assert(statuses.every((value) => /: serving\b/.test(value)), "At least one model service is unavailable");

  const input = (name, section) => page.locator(dashId(`${deploymentsPage}-${name}`, `${deploymentsPage}-${section}`));
  const result = page.locator(`#${deploymentsPage}-results-toast`);
  const cases = [
    ["optimisation", "Optimisation calibrator", ["value"], ["value"], async () => {
      await input("n-trials-input", "deployments").fill("1");
    }],
    ["sensitivity_analysis", "Sensitivity calibrator", ["name", "ST", "ST_conf"], ["ST", "ST_conf"], async () => {
      const search = input("parameter-names-dropdown", "deployments").locator("input");
      await search.fill("Primary count");
      await search.press("Enter");
    }],
    ["abc", "Bayesian calibrator", ["t"], ["t"], async () => {
      await input("t-input", "deployments").fill("0");
    }],
    ["surrogate", "Emulation calibrator", ["discrepancy", "lower_bound", "upper_bound"],
      ["discrepancy", "lower_bound", "upper_bound"], async () => {
        await input("trained-features-json", "parameters").fill(
          process.env.DRG_SURROGATE_ROW || '{"min_primary_length":19.5,"max_primary_length":28.5}');
      }],
    ["snpe", "Neural density calibrator", ["primary_root_count"], ["primary_root_count"]],
  ];
  for (const [task, label, required, finite, prepare] of cases) {
    try {
      await prepare?.();
      const button = page.getByRole("button", { name: label, exact: true });
      const download = task === "snpe" ? await uploadedSnpe(page, button) : await saveDownload(page, button);
      const { header, rows } = readCsv(download.file, required);
      assert(rows.every((row) => finite.every((name) => numeric(row[header.indexOf(name)]))),
        `${task} returned non-finite numeric results`);
      if (task === "optimisation" || task === "surrogate") assert.equal(rows.length, 1);
      if (task === "sensitivity_analysis") {
        assert.deepEqual(rows.map((row) => row[header.indexOf("name")]), ["primary_root_count"]);
      }
      if (task === "abc") assert(rows.every((row) => Number(row[header.indexOf("t")]) === 0));
      const toast = await visibleText(result, new RegExp(`Downloaded ${rows.length} rows from the ${task} service`));
      record(`deployments.${task}`, { filename: download.filename, columns: header, rows: rows.length, toast });
      await closeToast(page, `${deploymentsPage}-results-toast`);
    } catch (error) {
      recordError(`deployments.${task}`, error);
      if (await result.isVisible()) {
        record(`deployments.${task}.feedback`, { text: await result.innerText() });
        await closeToast(page, `${deploymentsPage}-results-toast`);
      }
    }
  }
  await page.screenshot({ path: path.join(outdir, "deployments.png"), fullPage: true });
}

async function snpeRequests(url) {
  if (!url) return null;
  const response = await fetch(url, { signal: AbortSignal.timeout(5000) });
  assert(response.ok, `SNPE request capture returned HTTP ${response.status}`);
  const body = await response.json();
  const requests = Array.isArray(body) ? body : body.requests;
  assert(Array.isArray(requests), "SNPE capture must return an array of request bodies");
  return requests;
}

async function uploadedSnpe(page, button) {
  const targets = Object.entries(JSON.parse(process.env.DRG_SNPE_TARGETS || '{"total_length":50}'));
  assert(targets.length && targets.every(([name, value]) => /^[a-zA-Z0-9_]+$/.test(name) && Number.isFinite(value)),
    "DRG_SNPE_TARGETS must map statistic names to finite synthetic values");
  const pageId = deploymentsPage;
  const source = page.locator(`#${pageId}-snpe-source`);
  const preview = page.locator(`#${pageId}-snpe-preview`);
  const firstManual = page.locator(dashId(targets[0][0], `${pageId}-summary_statistics`));
  const different = String(targets[0][1] === 0 ? 1 : 0);
  await source.getByRole("radio", { name: /manual/i }).check();
  await firstManual.fill(different);

  const csv = ["statistic_name,statistic_value", ...targets.map(([name, value]) => `${name},${value}`)].join("\n");
  const upload = dashId(`${pageId}-upload-obs-data-file-button`, `${pageId}-summary_data`);
  await source.getByRole("radio", { name: /upload/i }).check();
  await page.locator(`${upload} input[type=file]`).setInputFiles({
    name: "snpe-acceptance-targets.csv", mimeType: "text/csv", buffer: Buffer.from(csv),
  });
  for (const [name, value] of targets) {
    const row = preview.getByRole("row").filter({ has: page.getByRole("rowheader", { name, exact: true }) });
    await row.getByRole("cell", { name: String(value), exact: true }).waitFor();
  }

  const captureUrl = process.env.DRG_SNPE_REQUESTS_URL;
  const before = await snpeRequests(captureUrl);
  const [request, download] = await Promise.all([
    page.waitForRequest((request) => request.url().endsWith("/_dash-update-component")
      && request.method() === "POST"
      && (request.postDataJSON()?.changedPropIds || []).some((id) => id.includes("call-snpe-button"))),
    saveDownload(page, button),
  ]);
  const state = request.postDataJSON().state;
  const stateValue = (suffix) => state.find((entry) => entry.id === `${pageId}-${suffix}`)?.value;
  assert.equal(stateValue("snpe-source"), "upload");
  const manual = state.flat().find((entry) => entry.id?.index === targets[0][0] && entry.property === "value");
  assert.equal(manual?.value, Number(different), "Prediction did not retain the deliberately different manual value");
  const uploadedRows = stateValue("snpe-target-upload")?.values;
  assert(uploadedRows, "Prediction callback did not receive the uploaded target store");
  assert.deepEqual(Object.fromEntries(uploadedRows.map((row) => [row.statistic_name, row.statistic_value])),
    Object.fromEntries(targets));
  const info = stateValue("snpe-model-info");
  assert(info?.tag, "Prediction callback did not receive the selected model tag");
  let captured = null;
  if (before) {
    const after = await snpeRequests(captureUrl);
    assert.equal(after.length, before.length + 1, "Expected one SNPE prediction at the test service");
    captured = after.at(-1);
    assert.equal(captured.model_tag, info.tag);
    assert.deepEqual(captured.summary_statistics, info.input_schema.statistic_names.map((name) =>
      ({ statistic_name: name, statistic_value: Object.fromEntries(targets)[name] })));
  }
  record("deployments.snpe_conditioning", {
    uploadedRows, deliberately_different_manual_value: manual.value,
    model_tag: info.tag, observed_service_body: captured,
  });
  return download;
}

let failed = false;
function recordError(name, error) {
  failed = true;
  record(`${name}.error`, { error: String(error.message || error).split("\n")[0] });
}

const errors = [];
const journeys = new Map([["simulation", simulation], ["architecture", architecture], ["deployments", deployments]]);
const steps = (process.env.STEPS ?? [...journeys.keys()].join(",")).split(",").map((step) => step.trim());
let browser;
try {
  assert(steps.every((step) => journeys.has(step)), `Unknown STEPS selection: ${steps.join(",")}`);
  const { chromium } = require("playwright-core");
  browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || "/usr/bin/google-chrome", headless: true });
  for (const name of steps) {
    const context = await browser.newContext({ acceptDownloads: true, viewport: { width: 1400, height: 1000 } });
    try {
      const page = await context.newPage();
      page.on("response", (response) => {
        if (response.url().includes("_dash-update-component") && response.status() >= 500) {
          errors.push({ journey: name, status: response.status() });
        }
      });
      try {
        await journeys.get(name)(page);
      } catch (error) {
        recordError(name, error);
        await page.screenshot({ path: path.join(outdir, `${name}-error.png`), fullPage: true })
          .catch((error) => recordError(`${name}.screenshot`, error));
      }
    } finally {
      await context.close();
    }
  }
} catch (error) {
  recordError("browser", error);
} finally {
  await browser?.close().catch((error) => recordError("browser.close", error));
  record("callback_http_5xx", { count: errors.length, responses: errors });
  fs.writeFileSync(path.join(outdir, "browser-receipt.json"), JSON.stringify(receipt, null, 1));
  process.exitCode = failed || errors.length ? 1 : 0;
}
