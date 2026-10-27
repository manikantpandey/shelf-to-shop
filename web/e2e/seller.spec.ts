import { expect, test, type Page } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SHOTS = path.resolve(HERE, "../../docs/screenshots");
const CLIP = path.resolve(HERE, ".fixtures/clip.mp4");

async function shot(page: Page, name: string) {
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: false });
}

test("seller records, fixes prices, publishes; buyer orders on WhatsApp", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/signin$/);
  await page.getByLabel("Shop name").fill("Sharma Sarees");
  await shot(page, "signin-en");
  await page.getByRole("button", { name: "Start" }).click();

  await expect(page.getByRole("heading", { name: "What we keep" })).toBeVisible();
  await page.getByLabel("I agree").check();
  await page.getByLabel("WhatsApp number for orders").fill("98765 43210");
  await shot(page, "setup-en");
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page.getByRole("heading", { name: "Before you record" })).toBeVisible();
  await shot(page, "record-consent-en");
  await page.getByRole("button", { name: "I agree, open camera" }).click();
  await expect(page.getByRole("button", { name: "Record" })).toBeEnabled();
  await page.waitForTimeout(800); // let the fake camera paint a frame
  await shot(page, "record-live-en");

  // Upload a prepared clip through the gallery fallback (no 60 s wait in tests).
  await page.locator('input[type="file"]').setInputFiles(CLIP);
  await expect(page.getByRole("heading", { name: "Making your catalog" })).toBeVisible();
  await shot(page, "processing-en");

  await expect(page).toHaveURL(/\/review$/, { timeout: 60_000 });
  await expect(page.getByText("2 prices need a check.")).toBeVisible();
  await shot(page, "review-en");
  await page.getByRole("button", { name: "Fix 2 prices" }).click();
  await shot(page, "review-questions-en");

  // Tag says 900, seller said 850: keep 850. Item 3 has no price: set it.
  await page.getByRole("button", { name: "₹850", exact: true }).click();
  await expect(page.getByText(/you said ₹850/)).toHaveCount(0);
  const missing = page.getByRole("article").filter({ hasText: "No price heard" });
  await missing.getByPlaceholder("Other price").fill("650");
  await missing.getByRole("button", { name: "Set price" }).click();
  await expect(page.getByText("Everything looks right.")).toBeVisible();
  await page.getByRole("button", { name: "Publish" }).click();

  await expect(page.getByRole("heading", { name: "Your catalog is live" })).toBeVisible();
  await shot(page, "catalog-en");

  await page.goto("/settings");
  await shot(page, "settings-en");

  await page.goto("/s/sharma-sarees");
  await expect(page.getByText("₹1,200")).toBeVisible();
  await expect(page.getByText("₹650")).toBeVisible();
  const order = page.getByRole("link", { name: "Order on WhatsApp" }).first();
  await expect(order).toHaveAttribute("href", /^https:\/\/wa\.me\/919876543210\?text=/);
  // Photos must actually load (published media is served by the API, not the site).
  const photo = page.locator(".ledger img").first();
  await expect.poll(() => photo.evaluate((el) => (el as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
  await shot(page, "shop-en");

  await page.getByRole("button", { name: "हिंदी" }).click();
  await expect(page.getByRole("link", { name: "WhatsApp पर ऑर्डर करें" }).first()).toBeVisible();
  await shot(page, "shop-hi");
  await page.goto("/record");
  await shot(page, "record-live-hi");
});
