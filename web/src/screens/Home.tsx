import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api, apiUrl, type Item, type MyCatalog, type Offer, type Offers, type Stats, type VideoSummary } from "../api";
import { hasSeenVideoDetails, hidePath, showPath } from "../demoPath";
import { Icon } from "../components/Icon";
import { Signboard } from "../components/Signboard";
import { formatINR } from "../format";
import { formatOfferDay, offerTitle } from "../offers";
import { useSession } from "../session";
import { Shell } from "../Shell";
import { VideoRow } from "./Videos";

const PATH = ["fix", "read", "order", "pack"] as const;

/** Four real tasks that walk a demo visitor through the sample shop; each ticks when it is done. */
export function DemoPath({ stats, videos, url, onHide }: {
  stats: Stats;
  videos: VideoSummary[];
  url: string | null;
  onHide: () => void;
}) {
  const { t } = useTranslation();
  const toCheck = videos.find((v) => v.status === "needs_review");
  const read = videos.find((v) => v.status === "published") ?? videos[0];
  const c = stats.orders.counts;
  const orders = c.new + c.packed + c.delivered + c.cancelled;
  const done = {
    fix: !toCheck,
    read: hasSeenVideoDetails(),
    order: orders > 0,
    pack: c.packed + c.delivered > 0,
  };
  const go = {
    fix: toCheck ? (
      // "Check", not "Fix prices": Home knows how many questions there are, not whether they are about prices.
      <Link className="btn small primary" to={`/jobs/${toCheck.id}/review`}>{t("home.review")}</Link>
    ) : null,
    read: read ? <Link className="btn small" to={`/videos/${read.id}`}>{t("path.read_go")}</Link> : null,
    order: url ? <a className="btn small" href={url} target="_blank" rel="noopener">{t("home.open_shop")}</a> : null,
    pack: <Link className="btn small" to="/orders">{t("home.see_orders")}</Link>,
  };
  const all = PATH.every((k) => done[k]);
  return (
    <section className="panel demo-path" aria-labelledby="path-h">
      <div className="panel-head">
        <h2 id="path-h">{t("path.title")}</h2>
        <button type="button" className="btn small quiet" onClick={onHide}>{t("path.hide")}</button>
      </div>
      <p className="muted small">{t("path.lead")}</p>
      <ol className="steps">
        {PATH.map((k, i) => (
          <li key={k} className={done[k] ? "done" : ""}>
            <span className="n">{done[k] ? <Icon name="check" size={16} /> : i + 1}</span>
            <span className="what">{t(`path.${k}`)}</span>
            {done[k] ? <span className="state">{t("path.done")}</span> : go[k]}
          </li>
        ))}
      </ol>
      {all ? (
        <div className="row">
          <p className="ok grow">{t("path.all_done")}</p>
          <Link className="btn record-btn" to="/record"><Icon name="record" />{t("nav.record")}</Link>
        </div>
      ) : null}
    </section>
  );
}

export function Home() {
  const { t, i18n } = useTranslation();
  const { me } = useSession();
  const [stats, setStats] = useState<Stats | null>(null);
  const [videos, setVideos] = useState<VideoSummary[]>([]);
  const [catalog, setCatalog] = useState<MyCatalog | null>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [offer, setOffer] = useState<Offer | null>(null);
  const [path, setPath] = useState(showPath);
  const [copied, setCopied] = useState(false);
  const [copiedFeed, setCopiedFeed] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      api<Stats>("/api/v1/stats"),
      api<{ videos: VideoSummary[] }>("/api/v1/videos"),
      api<MyCatalog>("/api/v1/catalog"),
      api<{ items: Item[] }>("/api/v1/items"),
      // The offer notice is extra: Home still opens if this one call fails.
      api<Offers>("/api/v1/offers").catch(() => null),
    ])
      .then(([s, v, c, i, o]) => {
        setStats(s);
        setVideos(v.videos);
        setCatalog(c);
        setItems(i.items);
        setOffer(o?.active ?? null);
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
  const copyFeed = async (link: string) => {
    try {
      await navigator.clipboard.writeText(link);
      setCopiedFeed(true);
      window.setTimeout(() => setCopiedFeed(false), 2000);
    } catch {
      setCopiedFeed(false);
    }
  };
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
  const onShop = items.filter((it) => it.live && it.image_url && it.price_display).slice(0, 6);
  const weekday = new Intl.DateTimeFormat(i18n.language === "hi" ? "hi-IN" : "en-IN", { weekday: "short" });
  const lang = i18n.language === "hi" ? "hi" : "en";

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
      {path ? <DemoPath stats={stats} videos={videos} url={url} onHide={() => { hidePath(); setPath(false); }} /> : null}
      {toCheck && !path ? (
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
      {offer ? (
        <Link className="notice calm" to="/offers">
          <Icon name="tag" />
          <span className="grow">
            {t("home.offer_on", { title: offerTitle(offer, lang), date: formatOfferDay(offer.ends_on, lang) })}
          </span>
          <span className="btn small">{t("home.tell_customers")}</span>
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
            {onShop.length ? (
              // The shop window: what a customer sees first, and a big target to open it.
              <a className="window" href={url} target="_blank" rel="noopener" aria-label={t("home.open_shop")}>
                {onShop.map((it) => (
                  <span className="w-tile" key={it.id}>
                    <img src={apiUrl(it.image_url ?? "")} alt="" loading="lazy" />
                    <span className="pricetag">{it.price_display}</span>
                  </span>
                ))}
              </a>
            ) : null}
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
            {catalog.published && catalog.feed_link ? (
              <div className="feed-link">
                <p className="small"><strong>{t("home.feed_link_title")}</strong></p>
                <div className="row">
                  <code className="feed-url">{catalog.feed_link}</code>
                  <button type="button" className="btn small" onClick={() => void copyFeed(catalog.feed_link ?? "")}>
                    <Icon name={copiedFeed ? "check" : "copy"} size={18} />
                    {copiedFeed ? t("home.copied") : t("home.copy")}
                  </button>
                </div>
                <p className="muted small">{t("home.feed_link_hint")}</p>
              </div>
            ) : null}
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
