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
  const shot = async (name, fullPage = false) => {
    await page.waitForLoadState("networkidle");
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: `${OUT}/${name}-${size}.jpg`, fullPage, type: "jpeg", quality: 82 });
  };

  await page.goto(`${WEB}/signin`);
  await shot("signin");
  await page.getByRole("button", { name: "Try the sample shop" }).click();
  await page.waitForURL("**/home");
  await page.getByText("This week").waitFor();
  // Real activity, as a buyer would make it: open the shop page and tap two order buttons
  // (the WhatsApp tabs they open are blocked here).
  const shopLink = await page.locator("a.url").getAttribute("href");
  const buyer = await context.newPage();
  await buyer.route(/wa\.me/, (route) => route.abort());
  await buyer.goto(shopLink);
  await buyer.locator(".tile").first().waitFor();
  for (const n of [0, 1]) {
    const popup = buyer.waitForEvent("popup").catch(() => undefined);
    await buyer.locator(".tile .btn.primary").nth(n).click();
    await (await popup)?.close();
  }
  await buyer.close();
  await page.reload();
  await page.getByText("This week").waitFor();
  await shot("home", true);

  await page.goto(`${WEB}/items`);
  await page.locator(".tile").first().waitFor();
  await shot("items", true);
  await page.locator(".tile").first().click();
  await page.getByRole("dialog").waitFor();
  await page.waitForTimeout(400);
  await shot("item-sheet");
  await page.getByRole("button", { name: /Find the pack photo/ }).click();
  await page.locator(".packs img").first().waitFor();
  await page.waitForFunction(() => [...document.querySelectorAll(".packs img")].slice(0, 4)
    .every((i) => i.complete && i.naturalWidth > 0), null, { timeout: 20000 }).catch(() => undefined);
  await shot("item-pack");
  await page.keyboard.press("Escape");

  await page.goto(`${WEB}/videos`);
  await page.locator(".vrow").first().waitFor();
  await shot("videos");
  const published = page.locator(".vrow", { hasText: "On shop" }).first();
  await published.click();
  await page.locator(".steps li").first().waitFor();
  await shot("video-detail", true);

  await page.goto(`${WEB}/videos`);
  await page.locator(".vrow", { hasText: /question|Ready/ }).first().click();
  await page.getByText(/Found \d+ items/).waitFor();
  await shot("review", true);

  await page.goto(`${WEB}/settings`);
  await shot("settings", true);

  await page.goto(`${WEB}/home`);
  const shopUrl = await page.locator("a.url").getAttribute("href");
  await page.goto(shopUrl);
  await page.locator(".tile").first().waitFor();
  await shot("shop", true);
  await page.locator(".tile .photo").first().click();
  await page.locator(".product .big img").waitFor();
  await page.waitForFunction(() => [...document.images].every((i) => i.complete));
  await shot("product");
  await page.getByRole("button", { name: "हिंदी" }).click();
  await shot("product-hi");

  await context.close();
}

await browser.close();
console.log(`screenshots in ${OUT}`);
