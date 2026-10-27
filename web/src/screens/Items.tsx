import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api, apiUrl, type Item } from "../api";
import { Icon } from "../components/Icon";
import { PriceTag } from "../components/PriceTag";
import { Shell } from "../Shell";
import { ItemSheet } from "./ItemSheet";

type Filter = "all" | "live" | "sold_out" | "draft";

export function ItemTile({ item, onOpen }: { item: Item; onOpen: () => void }) {
  const { t, i18n } = useTranslation();
  const title = i18n.language === "hi" ? item.title_hi : item.title_en;
  return (
    <button type="button" className={`tile${item.sold_out ? " soldout" : ""}`} onClick={onOpen}>
      <span className="photo">
        {item.image_url ? (
          <img src={apiUrl(item.image_url)} alt="" loading="lazy" />
        ) : (
          <span className="nophoto"><Icon name="camera" size={32} /></span>
        )}
        {item.price_inr !== null ? (
          <PriceTag value={item.price_inr} />
        ) : (
          <span className="checktag"><Icon name="alert" size={16} />{t("items.no_price")}</span>
        )}
        {item.sold_out ? <span className="soldout-band">{t("items.sold_out")}</span> : null}
      </span>
      <span className="body">
        <span className="name">{title}</span>
        <span className={item.published && !item.live ? "meta warn" : "meta"}>
          {item.live ? t("items.on_shop") : item.published ? (item.image_url ? t("items.needs_price") : t("items.needs_photo")) : t("items.not_yet")}
          {item.image_source === "openfoodfacts" ? `, ${t("items.pack_photo")}` : ""}
          {item.image_source === "upload" ? `, ${t("items.your_photo")}` : ""}
          {item.ai_background ? `, ${t("items.ai_background")}` : ""}
        </span>
      </span>
    </button>
  );
}

export function Items() {
  const { t, i18n } = useTranslation();
  const [items, setItems] = useState<Item[] | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<Item | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<{ items: Item[] }>("/api/v1/items")
      .then((d) => setItems(d.items))
      .catch(() => setError(t("app.offline")));
  }, [t]);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (items ?? []).filter((it) => {
      if (filter === "live" && !(it.live && !it.sold_out)) return false;
      if (filter === "sold_out" && !it.sold_out) return false;
      if (filter === "draft" && it.live) return false;
      return !q || `${it.title_en} ${it.title_hi} ${it.brand ?? ""}`.toLowerCase().includes(q);
    });
  }, [items, filter, query]);

  const count = (f: Filter) =>
    (items ?? []).filter((it) =>
      f === "all" ? true : f === "live" ? it.live && !it.sold_out : f === "sold_out" ? it.sold_out : !it.live,
    ).length;

  const saved = (next: Item | null, removedId?: string) => {
    setItems((list) => {
      if (!list) return list;
      if (removedId) return list.filter((it) => it.id !== removedId);
      return next ? list.map((it) => (it.id === next.id ? next : it)) : list;
    });
    if (next) setOpen(next);
  };

  return (
    <Shell title={t("items.title")}>
      <div className="search">
        <Icon name="search" size={20} />
        <input className="input" type="search" value={query} onChange={(e) => setQuery(e.target.value)}
          placeholder={t("items.search")} aria-label={t("items.search")} lang={i18n.language} />
      </div>
      <div className="chips" role="group" aria-label={t("items.filter")}>
        {(["all", "live", "sold_out", "draft"] as Filter[]).map((f) => (
          <button type="button" key={f} className="chip" aria-pressed={filter === f} onClick={() => setFilter(f)}>
            {t(`items.f_${f}`, { count: count(f) })}
          </button>
        ))}
      </div>
      {error ? <p className="error" role="alert">{error}</p> : null}
      {items === null && !error ? <p className="muted">{t("app.loading")}</p> : null}
      {items && items.length === 0 ? (
        <div className="panel">
          <p>{t("items.empty")}</p>
          <Link className="btn record-btn" to="/record"><Icon name="record" />{t("nav.record")}</Link>
        </div>
      ) : null}
      {items && items.length > 0 && shown.length === 0 ? <p className="muted">{t("items.none_match")}</p> : null}
      <div className="tiles wide">
        {shown.map((it) => <ItemTile key={it.id} item={it} onOpen={() => setOpen(it)} />)}
      </div>
      {open ? <ItemSheet item={open} onClose={() => setOpen(null)} onSaved={saved} /> : null}
    </Shell>
  );
}
