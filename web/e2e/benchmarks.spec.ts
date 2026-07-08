import { test, expect } from "@playwright/test";

test.describe("benchmark dashboard", () => {
  test("sidebar navigates to overview and history", async ({ page }) => {
    await page.goto("/benchmarks");
    await expect(page.getByRole("heading", { name: "Benchmarks", exact: true })).toBeVisible();

    await page.getByRole("link", { name: "History" }).click();
    await expect(page).toHaveURL(/\/benchmarks\/history$/);
    await expect(page.getByRole("heading", { name: "Run history" })).toBeVisible();
  });

  test("history table responds to keyboard help", async ({ page }) => {
    await page.goto("/benchmarks/history");
    await page.keyboard.press("?");
    await expect(page.getByRole("dialog", { name: "Keyboard shortcuts" })).toBeVisible();
  });
});
