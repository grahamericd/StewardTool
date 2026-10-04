import { expect, test } from "@playwright/test";

test("steward completes the Ground Zero landscape workflow", async ({ page }) => {
  const suffix = Date.now().toString().slice(-6);
  const landscapeName = `Licensing landscape ${suffix}`;
  const functionName = `Process applications ${suffix}`;
  const conceptName = `License application ${suffix}`;
  const processName = `Application review ${suffix}`;
  const unitName = `Licensing operations ${suffix}`;
  const systemName = `Licensing system ${suffix}`;
  const unfinishedConcept = `Unfinished concept ${suffix}`;

  await page.goto("/");

  await test.step("create a durable landscape scope", async () => {
    await expect(page.getByRole("heading", { name: "Tell us about the work you support" })).toBeVisible();
    await page.getByLabel("What should we call this area of work?").fill(landscapeName);
    await page.getByLabel("Which team or program does it belong to?").fill("Professional licensing");
    await page.getByLabel("Who can help keep this information current?").fill("Acceptance Test Steward");
    await page.getByLabel("What does this work help people accomplish?").fill("Validate the business-first Ground Zero workflow.");
    await page.getByRole("button", { name: "Start with this work" }).click();
    await expect(page.getByRole("heading", { name: landscapeName })).toBeVisible();
    await page.reload();
    await expect(page.getByRole("heading", { name: landscapeName })).toBeVisible();
  });

  await test.step("capture the business layer", async () => {
    await page.getByRole("button", { name: "Business Landscape", exact: true }).click();
    await expect(page.getByText("Steward construction workspace")).toBeVisible();

    await page.getByLabel("Function name").fill(functionName);
    await page.getByLabel("Business outcome").fill("Issue accurate and timely licenses");
    await page.getByLabel("Description").fill("Receives and evaluates professional license applications");
    await page.getByRole("button", { name: "Add to business map" }).click();
    await expect(page.getByRole("heading", { name: functionName })).toBeVisible();

    await page.getByRole("tab", { name: "Business concepts" }).click();
    await page.getByLabel("Concept name").fill(conceptName);
    await page.getByLabel("Business definition").fill("Information submitted to request a professional license");
    await page.getByRole("button", { name: "Add to business map" }).click();

    await page.getByRole("tab", { name: "Business processes" }).click();
    await page.getByLabel("Process name").fill(processName);
    await page.getByLabel("What happens").fill("An application is reviewed and resolved");
    await page.getByRole("button", { name: "Add to business map" }).click();

    await page.getByRole("tab", { name: "Departments & units" }).click();
    await page.getByLabel("Department or unit name").fill(unitName);
    await page.getByLabel("What this group is responsible for").fill("Owns professional licensing operations");
    await page.getByRole("button", { name: "Add to business map" }).click();
  });

  await test.step("add a system", async () => {
    await page.getByRole("tab", { name: "Systems inventory" }).click();
    await page.getByRole("button", { name: "Add a system" }).click();
    await page.getByLabel("System name or working label").fill(systemName);
    await page.getByRole("button", { name: "Application", exact: true }).click();
    await page.getByRole("button", { name: /^Known/ }).click();
    await page.getByLabel("What is it used for?").fill("Manage license applications and decisions");
    await page.getByRole("button", { name: "Add to systems inventory" }).click();
    await expect(page.getByRole("heading", { name: systemName })).toBeVisible();
  });

  await test.step("map and validate the relationship", async () => {
    await page.getByRole("button", { name: "Relationship Builder", exact: true }).click();
    await page.getByRole("button", { name: /Connect work to a system/ }).click();
    await page.getByLabel("What work does the team do?").selectOption({ label: functionName });
    await page.getByLabel("Which system helps with this work?").selectOption({ label: systemName });
    await page.getByRole("button", { name: "Save this connection" }).click();
    await expect(page.getByText("Connection saved.")).toBeVisible();

    await page.getByRole("button", { name: "Business Landscape", exact: true }).click();
    await expect(page.getByText("Ready to proceed", { exact: false }).first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "Landscape ready for next step" })).toBeVisible();
  });

  await test.step("save and resume unfinished work", async () => {
    await page.getByRole("tab", { name: "Business concepts" }).click();
    const draftSaved = page.waitForResponse(response =>
      response.url().endsWith("/api/landscape/draft")
      && response.request().method() === "PATCH"
      && response.ok()
    );
    await page.getByLabel("Concept name").fill(unfinishedConcept);
    await draftSaved;
    await page.reload();
    await page.getByRole("button", { name: "Business Landscape", exact: true }).click();
    await expect(page.getByText("Saved unfinished work")).toBeVisible();
    await page.getByRole("button", { name: "Resume" }).click();
    await expect(page.getByLabel("Concept name")).toHaveValue(unfinishedConcept);
    await page.getByRole("button", { name: "Clear" }).click();
  });

  await test.step("hand off to asset-level stewardship", async () => {
    await page.getByRole("button", { name: "Create next-step tasks" }).click();
    await expect(page.getByText("Understanding", { exact: true })).toBeVisible();
    await expect(page.getByText("Official source review", { exact: true })).toBeVisible();
    await expect(page.getByText("Quality assessment", { exact: true })).toBeVisible();
    await expect(page.getByText("Approval", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Continue" }).click();
    await expect(page.getByRole("heading", { name: "Information Details" })).toBeVisible();
    await expect(page.locator(".tabs .tab.active")).toHaveText(
      /Help Others Understand It|Where It Lives|Can This Information Be Trusted\?|Share & Publish/
    );
  });
});

test("saving a guided review follow-up removes it from recommended work", async ({ page }) => {
  const stewardHeaders = { "X-User-Email": "steward@demo.gov" };
  await page.goto("/");

  const assetsResponse = await page.request.get("/api/assets", { headers: stewardHeaders });
  expect(assetsResponse.ok()).toBeTruthy();
  const assets = await assetsResponse.json();
  const assetId = assets[0].asset.asset_id;

  const classificationResponse = await page.request.patch(`/api/assets/${assetId}/governance`, {
    headers: stewardHeaders,
    data: { classification: "Internal" },
  });
  expect(classificationResponse.ok()).toBeTruthy();

  const reviewResponse = await page.request.post(`/api/assets/${assetId}/reviews`, {
    headers: stewardHeaders,
    data: {
      answers: { classification: "changed" },
      change_summary: "Handling conditions changed during the browser regression test.",
      review_interval_days: 365,
    },
  });
  expect(reviewResponse.ok()).toBeTruthy();

  await page.reload();
  await page.getByRole("button", { name: "My Next Steps", exact: true }).click();
  const followUp = page.locator(".task").filter({ hasText: "Recheck how this information should be handled" });
  await expect(followUp).toBeVisible();
  await followUp.getByRole("button", { name: "Start guided task" }).click();

  await page.getByRole("button", { name: "No, it is for internal or controlled use" }).click();
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "No personal information" }).click();
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "No known restriction" }).click();
  await page.getByRole("button", { name: "Show recommendation" }).click();
  await page.getByRole("button", { name: "Accept and save" }).click();
  await expect(page.getByText("Classification decision saved.")).toBeVisible();

  await page.getByRole("button", { name: "Overview", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Recheck how this information should be handled" })).toHaveCount(0);

  const tasksResponse = await page.request.get("/api/tasks", { headers: stewardHeaders });
  expect(tasksResponse.ok()).toBeTruthy();
  const tasks = await tasksResponse.json();
  expect(tasks.some(task => task.task_type === "review_change_classification")).toBeFalsy();
});
