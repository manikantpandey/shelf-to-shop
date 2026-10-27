import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useNavigate } from "react-router-dom";

import { api, ApiError } from "../api";
import { useSession } from "../session";
import { Shell } from "../Shell";

export function Setup() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { me, loading, refresh } = useSession();
  const [agree, setAgree] = useState(false);
  const [whatsapp, setWhatsapp] = useState(me?.workspace.whatsapp ?? "");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (loading) return null;
  if (!me) return <Navigate to="/signin" replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/api/v1/consents/account", { method: "POST" });
      await api("/api/v1/workspace", { method: "PATCH", json: { whatsapp } });
      await refresh();
      navigate("/record");
    } catch (err) {
      setError(err instanceof ApiError && err.status === 422 ? err.message : t("app.generic_error"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Shell
      title={t("setup.title")}
      footer={
        <button type="submit" form="setup" className="btn primary"
          disabled={busy || !agree || whatsapp.trim().length < 10}>
          {t("setup.continue")}
        </button>
      }
    >
      <form id="setup" onSubmit={submit} className="body">
        <section className="paper" aria-labelledby="notice">
          <h2 id="notice">{t("setup.notice_title")}</h2>
          <ul>
            <li>{t("setup.notice_1")}</li>
            <li>{t("setup.notice_2")}</li>
            <li>{t("setup.notice_3")}</li>
          </ul>
        </section>
        <label className="check">
          <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} required />
          <span>{t("setup.agree")}</span>
        </label>
        <div className="field">
          <label htmlFor="wa">{t("setup.whatsapp_label")}</label>
          <input id="wa" type="tel" inputMode="tel" required value={whatsapp} autoComplete="tel"
            onChange={(e) => setWhatsapp(e.target.value)} aria-describedby="wa-hint" placeholder="98765 43210" />
          <span id="wa-hint" className="hint">{t("setup.whatsapp_hint")}</span>
        </div>
        {error ? <p className="error" role="alert">{error}</p> : null}
      </form>
    </Shell>
  );
}
