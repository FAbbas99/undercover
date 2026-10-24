import { expect, test } from "@playwright/test";

test("the dashboard loads the queue from the backend", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("link", { name: "CLM-1001" })).toBeVisible();
});
