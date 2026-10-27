import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { api, ApiError, type Workspace } from "../api";
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

  const signOut = async () => {
    await api("/api/v1/auth/logout", { method: "POST" }).catch(() => undefined);
    setMe(null);
    navigate("/signin");
  };

  return (
    <Shell title={t("settings.title")}>
      <form onSubmit={save} className="body">
        <div className="field">
          <label htmlFor="s-name">{t("settings.name")}</label>
          <input id="s-name" value={name} minLength={2} maxLength={80} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="s-wa">{t("settings.whatsapp")}</label>
          <input id="s-wa" type="tel" inputMode="tel" value={whatsapp} onChange={(e) => setWhatsapp(e.target.value)} />
        </div>
        <div className="field">
          <span>{t("settings.language")}</span>
          <div className="row">
            <button type="button" className="btn small" aria-pressed={ws.language === "en"} onClick={() => setLanguage("en")}>English</button>
            <button type="button" className="btn small" lang="hi" aria-pressed={ws.language === "hi"} onClick={() => setLanguage("hi")}>हिंदी</button>
          </div>
        </div>
        <label className="check">
          <input type="checkbox" checked={aiMark} onChange={(e) => setAiMark(e.target.checked)} />
          <span>{t("settings.ai_mark")}</span>
        </label>
        <div className="field">
          <label htmlFor="s-days">{t("settings.retention")}</label>
          <input id="s-days" type="number" min={1} max={30} value={days} onChange={(e) => setDays(Number(e.target.value))} />
        </div>
        <button type="submit" className="btn primary">{t("settings.save")}</button>
        {status ? <p role="status">{status}</p> : null}
      </form>
      <button type="button" className="btn danger" onClick={signOut}>{t("settings.signout")}</button>
    </Shell>
  );
}
