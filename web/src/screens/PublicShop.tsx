import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";

import { api, ApiError, countShopEvent, type PublicProduct, type PublicShop as Shop } from "../api";
import { Icon } from "../components/Icon";
import { Signboard } from "../components/Signboard";
import { setLanguage } from "../i18n";

const counted = new Set<string>();

/** One page view per shop per browser tab (no visitor data is sent, only +1). */
function countView(slug: string): void {
  const key = `sts_viewed_${slug}`;
  if (counted.has(key)) return;
  counted.add(key);
  try {
    if (sessionStorage.getItem(key)) return;
    sessionStorage.setItem(key, "1");
  } catch {
    /* storage blocked: count anyway */
  }
  countShopEvent(slug, "view");
}

function OrderButton({ slug, product, hindi }: { slug: string; product: PublicProduct; hindi: boolean }) {
  const { t } = useTranslation();
  if (product.sold_out) {
    return <span className="btn" aria-disabled="true">{t("shop.sold_out")}</span>;
  }
  return (
    <a className="btn primary" href={hindi ? product.order_link_hi : product.order_link_en} target="_blank" rel="noopener"
      onClick={() => countShopEvent(slug, "order", product.id)}>
      <Icon name="chat" size={18} />
      {t("shop.order")}
    </a>
  );
}

function Tile({ slug, product, hindi }: { slug: string; product: PublicProduct; hindi: boolean }) {
  const { t } = useTranslation();
  const title = hindi ? product.title_hi : product.title_en;
  return (
    <article className={`tile${product.sold_out ? " soldout" : ""}`}>
      <Link to={`/s/${slug}/p/${product.id}`} className="photo" aria-label={title}>
        <img src={product.image_url} alt="" loading="lazy" width={512} height={512} />
        <span className="pricetag">{product.price_display}</span>
        {product.sold_out ? <span className="soldout-band">{t("shop.sold_out")}</span> : null}
      </Link>
      <div className="body">
        <h2 className="name">
          <Link to={`/s/${slug}/p/${product.id}`} style={{ color: "inherit", textDecoration: "none" }}>{title}</Link>
        </h2>
        <span className="meta">
          {product.ai_background ? t("shop.ai_label") : product.image_credit ? t("shop.pack_photo") : " "}
        </span>
        <div className="order">
          <OrderButton slug={slug} product={product} hindi={hindi} />
        </div>
      </div>
    </article>
  );
}

/** The page buyers open from WhatsApp or Instagram: the shop's board, items, one order button each. */
export function PublicShop() {
  const { t, i18n } = useTranslation();
  const { slug = "", itemId } = useParams();
  const [shop, setShop] = useState<Shop | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    api<Shop>(`/api/v1/public/shops/${encodeURIComponent(slug)}`)
      .then((data) => {
        setShop(data);
        document.title = data.shop.name;
        countView(slug);
      })
      .catch((err) => setMissing(err instanceof ApiError && err.status === 404));
  }, [slug]);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [itemId]);

  const hindi = i18n.language === "hi";
  const product = itemId ? shop?.products.find((p) => p.id === itemId) : undefined;
  const others = shop ? shop.products.filter((p) => p.id !== itemId && !p.sold_out).slice(0, 4) : [];

  return (
    <div className="shop">
      <header className="shop-head">
        <Signboard name={shop?.shop.name ?? " "} as={itemId ? "p" : "h1"} />
      </header>
      <div className="shop-bar">
        {itemId ? (
          <Link to={`/s/${slug}`} className="btn quiet small"><Icon name="back" size={18} />{t("shop.all_items")}</Link>
        ) : (
          <p className="muted">{shop && shop.products.length ? t("shop.how") : " "}</p>
        )}
        <button type="button" className="lang" onClick={() => setLanguage(hindi ? "en" : "hi")} lang={hindi ? "en" : "hi"}>
          {t("app.switch_language")}
        </button>
      </div>
      <main className="shop-body">
        {missing ? <p>{t("shop.not_found")}</p> : null}
        {shop && shop.products.length === 0 ? <p>{t("shop.empty")}</p> : null}
        {shop && itemId && !product ? <p>{t("shop.item_gone")}</p> : null}

        {product ? (
          <>
            <article className="product">
              <div className="big">
                <img src={product.image_url} alt={hindi ? product.title_hi : product.title_en} width={1024} height={1024} />
              </div>
              <div className="stack">
                <h1 style={{ fontSize: "var(--t-30)" }}>{hindi ? product.title_hi : product.title_en}</h1>
                <span className="pricetag lg" style={{ alignSelf: "flex-start" }}>{product.price_display}</span>
                {product.sold_out ? <p className="error">{t("shop.sold_out_long")}</p> : null}
                <p>{hindi ? product.description_hi : product.description_en}</p>
                <OrderButton slug={slug} product={product} hindi={hindi} />
                {product.ai_background ? <p className="credit">{t("shop.ai_long")}</p> : null}
                {product.image_credit ? (
                  <p className="credit">
                    {t("shop.photo_by")}{" "}
                    {product.image_credit_url ? (
                      <a href={product.image_credit_url} target="_blank" rel="noopener">{product.image_credit}</a>
                    ) : product.image_credit}
                  </p>
                ) : null}
              </div>
            </article>
            {others.length ? (
              <section className="stack" aria-labelledby="more-h">
                <h2 id="more-h">{t("shop.more")}</h2>
                <div className="tiles">
                  {others.map((p) => <Tile key={p.id} slug={slug} product={p} hindi={hindi} />)}
                </div>
              </section>
            ) : null}
          </>
        ) : null}

        {shop && !itemId ? (
          <div className="tiles wide">
            {shop.products.map((p) => <Tile key={p.id} slug={slug} product={p} hindi={hindi} />)}
          </div>
        ) : null}
        <p className="credit">{t("shop.made_with")}</p>
      </main>
    </div>
  );
}
