import { test, expect } from "@playwright/test";

test.describe("Theme toggle", () => {
  test("theme class is applied on html element", async ({ page }) => {
    await page.goto("/");
    await page.waitForTimeout(1000);
    const htmlClass = await page.locator("html").getAttribute("class");
    expect(htmlClass).toBeTruthy();
  });

  test("toggle changes theme class", async ({ page }) => {
    await page.goto("/");
    await page.waitForTimeout(1000);

    const htmlEl = page.locator("html");
    const classBefore = await htmlEl.getAttribute("class");
    const wasDark = classBefore?.includes("dark") ?? false;

    // Theme button is the last button in the header
    const themeBtn = page.locator("header button").last();
    await themeBtn.click();
    await page.waitForTimeout(500);

    if (wasDark) {
      await expect(htmlEl).not.toHaveClass(/\bdark\b/, { timeout: 3000 });
    } else {
      await expect(htmlEl).toHaveClass(/dark/, { timeout: 3000 });
    }
  });

  test("double toggle restores original theme", async ({ page }) => {
    await page.goto("/");
    await page.waitForTimeout(1000);

    const htmlEl = page.locator("html");
    const classBefore = await htmlEl.getAttribute("class");

    const themeBtn = page.locator("header button").last();
    await themeBtn.click();
    await page.waitForTimeout(300);
    await themeBtn.click();
    await page.waitForTimeout(300);

    const classAfter = await htmlEl.getAttribute("class");
    expect(classAfter?.includes("dark")).toBe(classBefore?.includes("dark"));
  });

  test("theme persists across reload", async ({ page }) => {
    await page.goto("/");
    await page.waitForTimeout(1000);

    const htmlEl = page.locator("html");
    const classBefore = await htmlEl.getAttribute("class");
    const wasDark = classBefore?.includes("dark") ?? false;

    // Toggle theme
    const themeBtn = page.locator("header button").last();
    await themeBtn.click();
    await page.waitForTimeout(500);

    // Verify toggle worked
    const classAfterToggle = await htmlEl.getAttribute("class");
    expect(classAfterToggle?.includes("dark")).toBe(!wasDark);

    // Reload and check persistence
    await page.reload();
    await page.waitForTimeout(1500);

    const classAfterReload = await htmlEl.getAttribute("class");
    expect(classAfterReload?.includes("dark")).toBe(!wasDark);
  });
});
