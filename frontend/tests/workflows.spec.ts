import { test, expect, type Page } from "@playwright/test";
const password = process.env.E2E_PASSWORD || "WorkLens-demo-2026!";
const stamp = Date.now().toString(36);
async function login(page: Page, username: string) {
  await page.goto("/");
  await page.getByLabel("Username", { exact: true }).fill(username);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("navigation", { name: "Main navigation" }),
  ).toBeVisible();
  await expect(page.locator(".loading-skeleton")).toHaveCount(0);
}
async function nav(page: Page, name: string) {
  await page
    .getByRole("navigation")
    .getByRole("button", { name, exact: true })
    .click();
}
async function submit(page: Page, name = "Save changes") {
  await page
    .getByRole("dialog")
    .getByRole("button", { name, exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
}

test("administrator configures and synchronizes a local source, resolves identities and calculates an explainable metric", async ({
  page,
}) => {
  const external: string[] = [];
  const errors: string[] = [];
  page.on("request", (req) => {
    if (!new URL(req.url()).hostname.match(/^(127\.0\.0\.1|localhost)$/))
      external.push(req.url());
  });
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page, "admin");
  await nav(page, "Data sources");
  await page
    .getByRole("button", { name: "Connect source", exact: true })
    .click();
  await page.getByLabel("Connection name").fill(`Browser fixture ${stamp}`);
  await page.getByLabel("Projects, repositories or spaces").fill("DEMO");
  await submit(page);
  const source = page.locator(".source-card").filter({
    has: page.getByRole("heading", {
      name: `Browser fixture ${stamp}`,
      exact: true,
    }),
  });
  await source.getByRole("button", { name: "Test connection" }).click();
  await expect(page.getByRole("dialog")).toContainText(
    "No network connection was attempted",
  );
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Close", exact: true })
    .click();
  await source.getByRole("button", { name: "Sync", exact: true }).click();
  await expect(source.locator("dd").last()).toContainText("succeeded");
  // The fixture's buildbot account is unassigned. Mark service accounts explicitly;
  // remaining mappings preserve the fixture employee identity.
  const serviceRow = page
    .getByRole("row")
    .filter({ hasText: "demo-buildbot" })
    .filter({ hasText: `Browser fixture ${stamp}` });
  await expect(serviceRow).toHaveCount(1);
  await serviceRow.getByRole("button", { name: "Resolve match" }).click();
  await page
    .getByRole("dialog")
    .getByLabel("This is a service account; do not attribute it to a person")
    .check();
  await submit(page, "Resolve identity");
  await expect(serviceRow).toContainText("service");
  await nav(page, "People & teams");
  await page
    .getByRole("button", { name: "View Alex Morgan", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Calculate metrics", exact: true })
    .click();
  await submit(page, "Calculate snapshots");
  await expect(page.locator(".metric-card")).toHaveCount(7);
  await page.locator(".metric-card").first().click();
  await expect(page.getByRole("dialog")).toContainText("Formula version");
  await expect(page.getByRole("dialog")).toContainText("sample_size");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Close", exact: true })
    .click();
  await nav(page, "Reports");
  await page
    .getByLabel("Employee", { exact: true })
    .selectOption({ label: "Alex Morgan" });
  await page.getByLabel("CSV data").check();
  const downloadPromise = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Export report", exact: true })
    .click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/\.csv$/);
  const queuedResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/report-jobs/") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Queue report", exact: true }).click();
  const queued = await (await queuedResponse).json();
  expect(queued.id).toBeGreaterThan(0);
  const jobRow = page.locator(`tr[data-report-id="${queued.id}"]`);
  await expect
    .poll(
      async () => {
        await page
          .getByRole("button", { name: "Refresh jobs", exact: true })
          .click();
        return jobRow.innerText();
      },
      { timeout: 30000, intervals: [500, 1000, 2000] },
    )
    .toContain("succeeded");
  const backgroundDownloadPromise = page.waitForEvent("download");
  await jobRow
    .getByRole("link", { name: "Download report", exact: true })
    .click();
  const backgroundDownload = await backgroundDownloadPromise;
  expect(backgroundDownload.suggestedFilename()).toMatch(/\.csv$/);

  expect(errors).toEqual([]);
  expect(external).toEqual([]);
});

test("employee submits missing context; independent reviewer approves; employee cannot export another person", async ({
  browser,
}) => {
  const employee = await browser.newPage();
  await login(employee, "alex");
  await nav(employee, "Reviews");
  await employee
    .getByRole("button", { name: "Request correction", exact: true })
    .click();
  await employee
    .getByLabel("What needs correcting?")
    .fill(`Browser correction ${stamp}`);
  await employee
    .getByLabel("Proposed context")
    .fill(
      "Synthetic end-to-end evidence: the delivery was shared and reviewed with the team.",
    );
  await submit(employee);
  await expect(employee.locator(".review-list")).toContainText(
    `Browser correction ${stamp}`,
  );
  const denied = await employee.request.get(
    "/api/reports/export/?employee=1&format=csv",
  );
  expect(denied.status()).toBe(403);
  await expect(
    employee
      .getByRole("navigation")
      .getByRole("button", { name: "Administration", exact: true }),
  ).toHaveCount(0);
  await expect(
    employee
      .getByRole("navigation")
      .getByRole("button", { name: "Data sources", exact: true }),
  ).toHaveCount(0);
  const reviewer = await browser.newPage();
  await login(reviewer, "reviewer");
  await nav(reviewer, "Reviews");
  const request = reviewer.locator(".review-list article").filter({
    has: reviewer.getByRole("heading", {
      name: `Browser correction ${stamp}`,
      exact: true,
    }),
  });
  await request
    .getByRole("button", { name: "Review request", exact: true })
    .click();
  await reviewer
    .getByLabel("Decision", { exact: true })
    .selectOption("approved");
  await reviewer
    .getByLabel("Review explanation")
    .fill(
      "Reviewed synthetic supporting context; approved with preserved history.",
    );
  await submit(reviewer, "Record decision");
  await expect(request).toContainText("approved");
  await employee
    .getByRole("button", { name: "Refresh workspace", exact: true })
    .click();
  await expect(
    employee
      .locator(".review-list article")
      .filter({ hasText: `Browser correction ${stamp}` }),
  ).toContainText("approved");
  await employee.close();
  await reviewer.close();
});

test("all screens render without runtime errors; mobile navigation remains usable", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page, "admin");
  for (const name of [
    "People & teams",
    "Goals & outcomes",
    "Skills & roadmap",
    "Reviews",
    "Metric dictionary",
    "Reports",
    "Data sources",
    "Administration",
    "Overview",
  ]) {
    await nav(page, name);
    await expect(page.locator("#main h1")).toBeVisible();
    await expect(page.getByRole("alert")).toHaveCount(0);
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page
    .getByRole("button", { name: "Open navigation", exact: true })
    .click();
  await nav(page, "Skills & roadmap");
  await expect(
    page.getByRole("heading", {
      name: "A shared direction for growth.",
      exact: true,
    }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  for (const name of [
    "Overview",
    "People & teams",
    "Goals & outcomes",
    "Reviews",
    "Reports",
    "Data sources",
    "Administration",
  ]) {
    await page
      .getByRole("button", { name: "Open navigation", exact: true })
      .click();
    await nav(page, name);
    await expect(page.locator("#main h1")).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
      `Mobile overflow on ${name}`,
    ).toBe(true);
  }
  expect(errors).toEqual([]);
});

test("manager reporting scope and integration responsibilities remain separate", async ({
  browser,
}) => {
  const manager = await browser.newPage();
  await login(manager, "manager");
  await nav(manager, "People & teams");
  await expect(
    manager.getByRole("button", { name: "View Alex Morgan", exact: true }),
  ).toBeVisible();
  await expect(
    manager.getByRole("button", { name: "View Jordan Patel", exact: true }),
  ).toHaveCount(0);
  expect(
    (
      await manager.request.get("/api/reports/export/?employee=4&format=csv")
    ).status(),
  ).toBe(403);
  const integration = await browser.newPage();
  await login(integration, "integrations");
  await expect(
    integration.getByRole("heading", {
      name: "Trusted sources. Traceable evidence.",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    integration
      .getByRole("navigation")
      .getByRole("button", { name: "Reviews", exact: true }),
  ).toHaveCount(0);
  await nav(integration, "Data sources");
  await expect(
    integration.getByRole("button", { name: "Connect source", exact: true }),
  ).toBeVisible();
  expect(
    (
      await integration.request.get(
        "/api/reports/export/?employee=2&format=csv",
      )
    ).status(),
  ).toBe(403);
  await manager.close();
  await integration.close();
});
