import { useCallback, useEffect, useRef, useState, type ChangeEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { api, ApiError, uploadVideo, type Job } from "../api";
import { cameraProblem, pickMimeType, type CameraProblem } from "../recorder/mime";
import { useSession } from "../session";
import { Shell } from "../Shell";

const MAX_SECONDS = 60;
type Phase = "consent" | "starting" | "live" | "recording" | "preview" | "uploading" | "problem";

export function Record() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { me, refresh } = useSession();
  const [phase, setPhase] = useState<Phase>(me?.workspace.consent_recording ? "starting" : "consent");
  const [problem, setProblem] = useState<CameraProblem | null>(null);
  const [left, setLeft] = useState(MAX_SECONDS);
  const [level, setLevel] = useState(0);
  const [torch, setTorch] = useState<boolean | null>(null);
  const [video, setVideo] = useState<Blob | null>(null);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");

  const liveRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const timerRef = useRef<number | undefined>(undefined);
  const audioRef = useRef<AudioContext | null>(null);
  const previewUrl = useRef<string>("");

  const stopCamera = useCallback(() => {
    window.clearInterval(timerRef.current);
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    void audioRef.current?.close();
    audioRef.current = null;
  }, []);

  const startCamera = useCallback(async () => {
    setPhase("starting");
    const hasMedia = Boolean(navigator.mediaDevices?.getUserMedia);
    if (!window.isSecureContext || !hasMedia || typeof MediaRecorder === "undefined") {
      setProblem(cameraProblem(null, window.isSecureContext, hasMedia));
      setPhase("problem");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: "environment" },
          width: { ideal: 1280, max: 1280 },
          height: { ideal: 720, max: 720 },
          frameRate: { ideal: 30, max: 30 },
        },
        audio: { echoCancellation: true, noiseSuppression: true },
      });
      streamRef.current = stream;
      if (liveRef.current) liveRef.current.srcObject = stream;
      const [track] = stream.getVideoTracks();
      const caps = (track.getCapabilities?.() ?? {}) as { torch?: boolean };
      setTorch(caps.torch ? false : null);
      const ctx = new AudioContext();
      audioRef.current = ctx;
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      ctx.createMediaStreamSource(stream).connect(analyser);
      const buf = new Float32Array(analyser.fftSize);
      const tick = () => {
        if (!audioRef.current) return;
        analyser.getFloatTimeDomainData(buf);
        let peak = 0;
        for (const v of buf) peak = Math.max(peak, Math.abs(v));
        setLevel(Math.min(1, peak * 2));
        requestAnimationFrame(tick);
      };
      tick();
      setPhase("live");
    } catch (err) {
      setProblem(cameraProblem(err, window.isSecureContext, hasMedia));
      setPhase("problem");
    }
  }, []);

  useEffect(() => {
    if (phase === "starting") void startCamera();
    // Start once when the screen opens with consent already given.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => () => {
    stopCamera();
    if (previewUrl.current) URL.revokeObjectURL(previewUrl.current);
  }, [stopCamera]);

  const agree = async () => {
    try {
      await api("/api/v1/consents/recording", { method: "POST" });
      await refresh();
      await startCamera();
    } catch {
      setError(t("app.generic_error"));
    }
  };

  const toggleTorch = async () => {
    const track = streamRef.current?.getVideoTracks()[0];
    if (!track || torch === null) return;
    try {
      await track.applyConstraints({ advanced: [{ torch: !torch } as MediaTrackConstraintSet] });
      setTorch(!torch);
    } catch {
      setTorch(null);
    }
  };

  const finish = (chunks: Blob[], type: string) => {
    const blob = new Blob(chunks, { type });
    setVideo(blob);
    if (previewUrl.current) URL.revokeObjectURL(previewUrl.current);
    previewUrl.current = URL.createObjectURL(blob);
    stopCamera();
    setPhase("preview");
  };

  const record = () => {
    const stream = streamRef.current;
    if (!stream) return;
    const mimeType = pickMimeType((type) => MediaRecorder.isTypeSupported(type));
    const recorder = new MediaRecorder(stream, {
      mimeType,
      videoBitsPerSecond: 2_500_000,
      audioBitsPerSecond: 96_000,
    });
    const chunks: Blob[] = [];
    recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    recorder.onstop = () => finish(chunks, recorder.mimeType || mimeType || "video/webm");
    recorderRef.current = recorder;
    const started = performance.now();
    recorder.start(1000);
    setPhase("recording");
    setLeft(MAX_SECONDS);
    timerRef.current = window.setInterval(() => {
      const remaining = Math.max(0, MAX_SECONDS - Math.floor((performance.now() - started) / 1000));
      setLeft(remaining);
      if (remaining <= 0) stop();
    }, 250);
  };

  const stop = () => {
    window.clearInterval(timerRef.current);
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
  };

  const retake = () => {
    setVideo(null);
    void startCamera();
  };

  const send = async (blob: Blob) => {
    setPhase("uploading");
    setError("");
    setProgress(0);
    try {
      const upload = await uploadVideo(blob, setProgress);
      const job = await api<Job>("/api/v1/jobs", { method: "POST", json: { upload_id: upload.id } });
      navigate(`/jobs/${job.id}`);
    } catch (err) {
      const message = err instanceof ApiError && err.status === 422 ? err.message : t("record.upload_failed");
      setError(message);
      setPhase(video ? "preview" : "problem");
    }
  };

  const pick = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      stopCamera();
      setVideo(file);
      void send(file);
    }
  };

  const gallery = (
    <label className="btn">
      {t("record.gallery")}
      <input type="file" accept="video/*" hidden onChange={pick} />
    </label>
  );

  if (phase === "consent") {
    return (
      <Shell title={t("record.title")} footer={<button type="button" className="btn primary" onClick={agree}>{t("record.consent_agree")}</button>}>
        <section className="paper" aria-labelledby="rc">
          <h2 id="rc">{t("record.consent_title")}</h2>
          <ul>
            <li>{t("record.consent_1")}</li>
            <li>{t("record.consent_2")}</li>
            <li>{t("record.consent_3")}</li>
          </ul>
        </section>
        {error ? <p className="error" role="alert">{error}</p> : null}
      </Shell>
    );
  }

  if (phase === "problem" && problem) {
    return (
      <Shell title={t("record.title")} footer={gallery}>
        <section className="paper" role="alert">
          <h2>{t(`record.${problem}_title`)}</h2>
          <p>{t(`record.${problem}_body`)}</p>
        </section>
        {problem === "denied" ? (
          <button type="button" className="btn" onClick={() => void startCamera()}>{t("record.try_again")}</button>
        ) : null}
        {error ? <p className="error" role="alert">{error}</p> : null}
      </Shell>
    );
  }

  if (phase === "preview" || phase === "uploading") {
    return (
      <Shell
        title={t("record.preview_title")}
        footer={
          phase === "uploading" ? (
            <div className="field" style={{ flex: 1 }}>
              <span aria-live="polite">{t("record.uploading", { percent: Math.round(progress * 100) })}</span>
              <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={100}
                aria-valuenow={Math.round(progress * 100)}>
                <span style={{ width: `${Math.round(progress * 100)}%` }} />
              </div>
            </div>
          ) : (
            <>
              <button type="button" className="btn" onClick={retake}>{t("record.retake")}</button>
              <button type="button" className="btn primary" onClick={() => video && void send(video)}>{t("record.use")}</button>
            </>
          )
        }
      >
        {previewUrl.current ? <video src={previewUrl.current} controls playsInline className="preview" /> : null}
        <p>{t("record.preview_hint")}</p>
        {error ? <p className="error" role="alert">{error}</p> : null}
      </Shell>
    );
  }

  const recording = phase === "recording";
  return (
    <div className="recorder dark">
      <div className="bar">
        <span className="count" aria-live="polite">
          {recording ? t("record.left", { seconds: left }) : t("record.up_to")}
        </span>
      </div>
      <video ref={liveRef} autoPlay playsInline muted aria-label={t("record.title")} />
      <div className="guide">
        <span className="chip">{t("record.guide_move")}</span>
        <span className="chip">{t("record.guide_say")}</span>
      </div>
      <div className="mic">
        <meter min={0} max={1} value={level} aria-label="Microphone level" />
        <span>{level > 0.08 ? t("record.mic_good") : t("record.mic_quiet")}</span>
      </div>
      <div className="controls">
        {torch !== null ? (
          <button type="button" className="btn small" aria-pressed={torch} onClick={toggleTorch}>{t("record.torch")}</button>
        ) : <span />}
        <button type="button" className={`shutter${recording ? " on" : ""}`} onClick={recording ? stop : record}
          aria-label={recording ? t("record.stop") : t("record.record")} disabled={phase === "starting"}>
          <span />
        </button>
        {recording ? <span /> : gallery}
      </div>
    </div>
  );
}
