import { useEffect, useState, type ChangeEvent, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api, apiUrl, ApiError, uploadImage, type Profile } from "../api";
import { Icon } from "../components/Icon";
import { Signboard } from "../components/Signboard";
import { useSession } from "../session";
import { Shell } from "../Shell";

/** What customers see at the top of the shop page: hours, delivery, payment, a photo, an offer. */
export function ShopProfile() {
  const { t } = useTranslation();
  const { me } = useSession();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const fill = (p: Profile) => {
    setProfile(p);
    setForm({
      hours: p.hours ?? "",
      delivery: p.delivery,
      delivery_note: p.delivery_note ?? "",
      min_order_inr: p.min_order_inr ? String(p.min_order_inr) : "",
      upi_id: p.upi_id ?? "",
      address: p.address ?? "",
      about: p.about ?? "",
      notice: p.notice ?? "",
    });
  };

  useEffect(() => {
    api<{ profile: Profile }>("/api/v1/profile").then((d) => fill(d.profile)).catch(() => setError(t("app.offline")));
  }, [t]);

  const set = (key: string) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setStatus("");
    setError("");
    try {
      const res = await api<{ profile: Profile }>("/api/v1/profile", {
        method: "PATCH",
        json: { ...form, min_order_inr: Number.parseInt(form.min_order_inr || "0", 10) || 0 },
      });
      fill(res.profile);
      setStatus(t("profile.saved"));
    } catch (err) {
      setError(err instanceof ApiError && err.status === 422 ? t("profile.check_upi") : t("app.offline"));
    } finally {
      setBusy(false);
    }
  };

  const pickLogo = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setError("");
    try {
      const res = await uploadImage("/api/v1/profile/logo", file);
      fill((res as { profile: Profile }).profile);
      setStatus(t("profile.photo_saved"));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("app.offline"));
    }
  };

  if (!profile) {
    return (
      <Shell title={t("profile.title")} back="/more">
        {error ? <p className="error" role="alert">{error}</p> : <p className="muted">{t("app.loading")}</p>}
      </Shell>
    );
  }

  return (
    <Shell title={t("profile.title")} back="/more">
      <p className="muted">{t("profile.hint")}</p>
      <form className="stack" onSubmit={save}>
        <section className="panel" aria-labelledby="look-h">
          <h2 id="look-h">{t("profile.look")}</h2>
          <div className="row" style={{ alignItems: "center", gap: 16 }}>
            {profile.logo_url ? (
              <img className="shop-logo" src={apiUrl(profile.logo_url)} alt={t("profile.photo")} />
            ) : (
              <span className="shop-logo" style={{ display: "grid", placeItems: "center", background: "var(--tint)" }}>
                <Icon name="store" />
              </span>
            )}
            <label className="btn small">
              <Icon name="camera" size={18} />
              {profile.logo_url ? t("profile.change_photo") : t("profile.add_photo")}
              <input type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={pickLogo} />
            </label>
          </div>
          <Signboard name={me?.workspace.name ?? ""} compact as="p" />
          <div className="field">
            <label htmlFor="pf-notice">{t("profile.notice")}</label>
            <input id="pf-notice" maxLength={140} value={form.notice} onChange={set("notice")} placeholder={t("profile.notice_eg")} />
            <span className="hint">{t("profile.notice_hint")}</span>
          </div>
          <div className="field">
            <label htmlFor="pf-about">{t("profile.about")}</label>
            <textarea id="pf-about" className="input" maxLength={300} value={form.about} onChange={set("about")} />
          </div>
        </section>

        <section className="panel" aria-labelledby="when-h">
          <h2 id="when-h">{t("profile.when_where")}</h2>
          <div className="field">
            <label htmlFor="pf-hours">{t("profile.hours")}</label>
            <input id="pf-hours" maxLength={80} value={form.hours} onChange={set("hours")} placeholder={t("profile.hours_eg")} />
          </div>
          <div className="field">
            <label htmlFor="pf-address">{t("profile.address")}</label>
            <input id="pf-address" maxLength={200} value={form.address} onChange={set("address")} />
          </div>
          <div className="field">
            <span className="label">{t("profile.delivery")}</span>
            <div className="radios" role="radiogroup" aria-label={t("profile.delivery")}>
              {(["pickup", "delivery", "both"] as const).map((d) => (
                <button type="button" key={d} className="chip" role="radio" aria-checked={form.delivery === d}
                  aria-pressed={form.delivery === d} onClick={() => setForm((f) => ({ ...f, delivery: d }))}>
                  {t(`profile.d_${d}`)}
                </button>
              ))}
            </div>
          </div>
          <div className="field">
            <label htmlFor="pf-dnote">{t("profile.delivery_note")}</label>
            <input id="pf-dnote" maxLength={120} value={form.delivery_note} onChange={set("delivery_note")}
              placeholder={t("profile.delivery_note_eg")} />
          </div>
          <div className="field">
            <label htmlFor="pf-min">{t("profile.min_order")}</label>
            <input id="pf-min" inputMode="numeric" value={form.min_order_inr}
              onChange={(e) => setForm((f) => ({ ...f, min_order_inr: e.target.value.replace(/\D/g, "") }))} />
          </div>
        </section>

        <section className="panel" aria-labelledby="pay-h">
          <h2 id="pay-h">{t("profile.payment")}</h2>
          <div className="field">
            <label htmlFor="pf-upi">{t("profile.upi")}</label>
            <input id="pf-upi" maxLength={100} value={form.upi_id} onChange={set("upi_id")} placeholder="shopname@okaxis" />
            <span className="hint">{t("profile.upi_hint")}</span>
          </div>
        </section>

        <div className="row">
          <button type="submit" className="btn primary" disabled={busy}>{busy ? t("sheet.saving") : t("profile.save")}</button>
          {status ? <p className="ok" role="status">{status}</p> : null}
        </div>
        {error ? <p className="error" role="alert">{error}</p> : null}
      </form>
      <Link className="notice calm" to="/sections">
        <Icon name="sections" />
        <span className="grow">{t("profile.arrange")}</span>
        <Icon name="next" />
      </Link>
    </Shell>
  );
}
