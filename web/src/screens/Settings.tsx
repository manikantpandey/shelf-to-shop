import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { api, apiUrl, ApiError, type Workspace } from "../api";
import { Icon } from "../components/Icon";
import { formatPhone } from "../format";
import { setLanguage } from "../i18n";
import { useSession } from "../session";
import { Shell } from "../Shell";

export function Settings() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { me, setMe } = useSession();
  const ws = me!.workspace;
  const [name, setName] = useState(ws.name);
  const [whatsapp, setWhatsapp] = useState(formatPhone(ws.whatsapp));
  const [aiMark, setAiMark] = useState(ws.ai_mark);
  const [days, setDays] = useState(ws.raw_retention_days);
  const [status, setStatus] = useState("");
  const [confirm, setConfirm] = useState("");
  const [deleteError, setDeleteError] = useState("");

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setStatus("");
    try {
      const res = await api<{ workspace: Workspace }>("/api/v1/workspace", {
        method: "PATCH",
        json: { name, whatsapp, ai_mark: aiMark, raw_retention_days: days },
      });
      setMe({ ...me!, workspace: res.workspace });
      setStatus(t("settings.saved"));
    } catch (err) {
      setStatus(err instanceof ApiError ? err.message : t("app.generic_error"));
    }
  };

  const deleteAll = async () => {
    setDeleteError("");
    try {
      await api("/api/v1/privacy/delete", { method: "POST", json: { confirm } });
      setMe(null);
      navigate("/signin");
    } catch (err) {
      setDeleteError(err instanceof ApiError ? err.message : t("app.offline"));
    }
  };

  const signOut = async () => {
    await api("/api/v1/auth/logout", { method: "POST" }).catch(() => undefined);
    setMe(null);
    navigate("/signin");
  };

  return (
    <Shell title={t("settings.title")}>
      <form onSubmit={save} className="stack">
        <section className="panel" aria-labelledby="shop-h">
          <h2 id="shop-h">{t("settings.shop")}</h2>
          <div className="field">
            <label htmlFor="s-name">{t("settings.name")}</label>
            <input id="s-name" value={name} minLength={2} maxLength={80} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="s-wa">{t("settings.whatsapp")}</label>
            <input id="s-wa" type="tel" inputMode="tel" value={whatsapp} onChange={(e) => setWhatsapp(e.target.value)} />
            <span className="hint">{t("settings.whatsapp_hint")}</span>
          </div>
          <div className="field">
            <span className="label">{t("settings.language")}</span>
            <div className="row">
              <button type="button" className="chip" aria-pressed={ws.language === "en"} onClick={() => setLanguage("en")}>English</button>
              <button type="button" className="chip" lang="hi" aria-pressed={ws.language === "hi"} onClick={() => setLanguage("hi")}>हिंदी</button>
            </div>
          </div>
        </section>
        <section className="panel" aria-labelledby="photos-h">
          <h2 id="photos-h">{t("settings.photos")}</h2>
          <label className="check">
            <input type="checkbox" checked={aiMark} onChange={(e) => setAiMark(e.target.checked)} />
            <span>{t("settings.ai_mark")}</span>
          </label>
        </section>
        <section className="panel" aria-labelledby="data-h">
          <h2 id="data-h">{t("settings.data")}</h2>
          <div className="field">
            <label htmlFor="s-days">{t("settings.retention")}</label>
            <input id="s-days" type="number" min={1} max={30} value={days} onChange={(e) => setDays(Number(e.target.value))} />
            <span className="hint">{t("settings.retention_hint")}</span>
          </div>
          <p className="muted small">{t("settings.orders_retention")}</p>
          <a className="btn small" href={apiUrl("/api/v1/privacy/export")} download>
            <Icon name="download" size={18} />{t("settings.export")}
          </a>
        </section>
        <div className="row">
          <button type="submit" className="btn primary">{t("settings.save")}</button>
          {status ? <p role="status" className="ok">{status}</p> : null}
        </div>
      </form>
      <button type="button" className="btn" onClick={signOut} style={{ alignSelf: "flex-start" }}>{t("settings.signout")}</button>

      <section className="panel" aria-labelledby="del-h">
        <h2 id="del-h">{t("settings.delete_title")}</h2>
        <p className="muted small">{t("settings.delete_body")}</p>
        <div className="field">
          <label htmlFor="del-confirm">{t("settings.delete_type", { name: ws.name })}</label>
          <input id="del-confirm" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="off" />
        </div>
        <button type="button" className="btn danger" style={{ alignSelf: "flex-start" }}
          disabled={confirm.trim().toLowerCase() !== ws.name.trim().toLowerCase()} onClick={() => void deleteAll()}>
          <Icon name="trash" size={18} />{t("settings.delete")}
        </button>
        {deleteError ? <p className="error" role="alert">{deleteError}</p> : null}
      </section>
    </Shell>
  );
}
