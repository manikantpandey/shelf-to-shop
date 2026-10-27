import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { NavLink } from "react-router-dom";

import { api } from "./api";
import { setLanguage } from "./i18n";
import { useSession } from "./session";

/** Seller screens: title bar, optional demo banner, content, bottom navigation. */
export function Shell({ title, children, footer }: { title: string; children: ReactNode; footer?: ReactNode }) {
  const { t, i18n } = useTranslation();
  const { me, setMe } = useSession();

  const switchLanguage = async () => {
    const next = i18n.language === "hi" ? "en" : "hi";
    setLanguage(next);
    if (me) {
      try {
        await api("/api/v1/workspace", { method: "PATCH", json: { language: next } });
        setMe({ ...me, workspace: { ...me.workspace, language: next } });
      } catch {
        /* the language still changes on this device */
      }
    }
  };

  return (
    <div className="screen">
      {me?.environment === "demo" || me?.environment === "dev" ? (
        <div className="banner" role="note">
          {t("app.demo_banner")}
        </div>
      ) : null}
      <header className="top">
        <h1>{title}</h1>
        <button type="button" className="lang" onClick={switchLanguage} lang={i18n.language === "hi" ? "en" : "hi"}>
          {t("app.switch_language")}
        </button>
      </header>
      <main className="body">{children}</main>
      {footer ? <div className="footer">{footer}</div> : null}
      {me ? (
        <nav className="nav" aria-label="Main">
          <NavLink to="/record">{t("nav.record")}</NavLink>
          <NavLink to="/catalog">{t("nav.catalog")}</NavLink>
          <NavLink to="/settings">{t("nav.settings")}</NavLink>
        </nav>
      ) : null}
    </div>
  );
}
