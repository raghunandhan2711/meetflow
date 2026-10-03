import { chromium } from "playwright";
import { readFileSync } from "node:fs";
import assert from "node:assert/strict";

const base = "http://127.0.0.1:8000";
const secret = readFileSync(".env", "utf8").match(
  /^GROQ_API_KEY=['"]?([^'"\r\n]+)/m,
)?.[1];
assert.ok(secret, "Backend credential is not configured.");
const browser = await chromium.launch({
  executablePath:
    process.env.CHROME_PATH ||
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
  headless: true,
});
let meetingId;
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
});
try {
  const page = await context.newPage();
  const unsafeRequests = [];
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("request", (request) => {
    if (
      request.url().includes("api.groq.com") ||
      JSON.stringify(request.headers()).includes(secret) ||
      (request.postData() || "").includes(secret)
    )
      unsafeRequests.push(
        "Browser exposed provider credential or called provider directly.",
      );
  });
  assert.equal(
    (await context.request.get(base + "/api/meetings")).status(),
    401,
  );
  await page.goto(base);
  await page
    .getByRole("button", { name: "New meeting", exact: true })
    .first()
    .waitFor();
  const cookie = (await context.cookies()).find(
    (cookie) => cookie.name === "meetflow_session",
  );
  assert.ok(cookie?.httpOnly && cookie.sameSite === "Strict");
  assert.ok(
    !(await page.evaluate(() => document.cookie)).includes("meetflow_session"),
  );
  assert.ok(!(await page.content()).includes(secret));
  const bundle = await context.request.get(base + "/static/workspace.js");
  assert.ok(!(await bundle.text()).includes(secret));
  for (const path of ["/docs", "/redoc", "/openapi.json", "/.env"])
    assert.equal((await context.request.get(base + path)).status(), 404);
  await page.locator("#new-top").click();
  await page.getByRole("tab", { name: "Paste transcript" }).click();
  await page
    .locator("#meeting-title")
    .fill("Verification: live private AI analysis");
  await page
    .locator("#transcript-input")
    .fill(
      "Alex: We decided to delay the release until Friday. I will fix the login bug by Thursday.\nSam: I will test the authentication module after Alex finishes.\nAlex: We agreed to use PostgreSQL for meeting history.",
    );
  const saved = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/meetings") &&
      response.request().method() === "POST",
  );
  await page.locator("#submit-meeting").click();
  meetingId = (await (await saved).json()).id;
  await page
    .locator("h1")
    .filter({ hasText: "Verification: live private AI analysis" })
    .waitFor();
  await page
    .locator(".detail-meta .pill")
    .filter({ hasText: "Analyzed" })
    .waitFor({ timeout: 120000 });
  const meeting = await context.request.get(
    base + "/api/meetings/" + meetingId,
  );
  const text = await meeting.text();
  assert.ok(!text.includes(secret));
  const data = JSON.parse(text);
  assert.equal(data.status, "ready");
  assert.ok(
    data.summary && data.decisions.length >= 1 && data.tasks.length >= 2,
  );
  assert.ok(data.tasks.some((task) => task.owner.toLowerCase() === "alex"));
  await page.screenshot({
    path: "artifacts/16-live-private-analysis.png",
    fullPage: true,
  });
  assert.deepEqual(unsafeRequests, []);
  assert.deepEqual(pageErrors, []);
  console.log(
    "Live website verification passed: real AI summary/decisions/tasks, HttpOnly session, private endpoints, no browser key exposure.",
  );
} finally {
  if (meetingId) {
    for (let attempt = 0; attempt < 20; attempt++) {
      const removed = await context.request.delete(
        base + "/api/meetings/" + meetingId,
      );
      if (removed.status() !== 409) break;
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
  }
  await browser.close();
}
