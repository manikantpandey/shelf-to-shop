import { expect, test } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const CLIP = path.resolve(HERE, ".fixtures/clip.mp4");

test("seller records, fixes prices, publishes, edits an item; buyer sends a basket order; seller packs it", async ({ page }) => {
  // The front door shows the demo and the eval figures, then leads to sign in.
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Your shop's catalog from one video" })).toBeVisible();
  await page.getByRole("button", { name: /^3 Share$/ }).click();
  await expect(page.getByText("Customers open your shop from WhatsApp, fill a basket and send you the order.")).toBeVisible();
  await page.getByRole("main").getByRole("link", { name: "Start your own shop" }).click();
  await expect(page).toHaveURL(/\/signin$/);
  // A fresh shop each run, so reruns against the same server never meet an earlier run's shop.
  const shopName = `Sharma Sarees ${Date.now().toString(36)}`;
  await page.getByLabel("Start your own shop").fill(shopName);
  await page.getByRole("button", { name: "Start", exact: true }).click();

  await expect(page.getByRole("heading", { name: "What we keep" })).toBeVisible();
  await page.getByLabel("I agree").check();
  await page.getByLabel("WhatsApp number for orders").fill("98765 43210");
  await page.getByRole("button", { name: "Continue" }).click();

  // A new shop lands on Home with the three steps and a way to record.
  await expect(page).toHaveURL(/\/home$/);
  await expect(page.getByText("Your shop is not published yet.")).toBeVisible();
  await page.goto("/record");

  await expect(page.getByRole("heading", { name: "Before you record" })).toBeVisible();
  await page.getByRole("button", { name: "I agree, open camera" }).click();
  await expect(page.getByRole("button", { name: "Record" })).toBeEnabled();

  // Upload a prepared clip through the gallery fallback (no 60 s wait in tests).
  await page.locator('input[type="file"]').setInputFiles(CLIP);
  await expect(page.getByRole("heading", { name: "Making your items" })).toBeVisible();

  await expect(page).toHaveURL(/\/review$/, { timeout: 60_000 });
  await expect(page.getByText("2 prices need a check.")).toBeVisible();
  await page.getByRole("button", { name: "Fix 2 prices" }).click();

  // Tag says 900, seller said 850: keep 850. Item 3 has no price: set it.
  await page.getByRole("button", { name: "₹850", exact: true }).click();
  await expect(page.getByText(/you said ₹850/)).toHaveCount(0);
  const missing = page.getByRole("article").filter({ hasText: "No price heard" });
  await missing.getByPlaceholder("Price (₹)").fill("650");
  await missing.getByRole("button", { name: "Set price" }).click();
  await expect(page.getByText("Everything looks right.")).toBeVisible();
  await page.getByRole("button", { name: "Publish" }).click();

  // Home: the shop is live, and the video is in the history.
  await expect(page).toHaveURL(/\/home$/);
  await expect(page.getByText("3 items on your shop:")).toBeVisible();
  await expect(page.locator(".vrow", { hasText: "On shop" })).toHaveCount(1);

  // Items: mark the red saree sold out; the live shop page updates straight away.
  await page.goto("/items");
  await expect(page.locator(".tile")).toHaveCount(3);
  await page.locator(".tile", { hasText: "₹850" }).click();
  await page.getByLabel(/Sold out/).check();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Saved. Your shop page is updated.")).toBeVisible();
  await page.getByRole("button", { name: "Close" }).click();
  await expect(page.locator(".tile.soldout")).toHaveCount(1);

  // The video's run details show each step and where each price came from.
  await page.goto("/videos");
  await page.locator(".vrow").first().click();
  await expect(page.getByRole("heading", { name: "How it was read" })).toBeVisible();
  await expect(page.locator(".steps li")).toHaveCount(8);

  // A customer: basket of two items, one WhatsApp message, priced by the shop.
  await page.route(/wa\.me/, (route) => route.fulfill({ status: 200, contentType: "text/html", body: "<p>WhatsApp</p>" }));
  await page.goto("/home");
  const shopPath = new URL((await page.locator("a.url").first().getAttribute("href")) ?? "").pathname;
  const slug = shopPath.split("/").pop() ?? "";
  await page.goto(shopPath);
  await expect(page.getByText("₹1,200")).toBeVisible();
  await expect(page.getByText("₹650")).toBeVisible();
  await expect(page.locator(".tile.soldout")).toHaveCount(1);
  // Photos must actually load (published media is served by the API, not the site).
  const photo = page.locator(".tile img").first();
  await expect.poll(() => photo.evaluate((el) => (el as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
  await page.getByRole("button", { name: "Add", exact: true }).first().click();
  await page.getByRole("button", { name: "One more" }).first().click();
  await expect(page.locator(".basketbar")).toContainText("2 items");
  await page.locator(".basketbar .btn").click();
  await page.getByLabel("Your name (optional)").fill("Ravi");
  const sent = page.waitForURL(/wa\.me\/919876543210\?text=/);
  await page.getByRole("button", { name: "Send order on WhatsApp" }).click();
  await sent;
  expect(decodeURIComponent(page.url())).toContain(`Order #1 for ${shopName}`);
  // Back on the shop the basket is empty, so the same order cannot be sent twice by mistake.
  await page.goto(shopPath);
  await expect(page.locator(".tile").first()).toBeVisible();
  await expect(page.locator(".basketbar")).toHaveCount(0);

  // The seller sees it in the order book and moves it along.
  await page.goto("/orders");
  await expect(page.getByText("Order #1")).toBeVisible();
  await expect(page.getByText("Ravi")).toBeVisible();
  await page.getByRole("button", { name: "Mark packed" }).click();
  await expect(page.getByText("Order #1")).toHaveCount(0);
  await page.getByRole("button", { name: /^Packed/ }).click();
  await expect(page.getByText("Order #1")).toBeVisible();

  // Taking back recording consent in Settings brings the notice back before the next video.
  await page.goto("/settings");
  await page.getByRole("button", { name: "Take back recording consent" }).click();
  await expect(page.getByText(/^Recording consent is off\./)).toBeVisible();
  await page.goto("/record");
  await expect(page.getByRole("heading", { name: "Before you record" })).toBeVisible();

  // Each item has its own page: the link the Meta feed and the WhatsApp message point to.
  await page.goto(shopPath);
  await page.locator(".tile .photo").first().click();
  await expect(page).toHaveURL(new RegExp(`/s/${slug}/p/${slug}-[0-9a-f]{8}$`));
  const product = page.locator(".product");
  await expect(product.getByRole("button", { name: "Add", exact: true })).toBeVisible();

  await page.getByRole("button", { name: "हिंदी" }).click();
  await expect(product.locator(".btn.primary")).toHaveText(/जो/);
});

test("an upload survives a dropped connection and a closed tab", async ({ page }) => {
  await page.goto("/signin");
  await page.getByLabel("Start your own shop").fill("Patchy Network Store");
  await page.getByRole("button", { name: "Start", exact: true }).click();
  await page.getByLabel("I agree").check();
  await page.getByLabel("WhatsApp number for orders").fill("98765 43210");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.waitForURL(/\/home$/);
  await page.goto("/record");
  await page.getByRole("button", { name: "I agree, open camera" }).click();
  await expect(page.getByRole("button", { name: "Record" })).toBeEnabled();

  // The network drops whenever a piece of the video is sent.
  await page.route(/\/api\/v1\/uploads\/[^/]+$/, (route) =>
    route.request().method() === "PATCH" ? route.abort("internetdisconnected") : route.continue());
  await page.locator('input[type="file"]').setInputFiles(CLIP);
  await expect(page.getByText("Upload stopped: the connection dropped.")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("button", { name: "Carry on uploading" })).toBeVisible();

  // The seller closes the app; the video is still on the phone when they come back.
  await page.unroute(/\/api\/v1\/uploads\/[^/]+$/);
  await page.goto("/record");
  await expect(page.getByRole("heading", { name: "Finish your last upload" })).toBeVisible();
  await page.getByRole("button", { name: "Carry on uploading" }).click();
  await expect(page.getByRole("heading", { name: "Making your items" })).toBeVisible({ timeout: 30_000 });

  // Once the server has it, the saved copy is gone: no second offer.
  await page.goto("/record");
  await expect(page.getByRole("heading", { name: "Finish your last upload" })).toHaveCount(0);
});
