import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { api, ApiError, setCsrf, type Workspace } from "../api";
import { useSession } from "../session";
import { Shell } from "../Shell";

export function SignIn() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { refresh } = useSession();
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await api<{ workspace: Workspace; csrf_token: string }>("/api/v1/auth/demo", {
        method: "POST",
        json: { shop_name: name.trim() },
      });
      setCsrf(res.csrf_token);
      await refresh();
      navigate("/setup");
    } catch (err) {
      setError(err instanceof ApiError && err.code === "offline" ? t("app.offline") : t("app.generic_error"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Shell
      title={t("app.name")}
      footer={
        <button type="submit" form="signin" className="btn primary" disabled={busy || name.trim().length < 2}>
          {t("signin.start")}
        </button>
      }
    >
      <form id="signin" onSubmit={submit} className="body">
        <h2>{t("signin.title")}</h2>
        <p className="muted">{t("signin.body")}</p>
        <div className="field">
          <label htmlFor="shop">{t("signin.shop_label")}</label>
          <input id="shop" required minLength={2} maxLength={80} value={name} autoComplete="organization"
            onChange={(e) => setName(e.target.value)} aria-describedby="shop-hint" />
          <span id="shop-hint" className="hint">{t("signin.shop_hint")}</span>
        </div>
        {error ? <p className="error" role="alert">{error}</p> : null}
      </form>
    </Shell>
  );
}
