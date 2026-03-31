import { test, expect } from "@playwright/test";

const routes = [
  { path: "/", label: "Dashboard" },
  { path: "/daily", label: "Reports" },
  { path: "/smc", label: "SMC Analysis" },
  { path: "/scorecard", label: "Scorecard" },
  { path: "/journal", label: "Journal" },
];

test.describe("Navigation", () => {
  test("every page title contains SMC Pulse", async ({ page }) => {
    for (const { path } of routes) {
      await page.goto(path);
      await expect(page).toHaveTitle(/SMC Pulse/);
    }
  });

  test("sidebar has 5 links and navigates correctly", async ({ page }) => {
    await page.goto("/");
    const sidebar = page.locator("nav.hidden.md\\:flex");
    const links = sidebar.locator("a");
    await expect(links).toHaveCount(5);

    for (const { path, label } of routes) {
      const link = sidebar.locator("a", { hasText: label });
      await link.click();
      await expect(page).toHaveURL(new RegExp(`${path}$`));
    }
  });

  test("bottom nav visible on mobile viewport", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto("/");
    const bottomNav = page.locator("nav.md\\:hidden");
    await expect(bottomNav).toBeVisible();
    const items = bottomNav.locator("a");
    await expect(items).toHaveCount(5);
  });

  test("active route is highlighted in sidebar", async ({ page }) => {
    await page.goto("/daily");
    const sidebar = page.locator("nav.hidden.md\\:flex");
    const activeLink = sidebar.locator("a", { hasText: "Reports" });
    await expect(activeLink).toHaveClass(/bg-bg-card-hover/);
  });
});
