import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { mkdirSync } from "node:fs";
import path from "node:path";
import assert from "node:assert/strict";

mkdirSync("artifacts", { recursive: true });
const base = "http://127.0.0.1:8128";
const server = spawn(
  path.resolve(".venv/Scripts/python.exe"),
  ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8128"],
  {
    windowsHide: true,
    env: {
      ...process.env,
      DATABASE_URL: `sqlite:///./artifacts/landing-${Date.now()}.db`,
      GROQ_API_KEY: "",
      JIRA_API_TOKEN: "",
    },
    stdio: ["ignore", "pipe", "pipe"],
  },
);
let logs = "",
  browser;
server.stdout.on("data", (chunk) => (logs += chunk));
server.stderr.on("data", (chunk) => (logs += chunk));
try {
  for (let attempt = 0; attempt < 100; attempt++) {
    if (
      await fetch(base + "/api/health")
        .then((r) => r.ok)
        .catch(() => false)
    )
      break;
    if (server.exitCode !== null || attempt === 99) throw new Error(logs);
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  browser = await chromium.launch({
    executablePath:
      process.env.CHROME_PATH ||
      "C:/Program Files/Google/Chrome/Application/chrome.exe",
    headless: true,
  });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
  });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("response", (response) => {
    if (response.status() >= 400)
      errors.push(response.url() + ": " + response.status());
  });
  await page.goto(base);
  await page.getByRole("heading", { name: /Great meeting/ }).waitFor();
  await page.getByRole("tab", { name: "Summary", exact: true }).click();
  assert.match(
    await page.locator("#preview-content").innerText(),
    /A launch plan/,
  );
  await page
    .getByRole("tab", { name: "Summary", exact: true })
    .press("ArrowRight");
  assert.equal(
    await page
      .getByRole("tab", { name: /Decisions/ })
      .getAttribute("aria-selected"),
    "true",
  );
  await page.getByRole("tab", { name: /Action items/ }).click();
  await page.locator('[data-view="after"]').click();
  assert.equal(await page.locator(".clarity-panel").isVisible(), true);
  assert.equal(await page.locator(".conversation-panel").isVisible(), false);
  await page.locator('[data-view="before"]').click();
  await page
    .locator('summary').filter({ hasText: 'Where does my meeting data go?' })
    .click();
  assert.equal(await page.locator("details[open]").count(), 1);
  await page.screenshot({
    path: "artifacts/landing-desktop.png",
    fullPage: true,
  });
  for (const width of [390, 320, 768]) {
    await page.setViewportSize({ width, height: 844 });
    assert.ok(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      `Overflow at ${width}px`,
    );
    await page.locator('[data-view="after"]').click();
    assert.ok(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      `Demo overflow at ${width}px`,
    );
    if (width === 390)
      await page.screenshot({
        path: "artifacts/landing-mobile.png",
        fullPage: true,
      });
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole("link", { name: /Analyze your first meeting/ }).click();
  await page.locator("#meeting-dialog[open]").waitFor();
  assert.equal(new URL(page.url()).pathname, "/app");
  await page.goto(base);
  await page
    .getByRole("link", { name: /Explore a full sample meeting/ })
    .click();
  await page.locator("h1").filter({ hasText: "Release readiness" }).waitFor();
  assert.match(
    await page.locator(".sample-notice").innerText(),
    /Example meeting/,
  );
  const direct = await browser.newContext();
  const directPage = await direct.newPage();
  await directPage.goto(base + "/app");
  await directPage.locator("#content h1").waitFor();
  assert.equal(
    (await direct.request.get(base + "/api/settings")).status(),
    200,
  );
  await direct.close();
  assert.deepEqual(errors, []);
  console.log(
    "Landing verified: tabs and keyboard controls, comparison, FAQ, 320/390/768px layout, upload CTA, sample CTA, direct workspace sessions, no browser errors.",
  );
} finally {
  if (browser) await browser.close();
  server.kill();
}
