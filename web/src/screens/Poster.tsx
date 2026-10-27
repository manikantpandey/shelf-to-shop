import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api, type MyCatalog, type Profile } from "../api";
import { Icon } from "../components/Icon";
import { Signboard } from "../components/Signboard";
import { useSession } from "../session";
import { qrDataUrl } from "./Share";

/** An A4 poster for the counter: the shop's board, a big QR code, how to order. Print it. */
export function Poster() {
  const { t } = useTranslation();
  const { me } = useSession();
  const [url, setUrl] = useState("");
  const [qr, setQr] = useState("");
  const [profile, setProfile] = useState<Profile | null>(null);

  useEffect(() => {
    api<MyCatalog>("/api/v1/catalog").then(async (c) => {
      if (!c.published) return;
      setUrl(c.url);
      setQr(await qrDataUrl(c.url, 900));
    }).catch(() => undefined);
    api<{ profile: Profile }>("/api/v1/profile").then((d) => setProfile(d.profile)).catch(() => undefined);
  }, []);

  return (
    <div className="poster">
      <div className="no-print">
        <button type="button" className="btn primary" onClick={() => window.print()} disabled={!qr}>
          <Icon name="print" />{t("poster.print")}
        </button>
        <Link className="btn" to="/share">{t("app.back")}</Link>
      </div>
      <Signboard name={me?.workspace.name ?? ""} as="h1" />
      <h2>{t("poster.headline")}</h2>
      {qr ? <div className="qr"><img src={qr} alt={t("share.qr_alt")} /></div> : <p className="muted">{t("share.not_live")}</p>}
      <div className="lines">
        <span>{t("poster.step")}</span>
        {profile?.hours ? <span>{t("poster.hours", { hours: profile.hours })}</span> : null}
        {profile && profile.delivery !== "pickup" ? <span>{profile.delivery_note || t("profile.d_" + profile.delivery)}</span> : null}
      </div>
      {url ? <p className="url">{url.replace(/^https?:\/\//, "")}</p> : null}
    </div>
  );
}
