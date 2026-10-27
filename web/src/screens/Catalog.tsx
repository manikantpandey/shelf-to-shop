import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api, apiUrl, type MyCatalog } from "../api";
import { Shell } from "../Shell";

export function Catalog() {
  const { t } = useTranslation();
  const [data, setData] = useState<MyCatalog | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api<MyCatalog>("/api/v1/catalog").then(setData).catch(() => setError(t("app.offline")));
  }, [t]);

  if (!data) return <Shell title={t("catalog.title")}>{error ? <p className="error">{error}</p> : <p>{t("app.loading")}</p>}</Shell>;
  if (!data.published) {
    return (
      <Shell title={t("catalog.title")} footer={<Link className="btn primary" to="/record">{t("catalog.new_video")}</Link>}>
        <p>{t("catalog.none")}</p>
      </Shell>
    );
  }

  const share = `https://wa.me/?text=${encodeURIComponent(t("catalog.share_text", { url: data.url }))}`;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(data.url);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  return (
    <Shell title={t("catalog.title")} footer={<a className="btn primary" href={share} target="_blank" rel="noopener">{t("catalog.share")}</a>}>
      <section className="paper">
        <h2>{t("catalog.live")}</h2>
        <p className="muted">{t("catalog.items", { count: data.items })}</p>
        <p><a href={data.url}>{data.url.replace(/^https?:\/\//, "")}</a></p>
      </section>
      <button type="button" className="btn" onClick={copy}>{copied ? t("catalog.copied") : t("catalog.copy")}</button>
      <a className="btn" href={data.url} target="_blank" rel="noopener">{t("catalog.open")}</a>
      {data.feed_url ? (
        <>
          <a className="btn" href={apiUrl(data.feed_url)}>{t("catalog.feed")}</a>
          <p className="muted">{t("catalog.feed_hint")}</p>
          {data.feed_left_out ? <p className="error">{t("catalog.feed_left_out", { count: data.feed_left_out })}</p> : null}
        </>
      ) : (
        <p className="muted">{t("catalog.feed_unavailable")}</p>
      )}
      <a className="btn" href={apiUrl(data.photos_url)}>{t("catalog.photos")}</a>
      <Link className="btn quiet" to="/record">{t("catalog.new_video")}</Link>
    </Shell>
  );
}
