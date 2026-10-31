import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import {
  api,
  ApiError,
  type Item,
  type Offer,
  type OfferKind,
  type OfferSaved,
  type Offers as OffersData,
  type OfferScope,
  type ShopSection,
} from "../api";
import { Icon } from "../components/Icon";
import { formatINR } from "../format";
import { dayFromToday, formatOfferDay, lastDay, offerMessage, offerTitle, whatsappShare, type Lang } from "../offers";
import { useSession } from "../session";
import { Shell } from "../Shell";

const KINDS: OfferKind[] = ["diwali", "festival", "weekend", "new_stock", "clearance", "custom"];
const PERCENTS = [5, 10, 15, 20, 25];
const SCOPES: OfferScope[] = ["all", "section", "items"];
type Discount = number | "other" | "none";

export type StartOffer = {
  kind: OfferKind;
  title_en: string;
  title_hi?: string;
  percent_off: number | null;
  scope: OfferScope;
  section_id?: string;
  item_ids?: string[];
  ends_on: string;
};

function sectionName(sections: ShopSection[], id: string | null, lang: Lang): string | null {
  const s = sections.find((x) => x.id === id);
  if (!s) return null;
  return lang === "hi" && s.name_hi ? s.name_hi : s.name_en;
}

const itemName = (it: Item, lang: Lang) => (lang === "hi" && it.title_hi ? it.title_hi : it.title_en);

/** "Run an offer": occasion, names, discount, what it covers, last day, and the message customers will get. */
function OfferForm({ sections, items, shop, url, lang, busy, error, onStart, onInvalid }: {
  sections: ShopSection[];
  items: Item[];
  shop: string;
  url: string | null;
  lang: Lang;
  busy: boolean;
  error: string;
  onStart: (body: StartOffer) => void;
  onInvalid: (message: string) => void;
}) {
  const { t } = useTranslation();
  // English and Hindi names come from their own locale, whatever language the app is in.
  const names = (k: OfferKind): [string, string] =>
    k === "custom" ? ["", ""] : [t(`offers.default_title.${k}`, { lng: "en" }), t(`offers.default_title.${k}`, { lng: "hi" })];
  const [kind, setKind] = useState<OfferKind>("diwali");
  const [titleEn, setTitleEn] = useState(() => names("diwali")[0]);
  const [titleHi, setTitleHi] = useState(() => names("diwali")[1]);
  const [discount, setDiscount] = useState<Discount>(10);
  const [other, setOther] = useState("");
  const [scope, setScope] = useState<OfferScope>("all");
  const [sectionId, setSectionId] = useState("");
  const [picked, setPicked] = useState<Set<string>>(() => new Set());
  const [query, setQuery] = useState("");
  const [endsOn, setEndsOn] = useState(() => dayFromToday(3));
  const nameRef = useRef<HTMLInputElement>(null);
  const today = dayFromToday(0);

  const newStock = kind === "new_stock";
  const percent = newStock || discount === "none" ? null : discount === "other" ? Number.parseInt(other, 10) : discount;
  const percentOk = percent === null || (Number.isInteger(percent) && percent >= 1 && percent <= 90);

  const live = useMemo(() => items.filter((it) => it.live), [items]);
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? live.filter((it) => `${it.title_en} ${it.title_hi} ${it.brand ?? ""}`.toLowerCase().includes(q)) : live;
  }, [live, query]);

  const pickKind = (k: OfferKind) => {
    setKind(k);
    const [en, hi] = names(k);
    setTitleEn(en);
    setTitleHi(hi);
    if (k === "custom") nameRef.current?.focus();
  };

  const toggle = (id: string, on: boolean) =>
    setPicked((cur) => {
      const next = new Set(cur);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });

  const preview = offerMessage(t, {
    lang,
    shop,
    title: (lang === "hi" && titleHi.trim() ? titleHi : titleEn).trim() || "…",
    percent: percentOk ? percent : null,
    scope,
    section: sectionName(sections, sectionId, lang),
    endsOn: endsOn || dayFromToday(3),
    url: url ?? t("offers.link_placeholder"),
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!titleEn.trim()) return onInvalid(t("offers.err_title"));
    if (!percentOk) return onInvalid(t("offers.err_percent"));
    if (scope === "section" && !sectionId) return onInvalid(t("offers.err_section"));
    if (scope === "items" && !picked.size) return onInvalid(t("offers.err_items"));
    if (!endsOn || endsOn < today) return onInvalid(t("offers.err_date"));
    const body: StartOffer = { kind, title_en: titleEn.trim(), percent_off: percent, scope, ends_on: endsOn };
    if (titleHi.trim()) body.title_hi = titleHi.trim();
    if (scope === "section") body.section_id = sectionId;
    if (scope === "items") body.item_ids = live.filter((it) => picked.has(it.id)).map((it) => it.id);
    onStart(body);
  };

  const chip = (checked: boolean, label: string, onClick: () => void, disabled = false, key?: string) => (
    <button type="button" key={key ?? label} className="chip" role="radio" aria-checked={checked} disabled={disabled} onClick={onClick}>
      {label}
    </button>
  );

  return (
    <form className="stack offer-form" onSubmit={submit} noValidate aria-labelledby="form-h">
      <section className="panel" aria-labelledby="form-h">
        <h2 id="form-h">{t("offers.form_title")}</h2>

        <div className="field">
          <span className="label" id="of-kind">{t("offers.occasion")}</span>
          <div className="radios" role="radiogroup" aria-labelledby="of-kind">
            {KINDS.map((k) => chip(kind === k, t(`offers.kind.${k}`), () => pickKind(k), false, k))}
          </div>
        </div>

        <div className="offer-names">
          <div className="field">
            <label htmlFor="of-en">{t("offers.name_en")}</label>
            <input id="of-en" ref={nameRef} maxLength={80} value={titleEn} onChange={(e) => setTitleEn(e.target.value)}
              placeholder={t("offers.name_eg", { lng: "en" })} />
          </div>
          <div className="field">
            <label htmlFor="of-hi">{t("offers.name_hi")}</label>
            <input id="of-hi" lang="hi" maxLength={80} value={titleHi} onChange={(e) => setTitleHi(e.target.value)}
              placeholder={t("offers.name_eg", { lng: "hi" })} aria-describedby="of-hi-hint" />
            <span className="hint" id="of-hi-hint">{t("offers.name_hi_hint")}</span>
          </div>
        </div>

        <div className="field">
          <span className="label" id="of-disc">{t("offers.discount")}</span>
          <div className="radios" role="radiogroup" aria-labelledby="of-disc">
            {PERCENTS.map((p) => chip(!newStock && discount === p, t("offers.pct", { percent: p }), () => setDiscount(p), newStock, String(p)))}
            {chip(!newStock && discount === "other", t("offers.other"), () => setDiscount("other"), newStock, "other")}
            {chip(newStock || discount === "none", t("offers.no_discount"), () => setDiscount("none"), newStock, "none")}
          </div>
          {newStock ? <p className="muted small">{t("offers.new_stock_note")}</p> : null}
        </div>
        {!newStock && discount === "other" ? (
          <div className="field offer-other">
            <label htmlFor="of-pct">{t("offers.other_label")}</label>
            <input id="of-pct" inputMode="numeric" maxLength={2} value={other} onChange={(e) => setOther(e.target.value.replace(/\D/g, ""))} />
          </div>
        ) : null}

        <div className="field">
          <span className="label" id="of-scope">{t("offers.apply_to")}</span>
          <div className="radios" role="radiogroup" aria-labelledby="of-scope">
            {SCOPES.map((s) => chip(scope === s, t(`offers.scope_${s}`), () => setScope(s), s === "section" && !sections.length, s))}
          </div>
        </div>
        {scope === "section" ? (
          <div className="field">
            <label htmlFor="of-sec">{t("offers.section")}</label>
            <select id="of-sec" value={sectionId} onChange={(e) => setSectionId(e.target.value)}>
              <option value="">{t("offers.pick_section")}</option>
              {sections.map((s) => <option key={s.id} value={s.id}>{sectionName(sections, s.id, lang)}</option>)}
            </select>
          </div>
        ) : null}
        {scope === "items" ? (
          live.length ? (
            <div className="stack pick-items">
              <div className="search">
                <Icon name="search" size={20} />
                <input className="input" type="search" value={query} onChange={(e) => setQuery(e.target.value)}
                  placeholder={t("offers.search_items")} aria-label={t("offers.search_items")} />
              </div>
              <p className="muted small" aria-live="polite">{t("offers.picked", { count: picked.size })}</p>
              {shown.length ? (
                <ul className="list-plain pick-list">
                  {shown.map((it) => (
                    <li key={it.id}>
                      <label className="check">
                        <input type="checkbox" checked={picked.has(it.id)} onChange={(e) => toggle(it.id, e.target.checked)} />
                        <span className="grow">{itemName(it, lang)}</span>
                        <span className="num">{it.price_inr !== null ? formatINR(it.price_inr) : t("offers.no_price")}</span>
                      </label>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="muted">{t("offers.no_match")}</p>
              )}
            </div>
          ) : (
            <p className="muted">{t("offers.no_items")}</p>
          )
        ) : null}

        <div className="field offer-date">
          <label htmlFor="of-end">{t("offers.ends_on")}</label>
          <input id="of-end" type="date" min={today} value={endsOn} onChange={(e) => setEndsOn(e.target.value)}
            aria-describedby="of-end-hint" />
          <span className="hint" id="of-end-hint">{t("offers.ends_hint")}</span>
        </div>
      </section>

      <section className="panel" aria-labelledby="pv-h">
        <h2 id="pv-h">{t("offers.preview")}</h2>
        <p className="offer-msg">{preview}</p>
        <p className="muted small">{url ? t("offers.preview_hint") : t("offers.not_published")}</p>
      </section>

      <div className="offer-go">
        {error ? <p className="error" role="alert">{error}</p> : null}
        <button type="submit" className="btn primary" disabled={busy}>{busy ? t("offers.starting") : t("offers.start")}</button>
      </div>
    </form>
  );
}

/** The offer that is on now: what it does, the message for customers, and the way to end it early. */
function RunningOffer({ offer, sections, shop, url, lang, busy, error, onEnd }: {
  offer: Offer;
  sections: ShopSection[];
  shop: string;
  url: string | null;
  lang: Lang;
  busy: boolean;
  error: string;
  onEnd: () => void;
}) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const title = offerTitle(offer, lang);
  const section = sectionName(sections, offer.section_id, lang);
  const message = url
    ? offerMessage(t, { lang, shop, title, percent: offer.percent_off, scope: offer.scope, section, endsOn: offer.ends_on, url })
    : "";
  const covers =
    offer.scope === "all"
      ? t("offers.covers_all")
      : offer.scope === "section" && section
        ? section
        : t("offers.covers_items", { count: offer.item_ids.length || offer.items_count });

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(message);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <>
      <section className="panel offer-run" aria-labelledby="run-h">
        <span className="pill">{t("offers.running")}</span>
        <div className="offer-head">
          <h2 id="run-h">{title}</h2>
          {offer.percent_off ? <span className="pricetag">{t("offers.percent", { percent: offer.percent_off })}</span> : null}
        </div>
        <p>{t("offers.until_line", { date: formatOfferDay(offer.ends_on, lang) })}</p>
        <dl className="offer-facts">
          <div>
            <dt>{t("offers.applies_to")}</dt>
            <dd>{covers}</dd>
          </div>
          <div>
            <dt>{t("offers.prices")}</dt>
            <dd>{offer.percent_off ? t("offers.changed", { count: offer.items_count }) : t("offers.unchanged")}</dd>
          </div>
        </dl>
      </section>

      {url ? (
        <section className="panel" aria-labelledby="tell-h">
          <h2 id="tell-h">{t("offers.message")}</h2>
          <p className="offer-msg">{message}</p>
          <div className="row offer-acts">
            <a className="btn primary" href={whatsappShare(message)} target="_blank" rel="noopener">
              <Icon name="chat" />
              {t("offers.tell")}
            </a>
            <button type="button" className="btn" onClick={() => void copy()}>
              <Icon name={copied ? "check" : "copy"} />
              {copied ? t("offers.copied") : t("offers.copy")}
            </button>
          </div>
          <p className="muted small">{t("offers.how")}</p>
        </section>
      ) : (
        <div className="notice calm">
          <Icon name="info" />
          <span className="grow">{t("offers.not_published")}</span>
        </div>
      )}

      {error ? <p className="error" role="alert">{error}</p> : null}
      <div className="row">
        <button type="button" className="btn danger" onClick={onEnd} disabled={busy}>
          {busy ? t("offers.ending") : t("offers.end")}
        </button>
      </div>
    </>
  );
}

function PastOffers({ offers, lang }: { offers: Offer[]; lang: Lang }) {
  const { t } = useTranslation();
  return (
    <section className="panel" aria-labelledby="past-h">
      <h2 id="past-h">{t("offers.past")}</h2>
      <ul className="list-plain past-offers">
        {offers.map((o) => (
          <li key={o.id}>
            <span className="what">
              <span>{offerTitle(o, lang)}</span>
              <span className="muted small">
                {t("offers.past_dates", { from: formatOfferDay(o.started_at, lang), to: formatOfferDay(lastDay(o), lang) })}
              </span>
            </span>
            <span className="num">{o.percent_off ? t("offers.percent", { percent: o.percent_off }) : t("offers.no_discount_short")}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Festival sales: start one, tell customers on WhatsApp (the seller sends it), end it early if needed. */
export function Offers() {
  const { t, i18n } = useTranslation();
  const { me } = useSession();
  const lang: Lang = i18n.language === "hi" ? "hi" : "en";
  const [data, setData] = useState<OffersData | null>(null);
  const [sections, setSections] = useState<ShopSection[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const statusRef = useRef<HTMLParagraphElement>(null);

  const load = async () => {
    const [o, s, i] = await Promise.all([
      api<OffersData>("/api/v1/offers"),
      api<{ sections: ShopSection[] }>("/api/v1/sections"),
      api<{ items: Item[] }>("/api/v1/items"),
    ]);
    setData(o);
    setSections(s.sections);
    setItems(i.items);
  };

  useEffect(() => {
    load().catch(() => setLoadError(t("app.offline")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t]);

  // After starting or ending, the page changes under the seller's thumb: bring the result into view.
  useEffect(() => {
    if (status) statusRef.current?.scrollIntoView?.({ block: "center" });
  }, [status]);

  const failed = (err: unknown) => setError(err instanceof ApiError && err.status ? err.message : t("app.offline"));

  const start = async (body: StartOffer) => {
    setBusy(true);
    setError("");
    setStatus("");
    try {
      const res = await api<OfferSaved>("/api/v1/offers", { method: "POST", json: body });
      setData((d) => (d ? { ...d, active: res.offer } : d));
      setStatus(res.shop_version !== null ? t("offers.started") : t("offers.started_unpublished"));
    } catch (err) {
      failed(err);
      // Another offer started meanwhile (another phone): show it.
      if (err instanceof ApiError && err.code === "offer_running") void load().catch(() => undefined);
    } finally {
      setBusy(false);
    }
  };

  const end = async () => {
    const active = data?.active;
    if (!active || !window.confirm(t("offers.end_confirm"))) return;
    setBusy(true);
    setError("");
    setStatus("");
    try {
      const res = await api<OfferSaved>(`/api/v1/offers/${encodeURIComponent(active.id)}/end`, { method: "POST" });
      setData((d) => (d ? { ...d, active: null, past: [res.offer, ...d.past.filter((p) => p.id !== res.offer.id)] } : d));
      setStatus(t("offers.ended"));
    } catch (err) {
      failed(err);
    } finally {
      setBusy(false);
    }
  };

  const shop = me?.workspace.name ?? "";
  const url = data?.shop_url ?? null;

  return (
    <Shell title={t("offers.title")} back="/more">
      <p className="muted">{t("offers.lead")}</p>
      {status ? <p className="ok" role="status" ref={statusRef}>{status}</p> : null}
      {data === null ? (
        loadError ? <p className="error" role="alert">{loadError}</p> : <p className="muted">{t("app.loading")}</p>
      ) : data.active ? (
        <RunningOffer offer={data.active} sections={sections} shop={shop} url={url} lang={lang} busy={busy} error={error}
          onEnd={() => void end()} />
      ) : (
        <OfferForm sections={sections} items={items} shop={shop} url={url} lang={lang} busy={busy} error={error}
          onStart={(body) => void start(body)} onInvalid={(message) => { setStatus(""); setError(message); }} />
      )}
      {data?.past.length ? <PastOffers offers={data.past} lang={lang} /> : null}
    </Shell>
  );
}
