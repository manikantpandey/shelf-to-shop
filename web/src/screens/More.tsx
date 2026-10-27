import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { Icon, type IconName } from "../components/Icon";
import { Shell } from "../Shell";

const LINKS: { to: string; icon: IconName; key: string }[] = [
  { to: "/videos", icon: "videos", key: "videos" },
  { to: "/shop", icon: "store", key: "shop" },
  { to: "/sections", icon: "sections", key: "sections" },
  { to: "/share", icon: "qr", key: "share" },
  { to: "/settings", icon: "settings", key: "settings" },
];

/** Phones: everything that is not a daily task, one tap away. */
export function More() {
  const { t } = useTranslation();
  return (
    <Shell title={t("more.title")}>
      <nav className="menu" aria-label={t("more.title")}>
        {LINKS.map((l) => (
          <Link key={l.to} to={l.to}>
            <span className="ic"><Icon name={l.icon} /></span>
            <span>
              {t(`more.${l.key}`)}
              <small>{t(`more.${l.key}_hint`)}</small>
            </span>
            <Icon name="next" size={18} />
          </Link>
        ))}
      </nav>
    </Shell>
  );
}
