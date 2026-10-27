import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api, apiUrl, type VideoSummary } from "../api";
import { Icon } from "../components/Icon";
import { Shell } from "../Shell";

export function when(iso: string, lang: string): string {
  const date = new Date(iso);
  const locale = lang === "hi" ? "hi-IN" : "en-IN";
  const today = new Date();
  const sameDay = date.toDateString() === today.toDateString();
  const time = new Intl.DateTimeFormat(locale, { hour: "numeric", minute: "2-digit" }).format(date);
  if (sameDay) return time;
  return `${new Intl.DateTimeFormat(locale, { day: "numeric", month: "short" }).format(date)}, ${time}`;
}

export function clock(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "";
  const s = Math.round(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function target(v: VideoSummary): string {
  if (v.status === "needs_review") return `/jobs/${v.id}/review`;
  if (v.status === "queued" || v.status === "running") return `/jobs/${v.id}`;
  return `/videos/${v.id}`;
}

export function VideoStatus({ video }: { video: VideoSummary }) {
  const { t } = useTranslation();
  if (video.status === "published") return <span className="pill">{t("videos.on_shop")}</span>;
  if (video.status === "needs_review") {
    return (
      <span className="pill warn">
        {video.open_flags ? t("videos.questions", { count: video.open_flags }) : t("videos.to_publish")}
      </span>
    );
  }
  if (video.status === "failed") return <span className="pill warn">{t("videos.failed")}</span>;
  return <span className="pill plain">{t("videos.working")}</span>;
}

export function VideoRow({ video }: { video: VideoSummary }) {
  const { t, i18n } = useTranslation();
  return (
    <Link className="vrow" to={target(video)}>
      {video.thumb_url ? (
        <img className="thumb" src={apiUrl(video.thumb_url)} alt="" loading="lazy" />
      ) : (
        <span className="thumb blank"><Icon name="videos" /></span>
      )}
      <span className="what">
        <strong>{when(video.created_at, i18n.language)}</strong>
        <span>{video.titles.length ? video.titles.join(", ") : video.error_message ?? t("videos.no_items")}</span>
      </span>
      <span className="side">
        <VideoStatus video={video} />
        <span className="muted small">
          {t("videos.line", { items: t("videos.items", { count: video.items }), length: clock(video.duration_s) })}
        </span>
      </span>
    </Link>
  );
}

export function Videos() {
  const { t } = useTranslation();
  const [videos, setVideos] = useState<VideoSummary[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<{ videos: VideoSummary[] }>("/api/v1/videos")
      .then((d) => setVideos(d.videos))
      .catch(() => setError(t("app.offline")));
  }, [t]);

  return (
    <Shell
      title={t("videos.title")}
      actions={
        <Link className="btn record-btn" to="/record">
          <Icon name="record" />
          {t("videos.new")}
        </Link>
      }
    >
      {error ? <p className="error" role="alert">{error}</p> : null}
      {videos === null && !error ? <p className="muted">{t("app.loading")}</p> : null}
      {videos && videos.length === 0 ? <p className="muted">{t("videos.empty")}</p> : null}
      {videos && videos.length ? (
        <>
          <p className="muted">{t("videos.hint")}</p>
          <div className="rows">
            {videos.map((v) => <VideoRow key={v.id} video={v} />)}
          </div>
        </>
      ) : null}
    </Shell>
  );
}
