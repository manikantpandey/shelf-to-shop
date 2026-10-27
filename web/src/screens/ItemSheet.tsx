import { useEffect, useRef, useState, type ChangeEvent, type FormEvent, type MouseEvent } from "react";
import { useTranslation } from "react-i18next";

import {
  api,
  apiUrl,
  ApiError,
  uploadPhoto,
  type Item,
  type ItemSaved,
  type Moment,
  type PackResult,
} from "../api";
import { Icon } from "../components/Icon";
import { PriceTag } from "../components/PriceTag";

type Mode = "main" | "moments" | "pack";

type Props = { item: Item; onClose: () => void; onSaved: (item: Item | null, removedId?: string) => void };

/** One item: price, name, sold out, and three ways to get a better photo. */
export function ItemSheet({ item, onClose, onSaved }: Props) {
  const { t, i18n } = useTranslation();
  const [mode, setMode] = useState<Mode>("main");
  const [price, setPrice] = useState(item.price_inr?.toString() ?? "");
  const [en, setEn] = useState(item.title_en);
  const [hi, setHi] = useState(item.title_hi);
  const [soldOut, setSoldOut] = useState(item.sold_out);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const run = async (work: () => Promise<ItemSaved>, done: string) => {
    setBusy(true);
    setError("");
    setStatus("");
    try {
      const res = await work();
      onSaved(res.item);
      setStatus(res.shop_version ? t("sheet.saved_live") : done);
      setMode("main");
    } catch (err) {
      setError(err instanceof ApiError && err.status !== 0 ? err.message : t("app.offline"));
    } finally {
      setBusy(false);
    }
  };

  const save = (e: FormEvent) => {
    e.preventDefault();
    const body: Record<string, unknown> = {};
    const value = Number.parseInt(price, 10);
    if (value > 0 && value !== item.price_inr) body.price_inr = value;
    if (en.trim() && en.trim() !== item.title_en) body.title_en = en.trim();
    if (hi.trim() && hi.trim() !== item.title_hi) body.title_hi = hi.trim();
    if (soldOut !== item.sold_out) body.sold_out = soldOut;
    if (!Object.keys(body).length) return onClose();
    void run(() => api<ItemSaved>(`/api/v1/items/${item.id}`, { method: "PATCH", json: body }), t("sheet.saved"));
  };

  const remove = async () => {
    if (!window.confirm(t("sheet.remove_confirm"))) return;
    setBusy(true);
    try {
      await api(`/api/v1/items/${item.id}`, { method: "PATCH", json: { removed: true } });
      onSaved(null, item.id);
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("app.offline"));
      setBusy(false);
    }
  };

  const pickFile = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) void run(() => uploadPhoto(item.id, file), t("sheet.photo_saved"));
  };

  const title = i18n.language === "hi" ? item.title_hi : item.title_en;
  return (
    <div className="scrim" role="presentation" onClick={onClose}>
      <div className="sheet" role="dialog" aria-modal="true" aria-labelledby="sheet-title" onClick={(e) => e.stopPropagation()}>
        <div className="sheet-head">
          {mode !== "main" ? (
            <button type="button" className="icon-btn" onClick={() => setMode("main")} aria-label={t("app.back")}>
              <Icon name="back" />
            </button>
          ) : null}
          <h2 id="sheet-title" style={{ flex: 1 }}>
            {mode === "moments" ? t("sheet.moment_title") : mode === "pack" ? t("sheet.pack_title") : title}
          </h2>
          <button type="button" className="icon-btn" onClick={onClose} aria-label={t("sheet.close")} ref={closeRef}>
            <Icon name="close" />
          </button>
        </div>

        {mode === "moments" ? <MomentPicker item={item} busy={busy} onPick={(body) =>
          run(() => api<ItemSaved>(`/api/v1/items/${item.id}/photo/moment`, { method: "POST", json: body }), t("sheet.photo_saved"))} /> : null}
        {mode === "pack" ? <PackSearch item={item} busy={busy} onPick={(code) =>
          run(() => api<ItemSaved>(`/api/v1/items/${item.id}/photo/pack`, { method: "POST", json: { code } }), t("sheet.photo_saved"))} /> : null}

        {mode === "main" ? (
          <>
            <div className="hero">
              {item.image_url ? <img src={apiUrl(item.image_url)} alt={title} /> : <span />}
              <div className="stack" style={{ gap: 8 }}>
                {item.price_inr !== null ? <PriceTag value={item.price_inr} size="lg" /> : null}
                <span className="muted small">
                  {item.live ? (item.sold_out ? t("items.sold_out") : t("items.on_shop")) : t("items.not_yet")}
                </span>
                {item.image_credit ? <span className="credit">{t("sheet.credit", { credit: item.image_credit })}</span> : null}
              </div>
            </div>

            <section className="stack" style={{ gap: 8 }} aria-labelledby="photo-h">
              <h3 id="photo-h">{t("sheet.change_photo")}</h3>
              <div className="choices">
                <label className="choice">
                  <span className="ic"><Icon name="camera" /></span>
                  <span>{t("sheet.upload")}<small>{t("sheet.upload_hint")}</small></span>
                  <input type="file" accept="image/jpeg,image/png,image/webp" capture="environment" hidden onChange={pickFile} disabled={busy} />
                </label>
                <button type="button" className="choice" onClick={() => setMode("moments")} disabled={busy}>
                  <span className="ic"><Icon name="frame" /></span>
                  <span>{t("sheet.moment")}<small>{t("sheet.moment_hint")}</small></span>
                </button>
                <button type="button" className="choice" onClick={() => setMode("pack")} disabled={busy}>
                  <span className="ic"><Icon name="pack" /></span>
                  <span>{t("sheet.pack")}<small>{t("sheet.pack_hint")}</small></span>
                </button>
              </div>
            </section>

            <form className="stack" onSubmit={save}>
              <div className="field">
                <label htmlFor="i-price">{t("sheet.price")}</label>
                <input id="i-price" className="price-input" inputMode="numeric" pattern="[0-9]*" value={price}
                  onChange={(e) => setPrice(e.target.value.replace(/\D/g, ""))} />
              </div>
              <div className="field">
                <label htmlFor="i-en">{t("sheet.name_en")}</label>
                <input id="i-en" value={en} maxLength={200} onChange={(e) => setEn(e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="i-hi">{t("sheet.name_hi")}</label>
                <input id="i-hi" lang="hi" value={hi} maxLength={200} onChange={(e) => setHi(e.target.value)} />
              </div>
              <label className="check">
                <input type="checkbox" checked={soldOut} onChange={(e) => setSoldOut(e.target.checked)} />
                <span>{t("sheet.sold_out")}<br /><small className="muted">{t("sheet.sold_out_hint")}</small></span>
              </label>
              <button type="submit" className="btn primary" disabled={busy}>{busy ? t("sheet.saving") : t("sheet.save")}</button>
              <button type="button" className="btn danger" onClick={remove} disabled={busy}>{t("sheet.remove")}</button>
            </form>
          </>
        ) : null}
        {busy && mode !== "main" ? <p className="muted" role="status">{t("sheet.working")}</p> : null}
        {status ? <p className="ok" role="status">{status}</p> : null}
        {error ? <p className="error" role="alert">{error}</p> : null}
      </div>
    </div>
  );
}

function MomentPicker({ item, busy, onPick }: {
  item: Item;
  busy: boolean;
  onPick: (body: { i: number; x: number; y: number }) => void;
}) {
  const { t } = useTranslation();
  const [moments, setMoments] = useState<Moment[] | null>(null);
  const [chosen, setChosen] = useState<number | null>(null);
  const [tap, setTap] = useState<{ x: number; y: number } | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<{ moments: Moment[] }>(`/api/v1/items/${item.id}/moments`)
      .then((d) => setMoments(d.moments))
      .catch((err) => setError(err instanceof ApiError && err.status !== 0 ? err.message : t("app.offline")));
  }, [item.id, t]);

  const onTap = (e: MouseEvent<HTMLDivElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    setTap({ x: (e.clientX - box.left) / box.width, y: (e.clientY - box.top) / box.height });
  };

  if (error) return <p className="error" role="alert">{error}</p>;
  if (!moments) return <p className="muted">{t("sheet.loading_moments")}</p>;
  const picked = moments.find((m) => m.i === chosen);
  return (
    <div className="stack">
      <p>{picked ? t("sheet.tap_item") : t("sheet.pick_moment")}</p>
      <div className="moments" role="group" aria-label={t("sheet.moment_title")}>
        {moments.map((m) => (
          <button type="button" key={m.i} aria-pressed={chosen === m.i} onClick={() => { setChosen(m.i); setTap(null); }}
            aria-label={t("sheet.at_time", { seconds: m.t_s.toFixed(1) })}>
            <img src={apiUrl(m.image_url)} alt="" />
          </button>
        ))}
      </div>
      {picked ? (
        <div className="tap-frame" onClick={onTap} role="presentation">
          <img src={apiUrl(picked.image_url)} alt={t("sheet.tap_item")} />
          {tap ? <span className="mark" style={{ left: `${tap.x * 100}%`, top: `${tap.y * 100}%` }} /> : null}
        </div>
      ) : null}
      <button type="button" className="btn primary" disabled={busy || chosen === null || !tap}
        onClick={() => chosen !== null && tap && onPick({ i: chosen, ...tap })}>
        {busy ? t("sheet.cutting") : t("sheet.use_moment")}
      </button>
    </div>
  );
}

type Detector = { detect: (source: ImageBitmap) => Promise<{ rawValue: string }[]> };

function PackSearch({ item, busy, onPick }: { item: Item; busy: boolean; onPick: (code: string) => void }) {
  const { t } = useTranslation();
  const startQuery = (item.brand && !item.title_en.toLowerCase().startsWith(item.brand.toLowerCase())
    ? `${item.brand} ${item.title_en}`
    : item.title_en
  ).slice(0, 60);
  const [query, setQuery] = useState(startQuery);
  const [barcode, setBarcode] = useState("");
  const [results, setResults] = useState<PackResult[] | null>(null);
  const [credit, setCredit] = useState("");
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");
  const scanner = typeof window !== "undefined" && "BarcodeDetector" in window;

  const search = async (params: Record<string, string>) => {
    setSearching(true);
    setError("");
    try {
      const qs = new URLSearchParams(params).toString();
      const res = await api<{ results: PackResult[]; credit: string }>(`/api/v1/photos/search?${qs}`);
      setResults(res.results);
      setCredit(res.credit);
    } catch (err) {
      setError(err instanceof ApiError && err.status !== 0 ? err.message : t("app.offline"));
    } finally {
      setSearching(false);
    }
  };

  useEffect(() => {
    // Search once with the item's own name, so the first matches are already there.
    void search({ q: startQuery });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const scan = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    try {
      const Ctor = (window as unknown as { BarcodeDetector: new () => Detector }).BarcodeDetector;
      const found = await new Ctor().detect(await createImageBitmap(file));
      const code = found.map((f) => f.rawValue).find((v) => /^\d{8,14}$/.test(v));
      if (!code) {
        setError(t("sheet.no_barcode"));
        return;
      }
      setBarcode(code);
      void search({ barcode: code });
    } catch {
      setError(t("sheet.no_barcode"));
    }
  };

  return (
    <div className="stack">
      <form className="stack" style={{ gap: 8 }} onSubmit={(e) => { e.preventDefault(); void search({ q: query }); }}>
        <div className="field">
          <label htmlFor="pk-q">{t("sheet.pack_name")}</label>
          <div className="row" style={{ flexWrap: "nowrap" }}>
            <input id="pk-q" className="input" value={query} onChange={(e) => setQuery(e.target.value)} maxLength={80} />
            <button type="submit" className="btn" disabled={searching || !query.trim()} aria-label={t("sheet.search")}>
              <Icon name="search" />
            </button>
          </div>
        </div>
      </form>
      <form className="stack" style={{ gap: 8 }} onSubmit={(e) => { e.preventDefault(); void search({ barcode }); }}>
        <div className="field">
          <label htmlFor="pk-b">{t("sheet.barcode")}</label>
          <div className="row" style={{ flexWrap: "nowrap" }}>
            <input id="pk-b" className="input" inputMode="numeric" value={barcode}
              onChange={(e) => setBarcode(e.target.value.replace(/\D/g, "").slice(0, 14))} />
            <button type="submit" className="btn" disabled={searching || barcode.length < 8} aria-label={t("sheet.search")}>
              <Icon name="search" />
            </button>
          </div>
        </div>
        {scanner ? (
          <label className="btn small">
            <Icon name="barcode" size={18} />
            {t("sheet.scan")}
            <input type="file" accept="image/*" capture="environment" hidden onChange={scan} />
          </label>
        ) : null}
      </form>
      {searching ? <p className="muted" role="status">{t("sheet.searching")}</p> : null}
      {error ? <p className="error" role="alert">{error}</p> : null}
      {results && results.length === 0 ? <p className="muted">{t("sheet.no_packs")}</p> : null}
      {results && results.length ? (
        <>
          <p>{t("sheet.pick_pack")}</p>
          <div className="packs">
            {results.map((r) => (
              <button type="button" key={r.code} onClick={() => onPick(r.code)} disabled={busy}>
                <img src={r.image_url} alt="" loading="lazy" referrerPolicy="no-referrer" />
                <strong>{r.name}</strong>
                {r.brand ? <span className="muted">{r.brand}</span> : null}
              </button>
            ))}
          </div>
          <p className="credit">{t("sheet.pack_credit", { credit })}</p>
        </>
      ) : null}
    </div>
  );
}
