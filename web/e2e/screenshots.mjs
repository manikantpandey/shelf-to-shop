// Screenshots of every seller screen and the public shop, at phone and laptop size, for the design
// critique in docs/design-plan.md. Needs the API (demo sign-in, sample shop seeded) and Vite running.
//   node e2e/screenshots.mjs [outDir]
import { mkdirSync } from "node:fs";
import { chromium } from "@playwright/test";

const WEB = process.env.WEB_URL ?? "http://localhost:5173";
const OUT = process.argv[2] ?? "../docs/screenshots";
const SIZES = { phone: { width: 360, height: 800 }, laptop: { width: 1440, height: 900 } };

mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch();

for (const [size, viewport] of Object.entries(SIZES)) {
  const context = await browser.newContext({ viewport, deviceScaleFactor: size === "phone" ? 2 : 1, locale: "en-IN" });
  const page = await context.newPage();
  const shotOf = (p) => async (name, fullPage = false) => {
    await p.waitForLoadState("networkidle");
    await p.evaluate(() => document.fonts.ready);
    await p.waitForFunction(() => [...document.images].filter((i) => i.loading !== "lazy").every((i) => i.complete), null,
      { timeout: 15000 }).catch(() => undefined);
    await p.screenshot({ path: `${OUT}/${name}-${size}.jpg`, fullPage, type: "jpeg", quality: 82 });
  };
  const shot = shotOf(page);

  await page.goto(`${WEB}/signin`);
  await shot("signin");
  await page.getByRole("button", { name: "Try the sample shop" }).click();
  await page.waitForURL("**/home");
  await page.getByText("This week").waitFor();
  const shopLink = await page.locator("a.url").first().getAttribute("href");

  // A customer: browse, fill a basket, send one order (WhatsApp itself is stubbed out here).
  const buyer = await context.newPage();
  const buyerShot = shotOf(buyer);
  await buyer.route(/wa\.me/, (route) => route.fulfill({ status: 200, contentType: "text/html", body: "<p>WhatsApp</p>" }));
  await buyer.goto(shopLink);
  await buyer.locator(".tile").first().waitFor();
  await buyerShot("shop", true);
  await buyer.getByRole("button", { name: "Add", exact: true }).nth(0).click();
  await buyer.getByRole("button", { name: "One more" }).first().click();
  await buyer.getByRole("button", { name: "Add", exact: true }).nth(0).click();
  await buyer.locator(".basketbar .btn").click();
  await buyer.getByLabel("Your name (optional)").fill("Ravi");
  await buyer.getByLabel("Note for the shop (optional)").fill("Near the temple, after 6 pm");
  await buyer.waitForTimeout(300);
  await buyerShot("basket");
  await buyer.getByRole("button", { name: "Send order on WhatsApp" }).click();
  await buyer.waitForURL(/wa\.me/);
  await buyer.goto(shopLink);
  await buyer.locator(".tile .photo").first().click();
  await buyer.locator(".product .big img").waitFor();
  await buyerShot("product");
  await buyer.close();

  await page.reload();
  await page.getByText("This week").waitFor();
  await shot("home", true);

  await page.goto(`${WEB}/orders`);
  await page.locator(".order").first().waitFor();
  await shot("orders", true);

  await page.goto(`${WEB}/items`);
  await page.locator(".tile").first().waitFor();
  await shot("items", true);
  await page.getByRole("button", { name: "Select" }).click();
  await page.locator(".tile-wrap .pick").nth(0).check();
  await page.locator(".tile-wrap .pick").nth(1).check();
  await shot("items-select");
  await page.getByRole("button", { name: "Done" }).click();
  await page.locator(".tile").first().click();
  await page.getByRole("dialog").waitFor();
  await page.waitForTimeout(400);
  await shot("item-sheet");
  await page.keyboard.press("Escape");

  await page.goto(`${WEB}/shop`);
  await page.getByText("How your shop looks").waitFor();
  await shot("shop-profile", true);
  await page.goto(`${WEB}/sections`);
  await page.locator(".sec-row").first().waitFor();
  await shot("sections", true);
  await page.goto(`${WEB}/share`);
  await page.locator(".qr img").first().waitFor();
  await page.getByRole("button", { name: "Make picture" }).click();
  await page.locator(".status-preview").waitFor();
  await shot("share", true);
  await page.goto(`${WEB}/poster`);
  await page.locator(".qr img").waitFor();
  await shot("poster");
  if (size === "phone") {
    await page.goto(`${WEB}/more`);
    await shot("more");
  }

  await page.goto(`${WEB}/videos`);
  await page.locator(".vrow").first().waitFor();
  await page.locator(".vrow", { hasText: "On shop" }).first().click();
  await page.locator(".steps li").first().waitFor();
  await shot("video-detail", true);
  await page.goto(`${WEB}/videos`);
  await page.locator(".vrow", { hasText: /question|Ready/ }).first().click();
  await page.getByText(/Found \d+ items/).waitFor();
  await shot("review", true);

  await context.close();
}

await browser.close();
console.log(`screenshots in ${OUT}`);
