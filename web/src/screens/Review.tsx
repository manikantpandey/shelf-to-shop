import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import { api, apiUrl, ApiError, type Flag, type Review as ReviewData, type ReviewProduct } from "../api";
import { Icon } from "../components/Icon";
import { PriceTag } from "../components/PriceTag";
import { formatINR } from "../format";
import { Shell } from "../Shell";

export function Review() {
  const { t, i18n } = useTranslation();
  const { jobId = "" } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState<ReviewData | null>(null);
  const [editing, setEditing] = useState<ReviewProduct | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const questionsRef = useRef<HTMLElement>(null);

  const load = useCallback(async () => {
    setData(await api<ReviewData>(`/api/v1/jobs/${jobId}/review`));
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
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("app.generic_error"));
    }
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

  const footer = open.length ? (
    <button type="button" className="btn primary" onClick={() => questionsRef.current?.scrollIntoView({ behavior: "smooth" })}>
      {t("review.fix", { count: open.length })}
    </button>
  ) : (
    <button type="button" className="btn primary" onClick={publish} disabled={busy}>
      {busy ? t("review.publishing") : t("review.publish")}
    </button>
  );

  return (
    <Shell title={t("review.found", { count: visible.length })} footer={footer} back="/videos">
      <p className={open.length ? "error" : "ok"}>
        {open.length ? t("review.check", { count: open.length }) : t("review.all_right")}
      </p>
      <div className="tiles">
        {data.products.map((p) => (
          <button type="button" key={p.idx} className={`tile${p.removed ? " removed" : ""}`} onClick={() => setEditing(p)}>
            <span className="photo">
              {p.image_url ? <img src={apiUrl(p.image_url)} alt="" loading="lazy" /> : null}
              {p.removed ? (
                <span className="checktag">{t("review.removed")}</span>
              ) : p.price_inr !== null && !needsCheck.has(p.idx) ? (
                <PriceTag value={p.price_inr} />
              ) : (
                <span className="checktag">
                  <Icon name="alert" size={16} />
                  {p.price_inr !== null ? formatINR(p.price_inr) : t("review.add_price")}
                </span>
              )}
            </span>
            <span className="body">
              <span className="name">{title(p)}</span>
              {p.ai_background ? <span className="meta">{t("review.ai_label")}</span> : null}
            </span>
          </button>
        ))}
      </div>

      {open.length ? (
        <section className="questions" ref={questionsRef} aria-labelledby="qh">
          <h2 id="qh">{t("review.questions")}</h2>
          {open.map((flag) => (
            <Question key={flag.id} flag={flag} itemName={(idx) => (byIdx.get(idx) ? title(byIdx.get(idx)!) : `#${idx}`)}
              onResolve={(body) => resolve(flag, body)} />
          ))}
        </section>
      ) : null}
      {error ? <p className="error" role="alert">{error}</p> : null}

      {editing ? <EditSheet product={editing} jobId={jobId} onClose={() => setEditing(null)} onSaved={load} /> : null}
    </Shell>
  );
}

function Question({ flag, itemName, onResolve }: {
  flag: Flag;
  itemName: (idx: number) => string;
  onResolve: (body: Record<string, unknown>) => Promise<void>;
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
          <input inputMode="numeric" pattern="[0-9]*" aria-label={t("review.other_price")} placeholder={t("review.other_price")}
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

function EditSheet({ product, jobId, onClose, onSaved }: {
  product: ReviewProduct;
  jobId: string;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const { t } = useTranslation();
  const [price, setPrice] = useState(product.price_inr?.toString() ?? "");
  const [en, setEn] = useState(product.title_en);
  const [hi, setHi] = useState(product.title_hi);
  const [error, setError] = useState("");

  const save = async (body: Record<string, unknown>) => {
    try {
      await api(`/api/v1/jobs/${jobId}/products/${product.idx}`, { method: "PATCH", json: body });
      await onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("app.generic_error"));
    }
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const body: Record<string, unknown> = { title_en: en, title_hi: hi };
    const value = Number.parseInt(price, 10);
    if (value > 0 && value !== product.price_inr) body.price_inr = value;
    void save(body);
  };

  return (
    <div className="scrim" role="presentation" onClick={onClose}>
      <form className="sheet" role="dialog" aria-modal="true" aria-labelledby="edit-title" onSubmit={submit}
        onClick={(e) => e.stopPropagation()}>
        <h2 id="edit-title">{t("review.edit_title")}</h2>
        <div className="field">
          <label htmlFor="p-price">{t("review.price_label")}</label>
          <input id="p-price" className="price-input" inputMode="numeric" pattern="[0-9]*" value={price} autoFocus
            onChange={(e) => setPrice(e.target.value.replace(/\D/g, ""))} />
        </div>
        <div className="field">
          <label htmlFor="p-en">{t("review.name_en")}</label>
          <input id="p-en" value={en} maxLength={200} onChange={(e) => setEn(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="p-hi">{t("review.name_hi")}</label>
          <input id="p-hi" lang="hi" value={hi} maxLength={200} onChange={(e) => setHi(e.target.value)} />
        </div>
        {error ? <p className="error" role="alert">{error}</p> : null}
        <button type="submit" className="btn primary">{t("review.save")}</button>
        <button type="button" className={`btn ${product.removed ? "" : "danger"}`}
          onClick={() => void save({ removed: !product.removed })}>
          {product.removed ? t("review.restore") : t("review.remove")}
        </button>
        <button type="button" className="btn quiet" onClick={onClose}>{t("review.close")}</button>
      </form>
    </div>
  );
}
