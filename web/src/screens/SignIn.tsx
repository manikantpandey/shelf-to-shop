import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { api, ApiError, setCsrf, type Workspace } from "../api";
import { Signboard } from "../components/Signboard";
import { useSession } from "../session";
import { LanguageButton } from "../Shell";

export function SignIn() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { refresh } = useSession();
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<"" | "sample" | "own">("");

  const signIn = async (body: Record<string, unknown>, kind: "sample" | "own") => {
    setBusy(kind);
    setError("");
    try {
      const res = await api<{ workspace: Workspace; csrf_token: string }>("/api/v1/auth/demo", {
        method: "POST",
        json: { ...body, language: i18n.language === "hi" ? "hi" : "en" },
      });
      setCsrf(res.csrf_token);
      await refresh();
      navigate(kind === "sample" ? "/home" : "/setup");
    } catch (err) {
      if (err instanceof ApiError && err.code === "offline") setError(t("app.offline"));
      else if (err instanceof ApiError && err.code === "no_sample") setError(t("signin.no_sample"));
      else setError(t("app.generic_error"));
    } finally {
      setBusy("");
    }
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    void signIn({ shop_name: name.trim() }, "own");
  };

  return (
    <div className="welcome">
      <section className="welcome-hero">
        <div className="welcome-inner">
          <div className="spread">
            <span className="muted small">{t("app.demo_note")}</span>
            <LanguageButton />
          </div>
          <Signboard name={t("app.name")} />
          <h2>{t("signin.title")}</h2>
          <ol className="steps-mini">
            <li>{t("signin.step_1")}</li>
            <li>{t("signin.step_2")}</li>
            <li>{t("signin.step_3")}</li>
          </ol>
        </div>
      </section>
      <section className="welcome-act">
        <div className="welcome-inner">
          <div className="stack" style={{ gap: 8 }}>
            <button type="button" className="btn primary" disabled={busy !== ""} onClick={() => void signIn({ sample: true }, "sample")}>
              {busy === "sample" ? t("signin.opening") : t("signin.sample")}
            </button>
            <p className="muted small">{t("signin.sample_hint")}</p>
          </div>
          <p className="or">{t("signin.or")}</p>
          <form className="stack" style={{ gap: 12 }} onSubmit={submit}>
            <div className="field">
              <label htmlFor="shop">{t("signin.shop_label")}</label>
              <input id="shop" required minLength={2} maxLength={80} value={name} autoComplete="organization"
                onChange={(e) => setName(e.target.value)} aria-describedby="shop-hint" />
              <span id="shop-hint" className="hint">{t("signin.shop_hint")}</span>
            </div>
            <button type="submit" className="btn" disabled={busy !== "" || name.trim().length < 2}>
              {busy === "own" ? t("signin.opening") : t("signin.start")}
            </button>
          </form>
          {error ? <p className="error" role="alert">{error}</p> : null}
        </div>
      </section>
    </div>
  );
}
