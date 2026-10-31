// Offers: the customer message and dates. Pure functions, so the wording is tested without a screen.
import type { TFunction } from "i18next";

import type { Offer, OfferScope } from "./api";

export type Lang = "en" | "hi";

/** A local date as "YYYY-MM-DD" (the seller's own day, not UTC). */
export function localDay(date: Date): string {
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${m}-${d}`;
}

/** Today plus `days`, as "YYYY-MM-DD". */
export function dayFromToday(days: number, now = new Date()): string {
  const date = new Date(now.getFullYear(), now.getMonth(), now.getDate() + days, 12);
  return localDay(date);
}

function toDate(value: string): Date {
  // A bare day is read at local noon so it never shifts to the day before; a timestamp is read as is.
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T12:00:00`) : new Date(value);
}

/** "2026-11-03" -> "3 Nov" in English, "3 नवंबर" in Hindi. */
export function formatOfferDay(value: string, lang: Lang): string {
  const date = toDate(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(lang === "hi" ? "hi-IN" : "en-IN", {
    day: "numeric",
    month: lang === "hi" ? "long" : "short",
  }).format(date);
}

/** The offer's last day as it happened: the day it was ended early, or its planned last day. */
export function lastDay(offer: Pick<Offer, "ends_on" | "ended_at">): string {
  if (!offer.ended_at) return offer.ends_on;
  const ended = localDay(toDate(offer.ended_at));
  return ended < offer.ends_on ? ended : offer.ends_on;
}

export function offerTitle(offer: { title_en: string; title_hi: string | null }, lang: Lang): string {
  return lang === "hi" && offer.title_hi?.trim() ? offer.title_hi : offer.title_en;
}

export type MessageParts = {
  lang: Lang;
  shop: string;
  title: string;
  /** Percent off, or null for an announcement with prices unchanged. */
  percent: number | null;
  scope: OfferScope;
  /** The section's name in `lang`, when the offer covers one section. */
  section?: string | null;
  /** "YYYY-MM-DD", the last day. */
  endsOn: string;
  url: string;
};

/** The plain message the seller sends to customers (no emoji). Wording lives in the locale files. */
export function offerMessage(t: TFunction, m: MessageParts): string {
  const vars = {
    lng: m.lang,
    title: m.title.trim(),
    shop: m.shop.trim(),
    until: formatOfferDay(m.endsOn, m.lang),
    url: m.url,
  };
  if (!m.percent) return t("offers.msg.plain", vars);
  const what =
    m.scope === "section" && m.section?.trim()
      ? m.section.trim()
      : t(m.scope === "all" ? "offers.msg.what_all" : "offers.msg.what_items", { lng: m.lang });
  return t("offers.msg.discount", { ...vars, percent: m.percent, what });
}

/** Opens WhatsApp with the text ready and no number, so the seller picks a broadcast list, chats or Status. */
export function whatsappShare(text: string): string {
  return `https://wa.me/?text=${encodeURIComponent(text)}`;
}
