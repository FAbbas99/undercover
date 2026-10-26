import { expect, test } from "@playwright/test";

test("the queue lists every claim", async ({ page }) => {
  await page.goto("/");
  const queue = page.getByRole("region", { name: "Claims queue" });
  await expect(queue.locator("tbody tr")).toHaveCount(25);
  await expect(queue.getByRole("link", { name: "CLM-1001" })).toBeVisible();
});

test("the agent decides and pays a small claim", async ({ page }) => {
  await page.goto("/#/claims/CLM-1004");
  await page.getByRole("button", { name: "Run agent" }).click();
  const title = page.locator(".claim-title");
  await expect(title.getByText("In progress")).toBeVisible();
  const steps = page.getByRole("region", { name: "Agent steps" });
  await expect(
    steps.getByText("Read the claim, policy and history"),
  ).toBeVisible();
  await expect(
    steps.getByText("Read a section of the policy wording"),
  ).toBeVisible();
  await expect(steps.getByText("3. Trip Delay")).toBeVisible();
  await expect(title.getByText("Decided")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("Paid $186.00")).toBeVisible();
  await expect(steps.getByText("Finished")).toBeVisible();
});

test("a payout over the limit waits for a handler's sign-off", async ({
  page,
}) => {
  await page.goto("/#/claims/CLM-1003");
  await page.getByRole("button", { name: "Run agent" }).click();
  const signOff = page.getByRole("region", { name: "Sign-off" });
  await expect(signOff).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("Paid $")).toBeHidden();

  await page.goto("/");
  const row = page.getByRole("row", { name: /CLM-1003/ });
  await expect(row.getByText("Waiting for sign-off")).toBeVisible();

  await row.getByRole("link", { name: "CLM-1003" }).click();
  await page.getByLabel("Handler").selectOption({ label: "Dana Whitfield" });
  await page.getByRole("button", { name: "Sign off and pay" }).click();
  await expect(
    page.getByText("Paid $3,800.00 after sign-off by HND-01"),
  ).toBeVisible();
  await expect(page.locator(".claim-title").getByText("Decided")).toBeVisible();
});

test("the agent's instructions are shown read only", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Agent instructions" }).click();
  const panel = page.getByRole("region", { name: "Agent instructions" });
  await expect(panel.getByText(/You are the UnderCover Agent/)).toBeVisible();
  await expect(
    panel.locator("input, textarea, select, [contenteditable]"),
  ).toHaveCount(0);
});

test("a run works the claims it takes and leaves the rest", async ({
  page,
}) => {
  await page.goto("/");
  const run = page.getByRole("region", { name: "Queue run" });
  const waiting = page.getByTestId("count-waiting");
  await expect(waiting).toBeVisible();
  const before = Number(await waiting.textContent());

  await run.getByLabel("Claims to work").fill("5");
  await run.getByRole("button", { name: "Start run" }).click();

  await expect(run.locator(".todo li")).toHaveCount(5);
  await expect(run.getByText("In progress").first()).toBeVisible({
    timeout: 30_000,
  });
  await expect(run.getByText("5 of 5 done.")).toBeVisible({ timeout: 30_000 });
  await expect(run.getByText("Worked 5 claims.")).toBeVisible();
  await expect(waiting).toHaveText(String(before - 5));
});
