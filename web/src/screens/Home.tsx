import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api, apiUrl, type MyCatalog, type Stats, type VideoSummary } from "../api";
import { Icon } from "../components/Icon";
import { Signboard } from "../components/Signboard";
import { formatINR } from "../format";
import { useSession } from "../session";
import { Shell } from "../Shell";
import { VideoRow } from "./Videos";

export function Home() {
  const { t, i18n } = useTranslation();
  const { me } = useSession();
  const [stats, setStats] = useState<Stats | null>(null);
  const [videos, setVideos] = useState<VideoSummary[]>([]);
  const [catalog, setCatalog] = useState<MyCatalog | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      api<Stats>("/api/v1/stats"),
      api<{ videos: VideoSummary[] }>("/api/v1/videos"),
      api<MyCatalog>("/api/v1/catalog"),
    ])
      .then(([s, v, c]) => {
        setStats(s);
        setVideos(v.videos);
        setCatalog(c);
      })
      .catch(() => setError(t("app.offline")));
  }, [t]);

  const name = me?.workspace.name ?? "";
  const board = <Signboard name={name} as="p" />;
  if (!stats || !catalog) {
    return (
      <Shell title={t("home.title")} board={board}>
        {error ? <p className="error" role="alert">{error}</p> : <p className="muted">{t("app.loading")}</p>}
      </Shell>
    );
  }

  const url = catalog.published ? catalog.url : null;
  const share = url ? `https://wa.me/?text=${encodeURIComponent(t("home.share_text", { url }))}` : "";
  const copy = async () => {
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };
  const toCheck = videos.find((v) => v.status === "needs_review");
  const working = videos.find((v) => v.status === "queued" || v.status === "running");
  const max = Math.max(1, ...stats.by_day.flatMap((d) => [d.views, d.orders]));
  const weekday = new Intl.DateTimeFormat(i18n.language === "hi" ? "hi-IN" : "en-IN", { weekday: "short" });

  return (
    <Shell title={t("home.title")} board={board}>
      {/* What needs the shopkeeper comes first: new orders, then questions, then work in progress. */}
      {stats.orders.counts.new ? (
        <Link className="notice" to="/orders">
          <Icon name="orders" />
          <span className="grow">{t("home.new_orders", { count: stats.orders.counts.new })}</span>
          <span className="btn small primary">{t("home.see_orders")}</span>
        </Link>
      ) : null}
      {toCheck ? (
        <Link className="notice" to={`/jobs/${toCheck.id}/review`}>
          <Icon name="alert" />
          <span className="grow">
            {toCheck.open_flags
              ? t("home.to_check", { count: toCheck.open_flags })
              : t("home.ready_to_publish", { count: toCheck.items })}
          </span>
          <span className="btn small primary">{toCheck.open_flags ? t("home.check") : t("home.review")}</span>
        </Link>
      ) : null}
      {working ? (
        <Link className="notice calm" to={`/jobs/${working.id}`}>
          <Icon name="videos" />
          <span className="grow">{t("home.processing")}</span>
          <Icon name="next" />
        </Link>
      ) : null}

      <section className="panel" aria-labelledby="shop-h">
        <h2 id="shop-h">{t("home.your_shop")}</h2>
        {url ? (
          <>
            <p>
              {t("home.live", { count: stats.items_live })}{" "}
              <a className="url" href={url} target="_blank" rel="noopener">{url.replace(/^https?:\/\//, "")}</a>
            </p>
            <div className="row">
              <a className="btn primary" href={share} target="_blank" rel="noopener">
                <Icon name="chat" />
                {t("home.share")}
              </a>
              <button type="button" className="btn" onClick={copy}>
                <Icon name={copied ? "check" : "copy"} />
                {copied ? t("home.copied") : t("home.copy")}
              </button>
              <a className="btn quiet" href={url} target="_blank" rel="noopener">
                <Icon name="open" />
                {t("home.open_shop")}
              </a>
            </div>
            <div className="row">
              {catalog.published && catalog.feed_url ? (
                <a className="btn small quiet" href={apiUrl(catalog.feed_url)}><Icon name="download" size={18} />{t("home.feed")}</a>
              ) : null}
              {catalog.published ? (
                <a className="btn small quiet" href={apiUrl(catalog.photos_url)}><Icon name="download" size={18} />{t("home.photos")}</a>
              ) : null}
              <Link className="btn small quiet" to="/share"><Icon name="qr" size={18} />{t("nav.share")}</Link>
            </div>
            {catalog.published && !catalog.feed_url ? <p className="muted small">{t("home.feed_unavailable")}</p> : null}
          </>
        ) : (
          <p className="muted">{t("home.not_live")}</p>
        )}
      </section>

      {videos.length === 0 ? (
        <section className="panel">
          <h2>{t("home.first_title")}</h2>
          <ol className="steps-mini">
            <li>{t("home.first_1")}</li>
            <li>{t("home.first_2")}</li>
            <li>{t("home.first_3")}</li>
          </ol>
          <Link className="btn primary record-btn" to="/record">
            <Icon name="record" />
            {t("nav.record")}
          </Link>
        </section>
      ) : (
        <div className="home-grid">
          <section className="panel span" aria-labelledby="week">
            <div className="panel-head">
              <h2 id="week">{t("home.week")}</h2>
              {stats.views_7d > 0 ? (
                <div className="legend" aria-hidden="true">
                  <span>{t("home.visits")}</span>
                  <span className="orders">{t("home.orders")}</span>
                </div>
              ) : null}
            </div>
            <div className="ledger-strip">
              <div>
                <span className="num">{stats.views_7d}</span>
                <span className="label">{t("home.visits")}</span>
              </div>
              <div>
                <span className="num">{formatINR(stats.orders.today_total_inr)}</span>
                <span className="label">{t("home.sales_today", { count: stats.orders.today_orders })}</span>
              </div>
              <div>
                <span className="num">{stats.items_live}</span>
                <span className="label">{t("home.items_live")}</span>
              </div>
            </div>
            {stats.views_7d > 0 ? (
              <div className="bars" role="img" aria-label={t("home.chart_label", { views: stats.views_7d, orders: stats.orders_7d })}>
                {stats.by_day.map((d) => (
                  <div className="bar" key={d.day}>
                    <div className="pair">
                      <div className="col" style={{ height: `${Math.round((d.views / max) * 100)}%` }} />
                      <div className="col orders" style={{ height: `${Math.round((d.orders / max) * 100)}%` }} />
                    </div>
                    <span className="day">{weekday.format(new Date(`${d.day}T12:00:00`))}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="muted small">{t("home.no_visits")}</p>
            )}
          </section>

          <section className="panel" aria-labelledby="recent">
            <div className="panel-head">
              <h2 id="recent">{t("home.recent")}</h2>
              <Link to="/videos">{t("home.all_videos")}<Icon name="next" size={18} /></Link>
            </div>
            <div className="list-plain">
              {videos.slice(0, 3).map((v) => <VideoRow key={v.id} video={v} />)}
            </div>
          </section>

          <section className="panel" aria-labelledby="top">
            <div className="panel-head">
              <h2 id="top">{t("home.top")}</h2>
              <Link to="/items">{t("home.all_items")}<Icon name="next" size={18} /></Link>
            </div>
            {stats.top_items.length ? (
              <ol className="ranked list-plain">
                {stats.top_items.map((item) => (
                  <li key={item.id}>
                    <span>{item.title}</span>
                    <span className="num">{t("home.orders_n", { count: item.orders })}</span>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="muted">{t("home.no_orders")}</p>
            )}
          </section>
        </div>
      )}
    </Shell>
  );
}
