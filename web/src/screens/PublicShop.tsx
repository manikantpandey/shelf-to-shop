import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { api, ApiError, type PublicShop as Shop } from "../api";
import { setLanguage } from "../i18n";

/** The page buyers open from WhatsApp or Instagram: ledger rows, one order button per item. */
export function PublicShop() {
  const { t, i18n } = useTranslation();
  const { slug = "" } = useParams();
  const [shop, setShop] = useState<Shop | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    api<Shop>(`/api/v1/public/shops/${encodeURIComponent(slug)}`)
      .then((data) => {
        setShop(data);
        document.title = data.shop.name;
      })
      .catch((err) => setMissing(err instanceof ApiError && err.status === 404));
  }, [slug]);

  const hindi = i18n.language === "hi";
  return (
    <div className="screen">
      <header className="top">
        <h1>{shop?.shop.name ?? ""}</h1>
        <button type="button" className="lang" onClick={() => setLanguage(hindi ? "en" : "hi")}>{t("app.switch_language")}</button>
      </header>
      <main className="body">
        {missing ? <p>{t("shop.not_found")}</p> : null}
        {shop && shop.products.length === 0 ? <p>{t("shop.empty")}</p> : null}
        {shop ? (
          <ul className="ledger">
            {shop.products.map((p) => (
              <li key={p.id}>
                <img src={p.image_url} alt={hindi ? p.title_hi : p.title_en} loading="lazy" width={112} height={112} />
                <div className="info">
                  <h2>{hindi ? p.title_hi : p.title_en}</h2>
                  <span className="price">{p.price_display}</span>
                  {p.ai_background ? <span className="ai">{t("shop.ai_label")}</span> : null}
                  <a className="btn small" href={hindi ? p.order_link_hi : p.order_link_en} target="_blank" rel="noopener">
                    {t("shop.order")}
                  </a>
                </div>
              </li>
            ))}
          </ul>
        ) : null}
      </main>
    </div>
  );
}
