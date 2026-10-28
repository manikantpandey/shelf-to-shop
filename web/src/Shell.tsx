import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link, NavLink } from "react-router-dom";

import { api, type OrderSummary } from "./api";
import { Icon, type IconName } from "./components/Icon";
import { Signboard } from "./components/Signboard";
import { setLanguage } from "./i18n";
import { useSession } from "./session";

type Place = { to: string; key: string; icon: IconName };

// Laptop sidebar: every place. Phone tab bar: the daily four plus Record; the rest under More.
const SIDE: Place[] = [
  { to: "/home", key: "nav.home", icon: "home" },
  { to: "/orders", key: "nav.orders", icon: "orders" },
  { to: "/items", key: "nav.items", icon: "items" },
  { to: "/videos", key: "nav.videos", icon: "videos" },
  { to: "/shop", key: "nav.shop", icon: "store" },
  { to: "/share", key: "nav.share", icon: "qr" },
  { to: "/settings", key: "nav.settings", icon: "settings" },
];
const TABS_LEFT: Place[] = [
  { to: "/home", key: "nav.home", icon: "home" },
  { to: "/items", key: "nav.items", icon: "items" },
];
const TABS_RIGHT: Place[] = [
  { to: "/orders", key: "nav.orders", icon: "orders" },
  { to: "/more", key: "nav.more", icon: "more" },
];

/** New-order count for the Orders badge, refreshed every 30 seconds while the app is open. */
const NewOrders = createContext(0);

function useNewOrders(enabled: boolean): number {
  const [count, setCount] = useState(0);
  useEffect(() => {
    if (!enabled) return;
    let stop = false;
    const load = () =>
      api<{ summary: OrderSummary }>("/api/v1/orders?status=new&days=30")
        .then((d) => !stop && setCount(d.summary.counts.new))
        .catch(() => undefined);
    void load();
    const timer = window.setInterval(load, 30_000);
    return () => {
      stop = true;
      window.clearInterval(timer);
    };
  }, [enabled]);
  return count;
}

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

function PlaceLink({ place, badge, tab = false }: { place: Place; badge?: number; tab?: boolean }) {
  const { t } = useTranslation();
  // Tab taps run as a view transition, so the mark slides from the old tab to the new one.
  return (
    <NavLink to={place.to} viewTransition={tab}>
      {({ isActive }) => (
        <>
          {tab && isActive ? <span className="tab-mark" aria-hidden="true" /> : null}
          <Icon name={place.icon} />
          <span>{t(place.key)}</span>
          {badge ? <span className="badge" aria-label={t("nav.new_orders", { count: badge })}>{badge}</span> : null}
        </>
      )}
    </NavLink>
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
  const newOrders = useNewOrders(nav);

  return (
    <NewOrders.Provider value={newOrders}>
      <div className={nav ? "app" : "app bare"}>
        {nav && me ? (
          <aside className="sidebar" aria-label={t("nav.label")}>
            <Signboard name={me.workspace.name} compact as="p" />
            <Link to="/record" className="btn record-btn">
              <Icon name="record" />
              {t("nav.record")}
            </Link>
            <nav className="side-nav">
              {SIDE.map((p) => (
                <PlaceLink key={p.to} place={p} badge={p.to === "/orders" ? newOrders : undefined} />
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
              {TABS_LEFT.map((p) => <PlaceLink key={p.to} place={p} tab />)}
              <NavLink to="/record" className="tab-record">
                <span className="dot" aria-hidden="true">
                  <Icon name="record" size={26} />
                </span>
                <span>{t("nav.record")}</span>
              </NavLink>
              {TABS_RIGHT.map((p) => (
                <PlaceLink key={p.to} place={p} badge={p.to === "/orders" ? newOrders : undefined} tab />
              ))}
            </nav>
          ) : null}
        </div>
      </div>
    </NewOrders.Provider>
  );
}

export function useNewOrderCount(): number {
  return useContext(NewOrders);
}
