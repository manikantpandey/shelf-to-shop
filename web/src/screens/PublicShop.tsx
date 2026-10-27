import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";

import { api, apiUrl, ApiError, countShopEvent, type PublicProduct, type PublicShop as Shop } from "../api";
import { Icon } from "../components/Icon";
import { Signboard } from "../components/Signboard";
import { formatINR } from "../format";
import { setLanguage } from "../i18n";

type Basket = Record<string, number>;
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

/** The basket survives a reload on this phone (nothing is sent until the customer orders). */
function useBasket(slug: string): [Basket, (id: string, qty: number) => void, () => void] {
  const key = `sts_basket_${slug}`;
  const [basket, setBasket] = useState<Basket>(() => {
    try {
      return JSON.parse(localStorage.getItem(key) ?? "{}") as Basket;
    } catch {
      return {};
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(basket));
    } catch {
      /* storage blocked: the basket lives for this visit only */
    }
  }, [key, basket]);
  const set = (id: string, qty: number) =>
    setBasket((b) => {
      const next = { ...b };
      if (qty <= 0) delete next[id];
      else next[id] = Math.min(99, qty);
      return next;
    });
  return [basket, set, () => setBasket({})];
}

function Stepper({ qty, onChange, label }: { qty: number; onChange: (n: number) => void; label: string }) {
  const { t } = useTranslation();
  return (
    <div className="stepper" role="group" aria-label={label}>
      <button type="button" onClick={() => onChange(qty - 1)} aria-label={t("shop.less")}>−</button>
      <span aria-live="polite">{qty}</span>
      <button type="button" onClick={() => onChange(qty + 1)} aria-label={t("shop.more_qty")}>+</button>
    </div>
  );
}

function AddButton({ product, qty, onChange, hindi }: {
  product: PublicProduct;
  qty: number;
  onChange: (n: number) => void;
  hindi: boolean;
}) {
  const { t } = useTranslation();
  if (product.sold_out) return <span className="btn" aria-disabled="true">{t("shop.sold_out")}</span>;
  if (qty > 0) return <Stepper qty={qty} onChange={onChange} label={hindi ? product.title_hi : product.title_en} />;
  return (
    <button type="button" className="btn primary" onClick={() => onChange(1)}>
      <Icon name="plus" size={18} />
      {t("shop.add")}
    </button>
  );
}

function Price({ product, big = false }: { product: PublicProduct; big?: boolean }) {
  return (
    <span className="row" style={{ gap: 4 }}>
      <span className={big ? "pricetag lg" : "pricetag"}>{product.price_display}</span>
      {product.mrp_display ? <span className="mrp">{product.mrp_display}</span> : null}
    </span>
  );
}

function Tile({ slug, product, hindi, qty, onQty }: {
  slug: string;
  product: PublicProduct;
  hindi: boolean;
  qty: number;
  onQty: (n: number) => void;
}) {
  const { t } = useTranslation();
  const title = hindi ? product.title_hi : product.title_en;
  return (
    <article className={`tile${product.sold_out ? " soldout" : ""}`}>
      <Link to={`/s/${slug}/p/${product.id}`} className="photo" aria-label={title}>
        <img src={product.image_url} alt="" loading="lazy" width={512} height={512} />
        <span className="pricetag">{product.price_display}</span>
        {product.featured ? <span className="pin">{t("shop.popular")}</span> : null}
        {product.sold_out ? <span className="soldout-band">{t("shop.sold_out")}</span> : null}
      </Link>
      <div className="body">
        <h3 className="name">
          <Link to={`/s/${slug}/p/${product.id}`} style={{ color: "inherit", textDecoration: "none" }}>{title}</Link>
        </h3>
        <span className="meta">
          {product.mrp_display ? <>{t("shop.mrp")} <s>{product.mrp_display}</s></> : product.ai_background ? t("shop.ai_label") : " "}
        </span>
        <div className="tile-action">
          <AddButton product={product} qty={qty} onChange={onQty} hindi={hindi} />
        </div>
      </div>
    </article>
  );
}

function BasketSheet({ shop, basket, setQty, clear, onClose, hindi }: {
  shop: Shop;
  basket: Basket;
  setQty: (id: string, n: number) => void;
  clear: () => void;
  onClose: () => void;
  hindi: boolean;
}) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sent, setSent] = useState<{ number: number; url: string; total: string } | null>(null);
  const lines = shop.products.filter((p) => basket[p.id]);
  const total = lines.reduce((sum, p) => sum + (p.price_paise / 100) * basket[p.id], 0);
  const profile = shop.profile;
  const belowMin = profile.min_order_inr && profile.delivery !== "pickup" && total < profile.min_order_inr;

  const send = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await api<{ number: number; whatsapp_url: string; total_display: string }>(
        `/api/v1/public/shops/${shop.shop.slug}/orders`,
        {
          method: "POST",
          json: {
            items: lines.map((p) => ({ id: p.id, qty: basket[p.id] })),
            name: name.trim() || null,
            note: note.trim() || null,
            lang: hindi ? "hi" : "en",
          },
        },
      );
      setSent({ number: res.number, url: res.whatsapp_url, total: res.total_display });
      clear();
      window.location.assign(res.whatsapp_url);
    } catch (err) {
      setError(err instanceof ApiError && err.status === 409 ? err.message : t("app.offline"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="scrim" role="presentation" onClick={onClose}>
      <form className="sheet" role="dialog" aria-modal="true" aria-labelledby="basket-h" onClick={(e) => e.stopPropagation()} onSubmit={send}>
        <div className="sheet-head">
          <h2 id="basket-h">{sent ? t("shop.sent_title") : t("shop.basket")}</h2>
          <button type="button" className="icon-btn" onClick={onClose} aria-label={t("sheet.close")}><Icon name="close" /></button>
        </div>
        {sent ? (
          <div className="sent">
            <span className="big">{t("shop.order_number", { number: sent.number })}</span>
            <p>{t("shop.sent_body", { total: sent.total })}</p>
            <a className="btn primary" href={sent.url}><Icon name="chat" />{t("shop.open_whatsapp")}</a>
          </div>
        ) : (
          <>
            <div className="basket-lines">
              {lines.map((p) => (
                <div className="basket-line" key={p.id}>
                  <img src={p.image_url} alt="" />
                  <span>
                    {hindi ? p.title_hi : p.title_en}
                    <br />
                    <span className="muted small">{t("shop.each", { price: p.price_display })}</span>
                  </span>
                  <Stepper qty={basket[p.id]} onChange={(n) => setQty(p.id, n)} label={hindi ? p.title_hi : p.title_en} />
                </div>
              ))}
            </div>
            <div className="order-total">
              <span>{t("shop.total")}</span>
              <span className="num">{formatINR(total)}</span>
            </div>
            {belowMin ? <p className="muted small">{t("shop.min_order", { min: formatINR(profile.min_order_inr ?? 0) })}</p> : null}
            <div className="field">
              <label htmlFor="b-name">{t("shop.your_name")}</label>
              <input id="b-name" maxLength={60} value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" />
            </div>
            <div className="field">
              <label htmlFor="b-note">{t("shop.note")}</label>
              <input id="b-note" maxLength={200} value={note} onChange={(e) => setNote(e.target.value)} placeholder={t("shop.note_eg")} />
            </div>
            {profile.upi_id ? (
              <div className="upi">
                <span className="small">{t("shop.upi", { upi: profile.upi_id })}</span>
                <button type="button" className="btn small quiet" onClick={() => void navigator.clipboard.writeText(profile.upi_id ?? "").catch(() => undefined)}>
                  <Icon name="copy" size={16} />{t("home.copy")}
                </button>
              </div>
            ) : null}
            <p className="muted small">{t("shop.privacy")}</p>
            {error ? <p className="error" role="alert">{error}</p> : null}
            <button type="submit" className="btn primary" disabled={busy || !lines.length}>
              <Icon name="chat" />
              {busy ? t("shop.sending") : t("shop.send_order")}
            </button>
          </>
        )}
      </form>
    </div>
  );
}

/** The page buyers open from WhatsApp or Instagram: the shop's board, sections, a basket. */
export function PublicShop() {
  const { t, i18n } = useTranslation();
  const { slug = "", itemId } = useParams();
  const [shop, setShop] = useState<Shop | null>(null);
  const [missing, setMissing] = useState(false);
  const [query, setQuery] = useState("");
  const [section, setSection] = useState("");
  const [open, setOpen] = useState(false);
  const [basket, setQty, clear] = useBasket(slug);
  const hindi = i18n.language === "hi";

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

  const groups = useMemo(() => {
    if (!shop) return [];
    const q = query.trim().toLowerCase();
    const found = shop.products.filter(
      (p) => (!section || p.section === section) && (!q || `${p.title_en} ${p.title_hi}`.toLowerCase().includes(q)),
    );
    const named = shop.sections.map((s) => ({ s, list: found.filter((p) => p.section === s.id) })).filter((g) => g.list.length);
    const loose = found.filter((p) => !shop.sections.some((s) => s.id === p.section));
    return loose.length ? [...named, { s: null, list: loose }] : named;
  }, [shop, query, section]);

  // Items that left the shop or sold out drop out of the basket.
  useEffect(() => {
    if (!shop) return;
    for (const id of Object.keys(basket)) {
      const p = shop.products.find((x) => x.id === id);
      if (!p || p.sold_out) setQty(id, 0);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shop]);

  const product = itemId ? shop?.products.find((p) => p.id === itemId) : undefined;
  const others = shop ? shop.products.filter((p) => p.id !== itemId && !p.sold_out && (!product || p.section === product.section)).slice(0, 4) : [];
  const count = Object.values(basket).reduce((a, b) => a + b, 0);
  const total = shop ? shop.products.reduce((sum, p) => sum + (basket[p.id] ? (p.price_paise / 100) * basket[p.id] : 0), 0) : 0;
  const profile = shop?.profile;

  return (
    <div className="shop">
      {profile?.notice ? <p className="notice-strip">{profile.notice}</p> : null}
      <header className="shop-head">
        <div className="brand">
          {profile?.logo_url ? <img className="shop-logo" src={apiUrl(profile.logo_url)} alt="" /> : null}
          <Signboard name={shop?.shop.name ?? " "} as={itemId ? "p" : "h1"} />
        </div>
      </header>
      <div className="shop-bar">
        {itemId ? (
          <Link to={`/s/${slug}`} className="btn quiet small"><Icon name="back" size={18} />{t("shop.all_items")}</Link>
        ) : (
          <div className="shop-info">
            {profile?.hours ? <span className="pill plain">{t("shop.open", { hours: profile.hours })}</span> : null}
            {profile ? <span className="pill">{t(`shop.d_${profile.delivery}`)}</span> : null}
            {profile?.delivery_note ? <span className="pill plain">{profile.delivery_note}</span> : null}
            {profile?.address ? <span className="pill plain">{profile.address}</span> : null}
          </div>
        )}
        <button type="button" className="lang" onClick={() => setLanguage(hindi ? "en" : "hi")} lang={hindi ? "en" : "hi"}>
          {t("app.switch_language")}
        </button>
      </div>
      <main className="shop-body">
        {missing ? <p>{t("shop.not_found")}</p> : null}
        {shop && shop.products.length === 0 ? <p>{t("shop.empty")}</p> : null}
        {shop && itemId && !product ? <p>{t("shop.item_gone")}</p> : null}
        {!itemId && profile?.about ? <p className="muted">{profile.about}</p> : null}

        {product ? (
          <>
            <article className="product">
              <div className="big">
                <img src={product.image_url} alt={hindi ? product.title_hi : product.title_en} width={1024} height={1024} />
              </div>
              <div className="stack">
                <h1 style={{ fontSize: "var(--t-24)" }}>{hindi ? product.title_hi : product.title_en}</h1>
                <Price product={product} big />
                {product.sold_out ? <p className="error">{t("shop.sold_out_long")}</p> : null}
                <p>{hindi ? product.description_hi : product.description_en}</p>
                <div style={{ maxWidth: 260 }}>
                  <AddButton product={product} qty={basket[product.id] ?? 0} onChange={(n) => setQty(product.id, n)} hindi={hindi} />
                </div>
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
                  {others.map((p) => (
                    <Tile key={p.id} slug={slug} product={p} hindi={hindi} qty={basket[p.id] ?? 0} onQty={(n) => setQty(p.id, n)} />
                  ))}
                </div>
              </section>
            ) : null}
          </>
        ) : null}

        {shop && !itemId && shop.products.length ? (
          <>
            <div className="search">
              <Icon name="search" size={20} />
              <input className="input" type="search" value={query} onChange={(e) => setQuery(e.target.value)}
                placeholder={t("shop.search")} aria-label={t("shop.search")} />
            </div>
            {shop.sections.length > 1 ? (
              <div className="chips" role="group" aria-label={t("shop.sections")}>
                <button type="button" className="chip" aria-pressed={!section} onClick={() => setSection("")}>{t("shop.all")}</button>
                {shop.sections.map((s) => (
                  <button type="button" key={s.id} className="chip" aria-pressed={section === s.id} onClick={() => setSection(s.id)}>
                    {hindi ? s.name_hi : s.name_en}
                  </button>
                ))}
              </div>
            ) : null}
            {groups.length === 0 ? <p className="muted">{t("shop.no_match")}</p> : null}
            {groups.map(({ s, list }) => (
              <section key={s?.id ?? "rest"} className="stack" style={{ gap: 8 }} aria-labelledby={`ps-${s?.id ?? "rest"}`}>
                <div className="section-head">
                  <h2 id={`ps-${s?.id ?? "rest"}`}>{s ? (hindi ? s.name_hi : s.name_en) : t("shop.more_items")}</h2>
                </div>
                <div className="tiles wide">
                  {list.map((p) => (
                    <Tile key={p.id} slug={slug} product={p} hindi={hindi} qty={basket[p.id] ?? 0} onQty={(n) => setQty(p.id, n)} />
                  ))}
                </div>
              </section>
            ))}
          </>
        ) : null}
        <p className="credit">{t("shop.made_with")}</p>
      </main>
      {count > 0 && shop ? (
        <div className="basketbar">
          <button type="button" className="btn primary" onClick={() => setOpen(true)}>
            <span><Icon name="basket" size={20} /> {t("shop.items_count", { count })}</span>
            <span>{t("shop.view_basket", { total: formatINR(total) })}</span>
          </button>
        </div>
      ) : null}
      {open && shop ? (
        <BasketSheet shop={shop} basket={basket} setQty={setQty} clear={clear} onClose={() => setOpen(false)} hindi={hindi} />
      ) : null}
    </div>
  );
}
