import { describe, expect, it } from "vitest";

import i18n from "./i18n";
import { dayFromToday, formatOfferDay, lastDay, offerMessage, offerTitle, whatsappShare, type MessageParts } from "./offers";

const URL_ = "https://shop.example/s/sharma-general-store";
const base: MessageParts = {
  lang: "en",
  shop: "Sharma General Store",
  title: "Diwali sale",
  percent: 10,
  scope: "section",
  section: "Snacks",
  endsOn: "2026-11-03",
  url: URL_,
};
const msg = (parts: Partial<MessageParts>) => offerMessage(i18n.t, { ...base, ...parts });

describe("offer message", () => {
  it("names the discount and the section in English", () => {
    expect(msg({})).toBe(
      `Diwali sale at Sharma General Store: 10% off on Snacks until 3 Nov. See the offers and order on WhatsApp: ${URL_}`,
    );
  });

  it("says everything or selected items for the other scopes", () => {
    expect(msg({ scope: "all", section: null })).toContain(": 10% off on everything until 3 Nov.");
    expect(msg({ scope: "items", section: null })).toContain(": 10% off on selected items until 3 Nov.");
    // A section that is no longer there still reads as a true sentence.
    expect(msg({ scope: "section", section: null })).toContain("10% off on selected items");
  });

  it("is an announcement without a discount", () => {
    expect(msg({ title: "New stock", percent: null, scope: "all" })).toBe(
      `New stock at Sharma General Store, until 3 Nov. See the shop and order on WhatsApp: ${URL_}`,
    );
  });

  it("is written in Hindi when the app is in Hindi", () => {
    expect(msg({ lang: "hi", title: "दिवाली सेल", section: "स्नैक्स" })).toBe(
      `Sharma General Store में दिवाली सेल: 3 नवंबर तक स्नैक्स पर 10% की छूट। ऑफ़र देखें और WhatsApp पर ऑर्डर करें: ${URL_}`,
    );
    expect(msg({ lang: "hi", title: "दिवाली सेल", scope: "all", section: null })).toContain("3 नवंबर तक सारे सामान पर 10% की छूट।");
    expect(msg({ lang: "hi", title: "नया माल", percent: null })).toBe(
      `Sharma General Store में नया माल, 3 नवंबर तक। दुकान देखें और WhatsApp पर ऑर्डर करें: ${URL_}`,
    );
  });

  it("does not depend on the language the app happens to be in", async () => {
    await i18n.changeLanguage("hi");
    try {
      expect(msg({})).toMatch(/^Diwali sale at Sharma General Store: 10% off/);
    } finally {
      await i18n.changeLanguage("en");
    }
  });

  it("has no emoji", () => {
    for (const lang of ["en", "hi"] as const) {
      for (const percent of [10, null]) {
        expect(/\p{Extended_Pictographic}/u.test(msg({ lang, percent }))).toBe(false);
      }
    }
  });
});

describe("WhatsApp link", () => {
  it("opens WhatsApp with the text and no number, and the text survives the trip", () => {
    const text = msg({ lang: "hi", title: "₹99 वाली सेल & more", section: "स्नैक्स" });
    const link = whatsappShare(text);
    expect(link.startsWith("https://wa.me/?text=")).toBe(true);
    expect(link).not.toMatch(/\s/);
    expect(link).toContain("%E2%82%B9"); // ₹
    expect(link).toContain("%26"); // "&" cannot end the text early
    expect(new URL(link).searchParams.get("text")).toBe(text);
    expect(decodeURIComponent(link.slice("https://wa.me/?text=".length))).toBe(text);
  });
});

describe("offer dates and names", () => {
  it("formats the last day for India in each language", () => {
    expect(formatOfferDay("2026-11-03", "en")).toBe("3 Nov");
    expect(formatOfferDay("2026-11-03", "hi")).toBe("3 नवंबर");
    expect(formatOfferDay("not a date", "en")).toBe("not a date");
  });

  it("counts days from the seller's own today", () => {
    expect(dayFromToday(3, new Date(2026, 9, 30, 23, 30))).toBe("2026-11-02");
    expect(dayFromToday(0, new Date(2026, 11, 31, 0, 5))).toBe("2026-12-31");
  });

  it("shows the day an offer really ended", () => {
    expect(lastDay({ ends_on: "2026-11-03", ended_at: null })).toBe("2026-11-03");
    expect(lastDay({ ends_on: "2026-11-03", ended_at: new Date(2026, 10, 2, 15).toISOString() })).toBe("2026-11-02");
    expect(lastDay({ ends_on: "2026-11-03", ended_at: new Date(2026, 10, 4, 0, 10).toISOString() })).toBe("2026-11-03");
  });

  it("falls back to the English name when there is no Hindi one", () => {
    expect(offerTitle({ title_en: "Weekend sale", title_hi: null }, "hi")).toBe("Weekend sale");
    expect(offerTitle({ title_en: "Weekend sale", title_hi: "वीकेंड सेल" }, "hi")).toBe("वीकेंड सेल");
    expect(offerTitle({ title_en: "Weekend sale", title_hi: "वीकेंड सेल" }, "en")).toBe("Weekend sale");
  });
});
