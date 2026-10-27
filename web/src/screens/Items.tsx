import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api, apiUrl, ApiError, type Item, type ItemSaved, type ShopSection } from "../api";
import { Icon } from "../components/Icon";
import { PriceTag } from "../components/PriceTag";
import { formatINR } from "../format";
import { Shell } from "../Shell";
import { ItemSheet } from "./ItemSheet";

type Filter = "all" | "live" | "sold_out" | "hidden" | "draft";
type Bulk = "sold_out" | "in_stock" | "hide" | "show" | "remove" | "price_add" | "price_percent" | "section";

function matches(it: Item, f: Filter): boolean {
  if (f === "live") return it.live && !it.sold_out;
  if (f === "sold_out") return it.sold_out;
  if (f === "hidden") return it.hidden;
  if (f === "draft") return !it.live && !it.hidden;
  return true;
}

export function ItemTile({ item, onOpen, selecting, selected, onSelect, onQuick }: {
  item: Item;
  onOpen: () => void;
  selecting?: boolean;
  selected?: boolean;
  onSelect?: (on: boolean) => void;
  onQuick?: () => void;
}) {
  const { t, i18n } = useTranslation();
  const title = i18n.language === "hi" ? item.title_hi : item.title_en;
  const state = item.hidden
    ? t("items.hidden")
    : item.live
      ? t("items.on_shop")
      : item.published
        ? item.image_url ? t("items.needs_price") : t("items.needs_photo")
        : t("items.not_yet");
  return (
    <div className="tile-wrap">
      {selecting ? (
        <input type="checkbox" className="pick" checked={selected} onChange={(e) => onSelect?.(e.target.checked)}
          aria-label={t("items.select_item", { name: title })} />
      ) : onQuick && item.live ? (
        <button type="button" className="quick" aria-pressed={item.sold_out} onClick={onQuick}>
          {item.sold_out ? t("items.sold_out") : t("items.in_stock")}
        </button>
      ) : null}
      <button type="button"
        className={`tile${item.sold_out ? " soldout" : ""}${item.hidden ? " hidden-item" : ""}${selected ? " selected" : ""}`}
        onClick={selecting ? () => onSelect?.(!selected) : onOpen}>
        <span className="photo">
          {item.image_url ? (
            <img src={apiUrl(item.image_url)} alt="" loading="lazy" />
          ) : (
            <span className="nophoto"><Icon name="camera" size={32} /></span>
          )}
          {item.featured && !selecting ? <span className="pin">{t("items.pinned")}</span> : null}
          {item.price_inr !== null ? (
            <PriceTag value={item.price_inr} />
          ) : (
            <span className="checktag"><Icon name="alert" size={16} />{t("items.no_price")}</span>
          )}
        </span>
        <span className="body">
          <span className="name">{title}</span>
          <span className={item.published && !item.live && !item.hidden ? "meta warn" : "meta"}>
            {state}
            {item.mrp_inr && item.price_inr !== null && item.mrp_inr > item.price_inr ? <span className="mrp">{formatINR(item.mrp_inr)}</span> : null}
          </span>
        </span>
      </button>
    </div>
  );
}

function AddItem({ sections, onAdded, onClose }: { sections: ShopSection[]; onAdded: (item: Item) => void; onClose: () => void }) {
  const { t, i18n } = useTranslation();
  const [name, setName] = useState("");
  const [price, setPrice] = useState("");
  const [mrp, setMrp] = useState("");
  const [section, setSection] = useState(sections[0]?.id ?? "");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await api<ItemSaved>("/api/v1/items", {
        method: "POST",
        json: {
          title_en: name.trim(),
          price_inr: Number.parseInt(price, 10),
          mrp_inr: mrp ? Number.parseInt(mrp, 10) : null,
          section_id: section || null,
        },
      });
      onAdded(res.item);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("app.offline"));
      setBusy(false);
    }
  };

  return (
    <div className="scrim" role="presentation" onClick={onClose}>
      <form className="sheet" role="dialog" aria-modal="true" aria-labelledby="add-h" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <div className="sheet-head">
          <h2 id="add-h">{t("items.add_title")}</h2>
          <button type="button" className="icon-btn" onClick={onClose} aria-label={t("sheet.close")}><Icon name="close" /></button>
        </div>
        <p className="muted small">{t("items.add_hint")}</p>
        <div className="field">
          <label htmlFor="ai-name">{t("sheet.name_en")}</label>
          <input id="ai-name" required maxLength={200} value={name} onChange={(e) => setName(e.target.value)} autoFocus />
        </div>
        <div className="grid-2">
          <div className="field">
            <label htmlFor="ai-price">{t("sheet.price")}</label>
            <input id="ai-price" className="price-input" required inputMode="numeric" value={price}
              onChange={(e) => setPrice(e.target.value.replace(/\D/g, ""))} />
          </div>
          <div className="field">
            <label htmlFor="ai-mrp">{t("sheet.mrp")}</label>
            <input id="ai-mrp" inputMode="numeric" value={mrp} onChange={(e) => setMrp(e.target.value.replace(/\D/g, ""))} />
          </div>
        </div>
        {sections.length ? (
          <div className="field">
            <label htmlFor="ai-sec">{t("sheet.section")}</label>
            <select id="ai-sec" className="input" value={section} onChange={(e) => setSection(e.target.value)}>
              {sections.map((s) => <option key={s.id} value={s.id}>{i18n.language === "hi" ? s.name_hi : s.name_en}</option>)}
            </select>
          </div>
        ) : null}
        {error ? <p className="error" role="alert">{error}</p> : null}
        <button type="submit" className="btn primary" disabled={busy || !name.trim() || !price}>{t("items.add_next")}</button>
      </form>
    </div>
  );
}

export function Items() {
  const { t, i18n } = useTranslation();
  const [items, setItems] = useState<Item[] | null>(null);
  const [sections, setSections] = useState<ShopSection[]>([]);
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<Item | null>(null);
  const [adding, setAdding] = useState(false);
  const [selecting, setSelecting] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkValue, setBulkValue] = useState("");
  const [bulkSection, setBulkSection] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const hindi = i18n.language === "hi";

  const load = async () => {
    const [i, s] = await Promise.all([
      api<{ items: Item[] }>("/api/v1/items"),
      api<{ sections: ShopSection[] }>("/api/v1/sections"),
    ]);
    setItems(i.items);
    setSections(s.sections);
  };

  useEffect(() => {
    load().catch(() => setError(t("app.offline")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t]);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (items ?? []).filter((it) =>
      matches(it, filter) && (!q || `${it.title_en} ${it.title_hi} ${it.brand ?? ""}`.toLowerCase().includes(q)));
  }, [items, filter, query]);

  const groups = useMemo(() => {
    const bySection = new Map<string, Item[]>();
    for (const it of shown) {
      const key = it.section_id ?? "";
      bySection.set(key, [...(bySection.get(key) ?? []), it]);
    }
    const ordered = sections.filter((s) => bySection.has(s.id)).map((s) => ({ section: s, list: bySection.get(s.id)! }));
    if (bySection.has("")) ordered.push({ section: { id: "", name_en: t("items.no_section"), name_hi: t("items.no_section") }, list: bySection.get("")! });
    return ordered;
  }, [shown, sections, t]);

  const count = (f: Filter) => (items ?? []).filter((it) => matches(it, f)).length;

  const replace = (list: Item[]) => setItems((cur) => cur?.map((it) => list.find((n) => n.id === it.id) ?? it) ?? cur);

  const saved = (next: Item | null, removedId?: string) => {
    setItems((list) => {
      if (!list) return list;
      if (removedId) return list.filter((it) => it.id !== removedId);
      if (!next) return list;
      return list.some((it) => it.id === next.id) ? list.map((it) => (it.id === next.id ? next : it)) : [next, ...list];
    });
    if (next) setOpen(next);
  };

  const quick = async (item: Item) => {
    try {
      const res = await api<ItemSaved>(`/api/v1/items/${item.id}`, { method: "PATCH", json: { sold_out: !item.sold_out } });
      replace([res.item]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("app.offline"));
    }
  };

  const bulk = async (action: Bulk) => {
    setError("");
    setStatus("");
    if (action === "remove" && !window.confirm(t("items.bulk_remove_confirm", { count: selected.size }))) return;
    const body: Record<string, unknown> = { ids: [...selected], action };
    if (action === "price_add" || action === "price_percent") body.value = Number.parseInt(bulkValue, 10);
    if (action === "section") body.section_id = bulkSection;
    try {
      const res = await api<{ items: Item[] }>("/api/v1/items/bulk", { method: "POST", json: body });
      if (action === "remove") setItems((cur) => cur?.filter((it) => !selected.has(it.id)) ?? cur);
      else replace(res.items);
      setStatus(t("items.bulk_done", { count: res.items.length }));
      setSelected(new Set());
      setSelecting(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("app.offline"));
    }
  };

  const toggle = (id: string, on: boolean) =>
    setSelected((cur) => {
      const next = new Set(cur);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });

  const value = Number.parseInt(bulkValue, 10);
  return (
    <Shell
      title={t("items.title")}
      actions={
        <>
          <button type="button" className="btn primary" onClick={() => setAdding(true)}><Icon name="plus" />{t("items.add")}</button>
          <button type="button" className="btn" aria-pressed={selecting} onClick={() => { setSelecting(!selecting); setSelected(new Set()); }}>
            <Icon name="check" />{selecting ? t("items.done_selecting") : t("items.select")}
          </button>
          <Link className="btn quiet" to="/sections"><Icon name="sections" />{t("items.arrange")}</Link>
        </>
      }
    >
      <div className="search">
        <Icon name="search" size={20} />
        <input className="input" type="search" value={query} onChange={(e) => setQuery(e.target.value)}
          placeholder={t("items.search")} aria-label={t("items.search")} />
      </div>
      <div className="chips" role="group" aria-label={t("items.filter")}>
        {(["all", "live", "sold_out", "hidden", "draft"] as Filter[]).map((f) => (
          <button type="button" key={f} className="chip" aria-pressed={filter === f} onClick={() => setFilter(f)}>
            {t(`items.f_${f}`, { count: count(f) })}
          </button>
        ))}
      </div>
      {status ? <p className="ok" role="status">{status}</p> : null}
      {error ? <p className="error" role="alert">{error}</p> : null}
      {items === null && !error ? <p className="muted">{t("app.loading")}</p> : null}
      {items && items.length === 0 ? (
        <div className="panel">
          <p>{t("items.empty")}</p>
          <div className="row">
            <Link className="btn record-btn" to="/record"><Icon name="record" />{t("nav.record")}</Link>
            <button type="button" className="btn" onClick={() => setAdding(true)}><Icon name="plus" />{t("items.add")}</button>
          </div>
        </div>
      ) : null}
      {items && items.length > 0 && shown.length === 0 ? <p className="muted">{t("items.none_match")}</p> : null}

      {groups.map(({ section, list }) => (
        <section key={section.id || "none"} aria-labelledby={`sec-${section.id || "none"}`} className="stack" style={{ gap: 8 }}>
          <div className="section-head">
            <h2 id={`sec-${section.id || "none"}`}>{hindi ? section.name_hi : section.name_en}</h2>
            <span className="muted small">{t("sections.items", { count: list.length })}</span>
          </div>
          <div className="tiles wide">
            {list.map((it) => (
              <ItemTile key={it.id} item={it} onOpen={() => setOpen(it)} selecting={selecting}
                selected={selected.has(it.id)} onSelect={(on) => toggle(it.id, on)} onQuick={() => void quick(it)} />
            ))}
          </div>
        </section>
      ))}

      {selecting && selected.size ? (
        <div className="actionbar" role="toolbar" aria-label={t("items.bulk")}>
          <span className="count">{t("items.selected", { count: selected.size })}</span>
          <button type="button" className="btn small" onClick={() => void bulk("sold_out")}>{t("items.sold_out")}</button>
          <button type="button" className="btn small" onClick={() => void bulk("in_stock")}>{t("items.in_stock")}</button>
          <button type="button" className="btn small" onClick={() => void bulk("hide")}>{t("items.hide")}</button>
          <button type="button" className="btn small" onClick={() => void bulk("show")}>{t("items.show")}</button>
          <input aria-label={t("items.price_change")} placeholder={t("items.price_change_eg")} inputMode="numeric" value={bulkValue}
            onChange={(e) => setBulkValue(e.target.value.replace(/[^\d-]/g, ""))} style={{ width: 90 }} />
          <button type="button" className="btn small" disabled={!value} onClick={() => void bulk("price_add")}>
            {t("items.price_add")}
          </button>
          <button type="button" className="btn small" disabled={!value} onClick={() => void bulk("price_percent")}>
            {t("items.price_percent")}
          </button>
          <select aria-label={t("sheet.section")} value={bulkSection} onChange={(e) => setBulkSection(e.target.value)}>
            <option value="">{t("items.move_to")}</option>
            {sections.map((s) => <option key={s.id} value={s.id}>{hindi ? s.name_hi : s.name_en}</option>)}
          </select>
          <button type="button" className="btn small" disabled={!bulkSection} onClick={() => void bulk("section")}>{t("items.move")}</button>
          <button type="button" className="btn small primary" onClick={() => void bulk("remove")}>{t("items.remove")}</button>
        </div>
      ) : null}

      {open ? <ItemSheet item={open} sections={sections} onClose={() => setOpen(null)} onSaved={saved} /> : null}
      {adding ? (
        <AddItem sections={sections} onClose={() => setAdding(false)} onAdded={(item) => {
          setAdding(false);
          saved(item);
        }} />
      ) : null}
    </Shell>
  );
}
