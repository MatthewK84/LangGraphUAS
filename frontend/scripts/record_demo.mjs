// Honest demo recording against a running demo-mode stack (#99).
// Start the backend with SUAS_DEMO_MODE=true (fixture weather, no keys) and
// the frontend on :3000, then: node frontend/scripts/record_demo.mjs
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const BASE = process.env.DEMO_BASE_URL ?? "http://127.0.0.1:3000";
const outDir = process.env.DEMO_OUT_DIR ?? "/workspace/demo-recording";
fs.mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1920, height: 1080 },
  locale: "en-US",
  timezoneId: "America/New_York",
  recordVideo: { dir: outDir, size: { width: 1920, height: 1080 } },
});
const page = await context.newPage();
const started = Date.now();

await page.goto(BASE, { waitUntil: "networkidle" });
await page.addStyleTag({
  content:
    "nextjs-portal, [data-nextjs-dev-indicator], [data-next-badge-root], [data-next-badge] { display: none !important; }",
});

const aircraft = page.getByLabel("Aircraft Platform");
await aircraft
  .locator("option", { hasText: "Skydio X10D" })
  .waitFor({ state: "attached" });
await page.waitForTimeout(2000);
await aircraft.selectOption("Skydio_X10D");
await page.waitForTimeout(1200);
await page.getByLabel("Latitude").fill("34.0");
await page.waitForTimeout(700);
await page.getByLabel("Longitude").fill("-80.0");
await page.waitForTimeout(1500);

const planned = page.waitForResponse(
  (response) =>
    response.url().endsWith("/api/plan") &&
    response.request().method() === "POST",
);
await page.getByRole("button", { name: "Analyze flight feasibility" }).click();
const plan = await (await planned).json();
if (plan.weather?.source !== "fixture") {
  throw new Error(`expected fixture weather, got ${plan.weather?.source}`);
}
if (
  plan.assessment?.decision !== "go" ||
  plan.assessment?.mode !== "advisory"
) {
  throw new Error(
    `expected advisory go, got ${plan.assessment?.decision} ${plan.assessment?.mode}`,
  );
}

const review = page.getByRole("region", { name: "Assessment review" });
await review.waitFor();
await page.getByText("ADVISORY GO - NOT FOR OPERATIONAL USE").waitFor();
await page.getByRole("region", { name: "Advisory: not a clearance" }).waitFor();
await page.waitForTimeout(18000);

await review.getByRole("checkbox").check();
await page.waitForTimeout(1500);
await review
  .getByRole("button", { name: "Acknowledge and generate brief" })
  .click();
const brief = page.getByRole("heading", { name: "Safety officer brief" });
await brief.waitFor();
await brief.scrollIntoViewIfNeeded();
await page.waitForTimeout(15000);

await page.getByLabel("Distance (m)").fill("500000");
await page.waitForTimeout(1500);
const planned2 = page.waitForResponse(
  (response) =>
    response.url().endsWith("/api/plan") &&
    response.request().method() === "POST",
);
await page.getByRole("button", { name: "Analyze flight feasibility" }).click();
const plan2 = await (await planned2).json();
if (plan2.assessment?.decision !== "no_go") {
  throw new Error(`expected no_go, got ${plan2.assessment?.decision}`);
}
await page.getByText("MISSION DENIED (NO-GO)").waitFor();
await page
  .getByText("Energy required exceeds usable battery capacity after reserve.")
  .waitFor();
await page.waitForTimeout(18000);

const elapsed = (Date.now() - started) / 1000;
const video = page.video();
await context.close();
await browser.close();
const raw = await video.path();
const dest = path.join(outDir, "v0.4.0-eval-demo.webm");
fs.renameSync(raw, dest);
console.log(
  JSON.stringify(
    {
      dest,
      elapsed_s: elapsed,
      plan: {
        decision: plan.assessment.decision,
        mode: plan.assessment.mode,
        energy_required_wh: plan.calculations?.energy_required_wh,
        weather: plan.weather?.source,
      },
      refusal: {
        decision: plan2.assessment.decision,
        reasons: plan2.assessment.reasons,
      },
    },
    null,
    2,
  ),
);
