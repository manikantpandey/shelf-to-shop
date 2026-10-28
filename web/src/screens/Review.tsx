import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import { api, apiUrl, ApiError, type Flag, type Item, type Review as ReviewData, type ReviewProduct, type ShopSection } from "../api";
import { Icon } from "../components/Icon";
import { PriceTag } from "../components/PriceTag";
import { formatINR } from "../format";
import { Shell } from "../Shell";
import { ItemSheet } from "./ItemSheet";

const PRICE_KINDS = new Set(["missing_price", "price_conflict", "ambiguous_price", "implausible_price", "uncertain_price"]);

export function Review() {
  const { t, i18n } = useTranslation();
  const { jobId = "" } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState<ReviewData | null>(null);
  const [items, setItems] = useState<Map<string, Item>>(new Map());
  const [sections, setSections] = useState<ShopSection[]>([]);
  const [editing, setEditing] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  // Items whose question the seller just answered: their new price tag lands with a stamp.
  const [answered, setAnswered] = useState<Set<number>>(new Set());
  const questionsRef = useRef<HTMLElement>(null);

  const load = useCallback(async () => {
    const [review, list, secs] = await Promise.all([
      api<ReviewData>(`/api/v1/jobs/${jobId}/review`),
      api<{ items: Item[] }>("/api/v1/items"),
      api<{ sections: ShopSection[] }>("/api/v1/sections"),
    ]);
    setData(review);
    setItems(new Map(list.items.map((it) => [it.id, it])));
    setSections(secs.sections);
  }, [jobId]);

  useEffect(() => {
    void load().catch(() => setError(t("app.offline")));
  }, [load, t]);

  if (!data) return <Shell title={t("review.questions")}>{error ? <p className="error">{error}</p> : <p>{t("app.loading")}</p>}</Shell>;

  const hindi = i18n.language === "hi";
  const title = (p: ReviewProduct) => (hindi ? p.title_hi : p.title_en);
  const byIdx = new Map(data.products.map((p) => [p.idx, p]));
  const open = data.flags.filter((f) => f.status === "open");
  const visible = data.products.filter((p) => !p.removed);
  const needsCheck = new Set(open.flatMap((f) => (f.product_idx ? [f.product_idx] : f.candidates)));

  const resolve = async (flag: Flag, body: Record<string, unknown>) => {
    setError("");
    try {
      await api(`/api/v1/jobs/${jobId}/flags/${flag.id}/resolve`, { method: "POST", json: body });
      const touched = typeof body.product_idx === "number" ? [body.product_idx] : flag.product_idx ? [flag.product_idx] : flag.candidates;
      setAnswered((s) => new Set([...s, ...touched]));
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("app.generic_error"));
    }
  };

  const putBack = async (p: ReviewProduct) => {
    if (!window.confirm(t("review.put_back_confirm"))) return;
    await api(`/api/v1/jobs/${jobId}/products/${p.idx}`, { method: "PATCH", json: { removed: false } }).catch(() => undefined);
    await load();
  };

  const publish = async () => {
    setBusy(true);
    setError("");
    try {
      await api(`/api/v1/jobs/${jobId}/publish`, { method: "POST" });
      navigate("/home");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("app.generic_error"));
    } finally {
      setBusy(false);
    }
  };

  const onlyPrices = open.every((f) => PRICE_KINDS.has(f.kind));
  const footer = open.length ? (
    <button type="button" className="btn primary" onClick={() => questionsRef.current?.scrollIntoView({ behavior: "smooth" })}>
      {onlyPrices ? t("review.fix", { count: open.length }) : t("review.answer", { count: open.length })}
    </button>
  ) : (
    <button type="button" className="btn primary" onClick={publish} disabled={busy}>
      {busy ? t("review.publishing") : t("review.publish")}
    </button>
  );
  const openItem = editing ? items.get(editing) : undefined;

  return (
    <Shell title={t("review.found", { count: visible.length })} footer={footer} back="/videos">
      <p className={open.length ? "error" : "ok"}>
        {open.length
          ? onlyPrices ? t("review.check", { count: open.length }) : t("review.check_questions", { count: open.length })
          : t("review.all_right")}
      </p>
      <p className="muted small">{t("review.tap_hint")}</p>
      <div className="tiles">
        {data.products.map((p) => (
          <button type="button" key={p.idx} className={`tile${p.removed ? " removed" : ""}`}
            onClick={() => (p.removed ? void putBack(p) : setEditing(p.id))}>
            <span className="photo">
              {p.image_url ? (
                <img src={apiUrl(p.image_url)} alt="" loading="lazy" />
              ) : (
                <span className="nophoto"><Icon name="camera" size={32} /></span>
              )}
              {p.removed ? (
                <span className="checktag">{t("review.removed")}</span>
              ) : p.price_inr !== null && !needsCheck.has(p.idx) ? (
                <PriceTag value={p.price_inr} stamp={answered.has(p.idx)} />
              ) : (
                <span className="checktag">
                  <Icon name="alert" size={16} />
                  {p.price_inr !== null ? formatINR(p.price_inr) : t("review.add_price")}
                </span>
              )}
            </span>
            <span className="body">
              <span className="name">{title(p)}</span>
              {!p.removed && p.mrp_inr && p.price_inr !== null && p.mrp_inr > p.price_inr ? (
                <span className="meta">{t("shop.mrp")} <s>{formatINR(p.mrp_inr)}</s></span>
              ) : null}
              <span className={p.image_url ? "meta" : "meta warn"}>
                {p.removed ? t("review.tap_to_put_back") : !p.image_url ? t("review.add_photo") : p.ai_background ? t("review.ai_label") : "\u00a0"}
              </span>
            </span>
          </button>
        ))}
      </div>

      {open.length ? (
        <section className="questions" ref={questionsRef} aria-labelledby="qh">
          <h2 id="qh">{t("review.questions")}</h2>
          {open.map((flag) => (
            <Question key={flag.id} flag={flag} itemName={(idx) => (byIdx.get(idx) ? title(byIdx.get(idx)!) : `#${idx}`)}
              onResolve={(body) => resolve(flag, body)}
              onPhoto={flag.product_idx && byIdx.get(flag.product_idx) ? () => setEditing(byIdx.get(flag.product_idx!)!.id) : undefined} />
          ))}
        </section>
      ) : null}
      {error ? <p className="error" role="alert">{error}</p> : null}

      {openItem ? (
        <ItemSheet item={openItem} sections={sections} onClose={() => { setEditing(null); void load(); }}
          onSaved={(next, removedId) => {
            if (removedId) setEditing(null);
            if (next) setItems((m) => new Map(m).set(next.id, next));
            void load();
          }} />
      ) : null}
    </Shell>
  );
}

function Question({ flag, itemName, onResolve, onPhoto }: {
  flag: Flag;
  itemName: (idx: number) => string;
  onResolve: (body: Record<string, unknown>) => Promise<void>;
  onPhoto?: () => void;
}) {
  const { t } = useTranslation();
  const [price, setPrice] = useState("");
  const [target, setTarget] = useState<number | null>(flag.product_idx ?? (flag.candidates.length === 1 ? flag.candidates[0] : null));
  const rupee = (v: unknown) => (typeof v === "number" ? formatINR(v) : String(v ?? ""));
  const sub = flag.kind === "price_conflict" ? flag.question_key.split(".").pop() : "";
  const key = flag.kind === "price_conflict" ? `review.q.price_conflict_${sub}` : `review.q.${flag.kind}`;
  const text = t(key, {
    item: flag.product_idx ? itemName(flag.product_idx) : "",
    price: rupee(flag.params.price),
    first: rupee(flag.params.first),
    second: rupee(flag.params.second),
  });

  const setTo = (value: number, product = target) => onResolve({ action: "set_price", price_inr: value, product_idx: product });
  const submitOther = (e: FormEvent) => {
    e.preventDefault();
    const value = Number.parseInt(price, 10);
    if (value > 0) void setTo(value);
  };

  return (
    <article className="question">
      <p>{text}</p>
      {flag.kind === "ambiguous_price" ? (
        <div className="row" role="group">
          {flag.candidates.map((idx) => (
            <button type="button" key={idx} className="btn small" onClick={() => void setTo(flag.options[0], idx)}>
              {itemName(idx)}
            </button>
          ))}
          <button type="button" className="btn small quiet" onClick={() => void onResolve({ action: "dismiss" })}>
            {t("review.none_of_these")}
          </button>
        </div>
      ) : null}
      {flag.kind === "duplicate" ? (
        <div className="row">
          <button type="button" className="btn small" onClick={() => void onResolve({ action: "remove_item" })}>{t("review.remove_this")}</button>
          <button type="button" className="btn small quiet" onClick={() => void onResolve({ action: "dismiss" })}>{t("review.keep_both")}</button>
        </div>
      ) : null}
      {flag.kind === "low_conf_mask" ? (
        <div className="row">
          {onPhoto ? (
            <button type="button" className="btn small primary" onClick={onPhoto}><Icon name="camera" size={18} />{t("review.change_photo")}</button>
          ) : null}
          <button type="button" className="btn small" onClick={() => void onResolve({ action: "dismiss" })}>{t("review.photo_fine")}</button>
          <button type="button" className="btn small danger" onClick={() => void onResolve({ action: "remove_item" })}>{t("review.remove")}</button>
        </div>
      ) : null}
      {["price_conflict", "implausible_price", "uncertain_price"].includes(flag.kind) ? (
        <div className="row">
          {flag.options.map((value) => (
            <button type="button" key={value} className="btn small price" onClick={() => void setTo(value)}>
              {flag.kind === "price_conflict" ? formatINR(value) : t("review.yes_price", { price: formatINR(value) })}
            </button>
          ))}
        </div>
      ) : null}
      {["price_conflict", "implausible_price", "uncertain_price", "missing_price"].includes(flag.kind) && target !== null ? (
        <form className="row" onSubmit={submitOther}>
          <input inputMode="numeric" pattern="[0-9]*" aria-label={flag.kind === "missing_price" ? t("review.price_label") : t("review.other_price")}
            placeholder={flag.kind === "missing_price" ? t("review.price_label") : t("review.other_price")}
            value={price} onChange={(e) => setPrice(e.target.value.replace(/\D/g, ""))} />
          <button type="submit" className="btn small" disabled={!price}>{t("review.set_price")}</button>
          {flag.kind === "missing_price" ? (
            <button type="button" className="btn small danger" onClick={() => void onResolve({ action: "remove_item" })}>{t("review.remove")}</button>
          ) : null}
        </form>
      ) : null}
      {target === null && flag.kind !== "ambiguous_price" ? (
        <div className="row">{flag.candidates.map((idx) => (
          <button type="button" key={idx} className="btn small" onClick={() => setTarget(idx)}>{itemName(idx)}</button>
        ))}</div>
      ) : null}
    </article>
  );
}
