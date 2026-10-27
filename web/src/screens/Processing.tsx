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

  const label = (status: string | undefined) => {
    if (status === "done" || status === "cached") return <span className="done">{t("processing.done")}</span>;
    if (status === "running") return <span className="running">{t("processing.running")}</span>;
    if (status === "failed") return <span className="failed">{t("processing.failed")}</span>;
    return <span />;
  };

  const failed = job?.status === "failed";
  return (
    <Shell
      title={t("processing.title")}
      footer={failed ? <button type="button" className="btn primary" onClick={retry}>{t("processing.try_again")}</button> : undefined}
    >
      <ol className="steps" aria-label={t("processing.title")}>
        {STAGES.map((stage, i) => (
          <li key={stage}>
            <span className="n">{i + 1}</span>
            <span>{t(`processing.stage.${stage}`)}</span>
            {label(job?.stages[stage])}
          </li>
        ))}
      </ol>
      {failed ? <p className="error" role="alert">{job?.error_message}</p> : <p className="muted">{t("processing.hint")}</p>}
      {error ? <p className="error" role="alert">{error}</p> : null}
    </Shell>
  );
}
