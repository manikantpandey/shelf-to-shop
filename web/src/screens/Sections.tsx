import { useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, ApiError, type ShopSection } from "../api";
import { Icon } from "../components/Icon";
import { Shell } from "../Shell";

/** Sections of the shop page: rename (English and Hindi), move up or down, add, delete. */
export function Sections() {
  const { t } = useTranslation();
  const [sections, setSections] = useState<ShopSection[] | null>(null);
  const [names, setNames] = useState<Record<string, { en: string; hi: string }>>({});
  const [newName, setNewName] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  const show = (list: ShopSection[]) => {
    setSections(list);
    setNames(Object.fromEntries(list.map((s) => [s.id, { en: s.name_en, hi: s.name_hi }])));
  };

  useEffect(() => {
    api<{ sections: ShopSection[] }>("/api/v1/sections").then((d) => show(d.sections)).catch(() => setError(t("app.offline")));
  }, [t]);

  const run = async (path: string, init: { method: string; json?: unknown }, done?: string) => {
    setError("");
    setStatus("");
    try {
      const res = await api<{ sections: ShopSection[] }>(path, init);
      show(res.sections);
      if (done) setStatus(done);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("app.offline"));
    }
  };

  const move = (index: number, by: number) => {
    if (!sections) return;
    const ids = sections.map((s) => s.id);
    const [moved] = ids.splice(index, 1);
    ids.splice(index + by, 0, moved);
    void run("/api/v1/sections/order", { method: "POST", json: { ids } });
  };

  const rename = (s: ShopSection) => {
    const n = names[s.id];
    if (!n || (n.en === s.name_en && n.hi === s.name_hi) || !n.en.trim()) return;
    void run(`/api/v1/sections/${s.id}`, { method: "PATCH", json: { name_en: n.en, name_hi: n.hi || n.en } }, t("sections.saved"));
  };

  const remove = (s: ShopSection) => {
    if (!sections) return;
    const others = sections.filter((o) => o.id !== s.id);
    if (s.items && !others.length) {
      setError(t("sections.last"));
      return;
    }
    if (!window.confirm(s.items ? t("sections.delete_move", { name: others[0].name_en, count: s.items }) : t("sections.delete_confirm"))) return;
    const target = s.items ? `?move_to=${others[0].id}` : "";
    void run(`/api/v1/sections/${s.id}${target}`, { method: "DELETE" }, t("sections.deleted"));
  };

  const add = (e: FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    void run("/api/v1/sections", { method: "POST", json: { name_en: newName.trim() } }, t("sections.added"));
    setNewName("");
  };

  return (
    <Shell title={t("sections.title")} back="/more">
      <p className="muted">{t("sections.hint")}</p>
      {sections === null && !error ? <p className="muted">{t("app.loading")}</p> : null}
      {sections ? (
        <section className="panel">
          {sections.map((s, i) => (
            <div className="sec-row" key={s.id}>
              <div className="names">
                <input className="input" aria-label={t("sections.name_en")} value={names[s.id]?.en ?? ""} maxLength={60}
                  onChange={(e) => setNames((n) => ({ ...n, [s.id]: { ...n[s.id], en: e.target.value } }))} onBlur={() => rename(s)} />
                <input className="input" lang="hi" aria-label={t("sections.name_hi")} value={names[s.id]?.hi ?? ""} maxLength={60}
                  onChange={(e) => setNames((n) => ({ ...n, [s.id]: { ...n[s.id], hi: e.target.value } }))} onBlur={() => rename(s)} />
                <span className="muted small">{t("sections.items", { count: s.items ?? 0 })}</span>
              </div>
              <div className="moves">
                <button type="button" className="icon-btn" aria-label={t("sections.up")} disabled={i === 0} onClick={() => move(i, -1)}>
                  <Icon name="up" />
                </button>
                <button type="button" className="icon-btn" aria-label={t("sections.down")} disabled={i === sections.length - 1}
                  onClick={() => move(i, 1)}>
                  <Icon name="down" />
                </button>
                <button type="button" className="icon-btn" aria-label={t("sections.delete")} onClick={() => remove(s)}>
                  <Icon name="trash" />
                </button>
              </div>
            </div>
          ))}
        </section>
      ) : null}
      <form className="toolbar" onSubmit={add}>
        <input className="input grow" value={newName} maxLength={60} onChange={(e) => setNewName(e.target.value)}
          placeholder={t("sections.new_eg")} aria-label={t("sections.new")} />
        <button type="submit" className="btn" disabled={!newName.trim()}><Icon name="plus" />{t("sections.add")}</button>
      </form>
      {status ? <p className="ok" role="status">{status}</p> : null}
      {error ? <p className="error" role="alert">{error}</p> : null}
    </Shell>
  );
}
