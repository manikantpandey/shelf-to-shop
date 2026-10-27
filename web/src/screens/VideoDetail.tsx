import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";

import { api, apiUrl, type JobDetails } from "../api";
import { formatINR } from "../format";
import { Shell } from "../Shell";
import { STAGES } from "./Processing";
import { clock, when } from "./Videos";

const MODEL_NAMES: Record<string, string> = {
  "muse-spark-1.3": "Muse Spark",
  "sam-3.1": "SAM 3.1",
  "muse-voice-transcribe-1.0": "Muse Voice Transcribe",
  "muse-image-1.0": "Muse Image",
};

function usd(value: string): string {
  const n = Number(value);
  return n < 0.01 && n > 0 ? "<$0.01" : `$${n.toFixed(2)}`;
}

/** How one video became items: what was heard, each step, and the proof behind each price. */
export function VideoDetail() {
  const { t, i18n } = useTranslation();
  const { jobId = "" } = useParams();
  const [data, setData] = useState<JobDetails | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<JobDetails>(`/api/v1/jobs/${jobId}/details`).then(setData).catch(() => setError(t("app.offline")));
  }, [jobId, t]);

  if (!data) {
    return (
      <Shell title={t("detail.title")} back="/videos">
        {error ? <p className="error" role="alert">{error}</p> : <p className="muted">{t("app.loading")}</p>}
      </Shell>
    );
  }

  const hindi = i18n.language === "hi";
  const kept = data.items.filter((i) => !i.removed);
  const steps = data.stages.filter((s) => s.stage !== "recut" || s.calls);
  const stepLabel = (stage: string) =>
    STAGES.includes(stage) ? t(`processing.stage.${stage}`) : t("detail.recut");

  return (
    <Shell
      title={t("detail.heading", { when: when(data.created_at, i18n.language) })}
      back="/videos"
      actions={data.status === "needs_review" ? (
        <Link className="btn primary" to={`/jobs/${data.id}/review`}>{t("detail.review")}</Link>
      ) : undefined}
    >
      <div className="facts">
        <div><span className="num">{clock(data.duration_s)}</span><span className="label">{t("detail.length")}</span></div>
        <div><span className="num">{kept.length}</span><span className="label">{t("detail.items")}</span></div>
        <div><span className="num">{data.total_seconds !== null ? `${Math.round(data.total_seconds)} s` : "–"}</span><span className="label">{t("detail.time")}</span></div>
        <div><span className="num">{usd(data.cost_usd)}</span><span className="label">{t("detail.cost")}</span></div>
      </div>

      <div className="detail-grid">
        <section className="panel" aria-labelledby="steps-h">
          <h2 id="steps-h">{t("detail.steps")}</h2>
          <ol className="steps">
            {steps.map((s, i) => (
              <li key={s.stage} className={s.errors && !s.calls ? "failed" : "done"}>
                <span className="n">{i + 1}</span>
                <span className="what">
                  <span>{stepLabel(s.stage)}</span>
                  <small>
                    {s.models.length
                      ? t("detail.by", { models: s.models.map((m) => MODEL_NAMES[m] ?? m).join(", "), count: s.calls })
                      : t("detail.on_server")}
                  </small>
                </span>
                <span className="state">
                  {s.seconds !== null ? `${s.seconds} s` : ""}
                  {Number(s.cost_usd) > 0 ? <><br />{usd(s.cost_usd)}</> : null}
                </span>
              </li>
            ))}
          </ol>
        </section>

        <div className="stack">
          <section className="panel" aria-labelledby="heard-h">
            <h2 id="heard-h">{t("detail.heard")}</h2>
            {data.transcript.length ? (
              <ul className="heard list-plain">
                {data.transcript.map((c, i) => (
                  <li key={i}>
                    <span className="t">{clock(c.start_s)}</span>
                    <span lang="hi">{c.text}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">{t("detail.nothing_heard")}</p>
            )}
          </section>

          <section className="panel" aria-labelledby="proof-h">
            <h2 id="proof-h">{t("detail.proof")}</h2>
            <div className="list-plain">
              {kept.map((item) => {
                const spoken = item.evidence.find((e) => e.kind === "speech" || e.snippet);
                return (
                  <div className="evidence" key={item.idx}>
                    {item.frame_url || item.image_url ? (
                      <img src={apiUrl(item.frame_url ?? item.image_url ?? "")} alt="" loading="lazy" />
                    ) : <span />}
                    <div className="proof">
                      <strong>{hindi ? item.title_hi : item.title_en}</strong>
                      <span className="price">{item.price_inr !== null ? formatINR(item.price_inr) : t("detail.no_price")}</span>
                      <span className="muted small">
                        {item.first_seen_s !== null
                          ? t("detail.seen", { from: clock(item.first_seen_s), to: clock(item.last_seen_s) })
                          : null}
                        {" "}
                        {t(`detail.source.${item.source}`, { defaultValue: "" })}
                      </span>
                      {spoken?.snippet ? (
                        <span className="small">
                          {spoken.t_s !== null ? `${clock(spoken.t_s)} ` : ""}<q lang="hi">{spoken.snippet}</q>
                        </span>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        </div>
      </div>
    </Shell>
  );
}
