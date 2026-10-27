import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import en from "./locales/en.json";
import hi from "./locales/hi.json";

export type Lang = "en" | "hi";
const STORED = "sts_lang";

function initial(): Lang {
  try {
    const saved = localStorage.getItem(STORED);
    if (saved === "en" || saved === "hi") return saved;
  } catch {
    /* storage blocked */
  }
  return navigator.language?.startsWith("hi") ? "hi" : "en";
}

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, hi: { translation: hi } },
  lng: initial(),
  fallbackLng: "en",
  interpolation: { escapeValue: false }, // React escapes output
});

export function setLanguage(lang: Lang): void {
  void i18n.changeLanguage(lang);
  document.documentElement.lang = lang;
  try {
    localStorage.setItem(STORED, lang);
  } catch {
    /* storage blocked */
  }
}

document.documentElement.lang = i18n.language;

export default i18n;
