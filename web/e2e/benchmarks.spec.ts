import { test, expect } from "@playwright/test";

test.describe("benchmark dashboard", () => {
  test("sidebar navigates to overview and proxy history", async ({ page }) => {
    await page.goto("/benchmarks");
    await expect(page.getByRole("heading", { name: "Benchmarks", exact: true })).toBeVisible();

    await page.getByRole("link", { name: "Latency", exact: true }).first().click();
    await expect(page).toHaveURL(/\/benchmarks\/latency$/);
    await expect(page.url()).not.toMatch(/\.txt$/);
    await expect(page.getByRole("heading", { name: "Latency trends" })).toBeVisible();

    await page.getByRole("navigation", { name: /sidebar|benchmarks/i }).getByRole("link", { name: "History", exact: true }).first().click();
    await expect(page).toHaveURL(/\/benchmarks\/history$/);
    await expect(page.getByRole("heading", { name: "Run history" })).toBeVisible();
  });

  test("history table responds to keyboard help", async ({ page }) => {
    await page.goto("/benchmarks/history");
    await page.keyboard.press("?");
    await expect(page.getByRole("dialog", { name: "Keyboard shortcuts" })).toBeVisible();
  });
});
