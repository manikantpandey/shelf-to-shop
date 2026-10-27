import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link, NavLink } from "react-router-dom";

import { api } from "./api";
import { Icon, type IconName } from "./components/Icon";
import { Signboard } from "./components/Signboard";
import { setLanguage } from "./i18n";
import { useSession } from "./session";

const PLACES: { to: string; key: string; icon: IconName }[] = [
  { to: "/home", key: "nav.home", icon: "home" },
  { to: "/items", key: "nav.items", icon: "items" },
  { to: "/videos", key: "nav.videos", icon: "videos" },
  { to: "/settings", key: "nav.settings", icon: "settings" },
];

export function LanguageButton({ className = "lang" }: { className?: string }) {
  const { t, i18n } = useTranslation();
  const { me, setMe } = useSession();
  const next = i18n.language === "hi" ? "en" : "hi";
  const toggle = async () => {
    setLanguage(next);
    if (!me) return;
    try {
      await api("/api/v1/workspace", { method: "PATCH", json: { language: next } });
      setMe({ ...me, workspace: { ...me.workspace, language: next } });
    } catch {
      /* the language still changes on this device */
    }
  };
  return (
    <button type="button" className={className} onClick={toggle} lang={next}>
      {t("app.switch_language")}
    </button>
  );
}

type ShellProps = {
  title: string;
  children: ReactNode;
  /** Shown instead of the title on phones (Home): the shop's signboard. */
  board?: ReactNode;
  /** Page-level actions: next to the title on laptops, under it on phones. */
  actions?: ReactNode;
  /** The screen's one primary action, pinned at the bottom on phones. */
  footer?: ReactNode;
  back?: string;
  /** No navigation (setup before the shop exists). */
  bare?: boolean;
};

/** Seller screens: sidebar on laptops; top bar, pinned action and bottom places on phones. */
export function Shell({ title, children, board, actions, footer, back, bare = false }: ShellProps) {
  const { t } = useTranslation();
  const { me } = useSession();
  const demo = me?.environment === "demo" || me?.environment === "dev";
  const nav = Boolean(me) && !bare;

  return (
    <div className={nav ? "app" : "app bare"}>
      {nav && me ? (
        <aside className="sidebar" aria-label={t("nav.label")}>
          <Signboard name={me.workspace.name} compact as="p" />
          <Link to="/record" className="btn record-btn">
            <Icon name="record" />
            {t("nav.record")}
          </Link>
          <nav className="side-nav">
            {PLACES.map((p) => (
              <NavLink key={p.to} to={p.to}>
                <Icon name={p.icon} />
                {t(p.key)}
              </NavLink>
            ))}
          </nav>
          <div className="side-foot">
            <LanguageButton className="lang on-board" />
            {demo ? <span className="demo-note">{t("app.demo_note")}</span> : null}
          </div>
        </aside>
      ) : null}

      <div className="main">
        <header className={`topbar${board ? " has-board" : ""}`}>
          {back ? (
            <Link to={back} className="icon-btn" aria-label={t("app.back")}>
              <Icon name="back" />
            </Link>
          ) : null}
          {board ? <div className="board-slot">{board}</div> : null}
          <h1 className={board ? "page-title with-board" : "page-title"}>{title}</h1>
          <LanguageButton />
        </header>
        <main className="content">
          {actions ? <div className="page-actions">{actions}</div> : null}
          {children}
        </main>
        {footer ? <div className="footer">{footer}</div> : null}
        {nav ? (
          <nav className="tabbar" aria-label={t("nav.label")}>
            {PLACES.slice(0, 2).map((p) => (
              <NavLink key={p.to} to={p.to}>
                <Icon name={p.icon} />
                <span>{t(p.key)}</span>
              </NavLink>
            ))}
            <NavLink to="/record" className="tab-record">
              <span className="dot" aria-hidden="true">
                <Icon name="record" size={26} />
              </span>
              <span>{t("nav.record")}</span>
            </NavLink>
            {PLACES.slice(2).map((p) => (
              <NavLink key={p.to} to={p.to}>
                <Icon name={p.icon} />
                <span>{t(p.key)}</span>
              </NavLink>
            ))}
          </nav>
        ) : null}
      </div>
    </div>
  );
}
