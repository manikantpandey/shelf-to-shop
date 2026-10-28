import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import { api, type Job } from "../api";
import { Shell } from "../Shell";

export const STAGES = ["ingest", "detect", "transcribe", "segment", "enrich", "match", "verify", "backgrounds"];

export function Processing() {
  const { t } = useTranslation();
  const { jobId = "" } = useParams();
  const navigate = useNavigate();
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let stopped = false;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const data = await api<Job>(`/api/v1/jobs/${jobId}`);
        if (stopped) return;
        setJob(data);
        setError("");
        if (data.status === "needs_review" || data.status === "published") {
          navigate(`/jobs/${jobId}/review`, { replace: true });
          return;
        }
        if (data.status === "failed") return;
      } catch {
        setError(t("app.offline"));
      }
      timer = window.setTimeout(poll, 2000);
    };
    void poll();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [jobId, navigate, t]);

  const retry = async () => {
    await api(`/api/v1/jobs/${jobId}/retry`, { method: "POST" });
    navigate(0);
  };

  const state = (status: string | undefined) =>
    status === "done" || status === "cached" ? "done" : status === "running" ? "running" : status === "failed" ? "failed" : "";
  const label = (status: string | undefined) => {
    const s = state(status);
    return s ? t(`processing.${s}`) : "";
  };

  const failed = job?.status === "failed";
  return (
    <Shell
      title={t("processing.title")}
      back="/videos"
      footer={failed ? <button type="button" className="btn primary" onClick={retry}>{t("processing.try_again")}</button> : undefined}
    >
      <p className="muted">{failed ? null : t("processing.hint")}</p>
      <ol className="steps" aria-label={t("processing.title")}>
        {STAGES.map((stage, i) => (
          <li key={stage} className={state(job?.stages[stage])}>
            <span className="n">{i + 1}</span>
            <span className="what">{t(`processing.stage.${stage}`)}</span>
            <span className="state">{label(job?.stages[stage])}</span>
          </li>
        ))}
      </ol>
      {failed ? (
        <p className="error" role="alert">
          {job?.error_code ? t(`job_error.${job.error_code}`, { defaultValue: job.error_message ?? "" }) : job?.error_message}
        </p>
      ) : null}
      {error ? <p className="error" role="alert">{error}</p> : null}
    </Shell>
  );
}
