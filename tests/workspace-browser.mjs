import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { mkdirSync } from "node:fs";
import path from "node:path";
import assert from "node:assert/strict";

mkdirSync("artifacts", { recursive: true });
const port = 8127,
  base = `http://127.0.0.1:${port}`;
const server = spawn(
  path.resolve(".venv/Scripts/python.exe"),
  [
    "-m",
    "uvicorn",
    "app.main:app",
    "--host",
    "127.0.0.1",
    "--port",
    String(port),
  ],
  {
    cwd: process.cwd(),
    windowsHide: true,
    env: {
      ...process.env,
      DATABASE_URL: `sqlite:///./artifacts/workspace-${Date.now()}.db`,
      GROQ_API_KEY: "",
      JIRA_API_TOKEN: "",
      TRANSCRIPTION_PROVIDER: "local",
      DIARIZATION_ENABLED: "false",
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
        .then((response) => response.ok)
        .catch(() => false)
    )
      break;
    if (server.exitCode !== null) throw new Error(logs);
    await new Promise((resolve) => setTimeout(resolve, 250));
    if (attempt === 99) throw new Error(logs);
  }
  browser = await chromium.launch({
    executablePath:
      process.env.CHROME_PATH ||
      "C:/Program Files/Google/Chrome/Application/chrome.exe",
    headless: true,
    args: [
      "--use-fake-ui-for-media-stream",
      "--use-fake-device-for-media-stream",
    ],
  });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    permissions: ["microphone"],
  });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(base + '/app');
  await page.getByText("Ready for your first meeting.").waitFor();
  assert.match(await page.title(), /AI-Powered Meeting Analysis/);
  assert.equal(await page.locator('[data-nav="settings"]').count(), 0);
  await page.screenshot({ path: "artifacts/10-dashboard.png", fullPage: true });
  await page.locator("#sample-button").click();
  await page.locator("h1").filter({ hasText: "Release readiness" }).waitFor();
  await page.screenshot({
    path: "artifacts/11-meeting-analysis.png",
    fullPage: true,
  });
  await page.getByRole("tab", { name: "Transcript", exact: true }).click();
  await page.locator(".transcript-entry").first().waitFor();
  assert.equal(await page.locator(".transcript-entry").count(), 5);
  await page
    .getByRole("button", { name: "Rename Nishan", exact: true })
    .first()
    .click();
  await page.locator("#speaker-name").fill("Nishan K");
  await page.getByRole("button", { name: "Save name", exact: true }).click();
  await page.locator("#speaker-dialog").waitFor({ state: "hidden" });
  await page
    .getByRole("button", { name: "Rename Nishan K", exact: true })
    .first()
    .waitFor();
  await page.getByRole("tab", { name: "Action items" }).click();
  await page
    .getByRole("button", {
      name: "Fix refresh token reuse in authentication",
      exact: true,
    })
    .click();
  await page.locator("#task-owner").fill("Test owner");
  await page.locator('#task-dialog button[type="submit"]').click();
  await page.locator("#task-dialog").waitFor({ state: "hidden" });
  await page.getByText("Test owner", { exact: true }).waitFor();
  await page.locator(".task-check").first().click();
  await page.locator(".task-check.done").waitFor();
  await page.reload();
  await page.locator(".task-check.done").waitFor();
  await page.getByRole("button", { name: "Add task", exact: true }).click();
  await page.locator("#task-title").fill("Review database backups");
  await page.locator("#task-owner").fill("Nishan K");
  await page.locator('#task-dialog button[type="submit"]').click();
  await page.locator("#task-dialog").waitFor({ state: "hidden" });
  await page
    .getByRole("button", { name: "Review database backups", exact: true })
    .waitFor();
  const manualCard = page
    .locator(".task-card")
    .filter({ hasText: "Review database backups" });
  await manualCard.locator("select").selectOption("in_progress");
  await page
    .locator(".task-card")
    .filter({ hasText: "Review database backups" })
    .locator("select")
    .waitFor();
  assert.equal(
    await page
      .locator(".task-card")
      .filter({ hasText: "Review database backups" })
      .locator("select")
      .inputValue(),
    "in_progress",
  );
  const notes = page.waitForEvent("download");
  await page.getByRole("link", { name: "Export notes" }).click();
  assert.equal((await notes).suggestedFilename(), "meeting-notes.md");
  const csv = page.waitForEvent("download");
  await page.getByRole("link", { name: "CSV", exact: true }).click();
  assert.equal((await csv).suggestedFilename(), "action-items.csv");
  const popup = page.waitForEvent("popup");
  await page.getByRole("link", { name: "PDF report" }).click();
  const report = await popup;
  await report.getByRole("heading", { name: "Full transcript" }).waitFor();
  await report.close();
  await page
    .locator(".task-card")
    .filter({ hasText: "Review database backups" })
    .getByRole("button", { name: "Delete task: Review database backups" })
    .click();
  await page.locator("#confirm-action").click();
  await page
    .getByRole("button", { name: "Review database backups", exact: true })
    .waitFor({ state: "hidden" });
  await page.locator('.sidebar [data-nav="tasks"]').click();
  await page.getByRole("button", { name: "Board view" }).click();
  await page.locator(".board-column").first().waitFor();
  assert.equal(await page.locator(".board-column").count(), 3);
  await page.screenshot({
    path: "artifacts/12-task-board.png",
    fullPage: true,
  });
  await page.locator('.sidebar [data-nav="decisions"]').click();
  await page.locator(".decision").first().waitFor();
  assert.equal(await page.locator(".decision").count(), 3);
  await page.locator('.sidebar [data-nav="meetings"]').click();
  await page.getByRole("textbox", { name: "Search meetings" }).fill("expired");
  await page.waitForTimeout(500);
  assert.equal(await page.locator(".meeting-row").count(), 1);
  await page
    .getByRole("textbox", { name: "Search meetings" })
    .fill("nonexistent");
  await page.getByText("No matching meetings.").waitFor();
  await page.locator("#new-top").click();
  await page.getByRole("tab", { name: "Paste transcript" }).click();
  await page.locator("#meeting-title").fill("Imported planning meeting");
  await page
    .locator("#transcript-input")
    .fill(
      "Alex: I will write the API documentation by Friday. We agreed to use PostgreSQL for meeting history.",
    );
  await page.locator("#submit-meeting").click();
  await page.getByText("Transcript ready.", { exact: true }).waitFor();
  await page.getByRole("tab", { name: "Transcript", exact: true }).click();
  assert.match(
    await page.locator(".raw-transcript").innerText(),
    /API documentation/,
  );
  await page.locator("#new-top").click();
  await page.getByRole("tab", { name: "Record", exact: true }).click();
  await page.locator("#record-button").click();
  await page
    .getByRole("button", { name: "Stop recording", exact: true })
    .waitFor();
  await page.waitForTimeout(1100);
  await page
    .getByRole("button", { name: "Stop recording", exact: true })
    .click();
  await page.locator("#record-preview").waitFor({ state: "visible" });
  assert.match(
    await page.locator("#record-preview").getAttribute("src"),
    /^blob:/,
  );
  await page.locator('#meeting-dialog [aria-label="Close dialog"]').click();
  {
    await page.locator("#new-top").click();
    await page.getByRole("tab", { name: "Upload audio", exact: true }).click();
    await page
      .locator("#audio-file")
      .setInputFiles("tests/fixtures/meeting.wav");
    await page
      .locator("#meeting-title")
      .fill("Actual audio transcription test");
    await page.locator("#submit-meeting").click();
    await page
      .getByText("Transcript ready.", { exact: true })
      .waitFor({ timeout: 120000 });
    await page.locator("#meeting-audio").waitFor();
    await page.getByRole("tab", { name: "Transcript", exact: true }).click();
    await page.locator(".transcript-entry").first().waitFor();
    assert.ok((await page.locator(".transcript-entry").count()) > 0);
    assert.match(
      await page
        .locator(".transcript-entry")
        .allTextContents()
        .then((lines) => lines.join(" ")),
      /login|meeting|release/i,
    );
    await page.screenshot({
      path: "artifacts/13-real-transcription.png",
      fullPage: true,
    });
  }
  await page.locator('.sidebar [data-nav="dashboard"]').click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "artifacts/14-mobile-dashboard.png",
    fullPage: true,
  });
  assert.ok(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    "Dashboard overflow",
  );
  await page
    .locator(".meeting-row")
    .filter({ hasText: "Release readiness" })
    .click();
  await page.screenshot({
    path: "artifacts/15-mobile-analysis.png",
    fullPage: true,
  });
  const taskTextWidth = await page.locator('.task-body').first().evaluate(element => element.getBoundingClientRect().width);
  assert.ok(taskTextWidth > 180, 'Mobile task text must keep a readable width beside or above its controls');
  assert.ok(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    "Meeting overflow",
  );
  assert.deepEqual(errors, []);
  console.log(
    "Website checks passed: dashboard, routing, speaker correction, task CRUD, persistence, board, decisions, search, imports, exports, PDF report, recording, audio upload/playback, real local transcription, mobile layout.",
  );
} finally {
  await browser?.close();
  server.kill();
}
