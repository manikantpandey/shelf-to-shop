import { useCallback, useEffect, useRef, useState, type ChangeEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";

import { api, ApiError, type Job } from "../api";
import { Icon } from "../components/Icon";
import { cameraProblem, pickMimeType, type CameraProblem } from "../recorder/mime";
import { forgetRecording, keepRecording, pendingRecording, rememberUpload, type Pending } from "../recordings";
import { resumableUpload } from "../uploader";
import { useSession } from "../session";
import { Shell } from "../Shell";
import { clock as clockText } from "./Videos";

const MAX_SECONDS = 60;
type Phase = "consent" | "starting" | "live" | "recording" | "preview" | "uploading" | "clip" | "problem";

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
  // A long upload: which minute of it to use.
  const [long, setLong] = useState<{ id: string; duration: number; clip: number } | null>(null);
  const [start, setStart] = useState(0);
  const [leftover, setLeftover] = useState<Pending | null>(null);
  const [paused, setPaused] = useState(false);
  const uploadId = useRef<string | undefined>(undefined);
  const clipRef = useRef<HTMLVideoElement>(null);

  const liveRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const timerRef = useRef<number | undefined>(undefined);
  const audioRef = useRef<AudioContext | null>(null);
  const previewUrl = useRef<string>("");
  const startId = useRef(0);

  const stopCamera = useCallback(() => {
    startId.current += 1;
    window.clearInterval(timerRef.current);
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    void audioRef.current?.close();
    audioRef.current = null;
  }, []);

  const startCamera = useCallback(async () => {
    stopCamera();
    const id = startId.current;
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
      // The screen closed or a newer start began while we waited, so release this camera.
      if (id !== startId.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
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
      if (id !== startId.current) return;
      setProblem(cameraProblem(err, window.isSecureContext, hasMedia));
      setPhase("problem");
    }
  }, [stopCamera]);

  useEffect(() => {
    if (phase === "starting") void startCamera();
    // Start once when the screen opens with consent already given.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => () => {
    stopCamera();
    if (previewUrl.current) URL.revokeObjectURL(previewUrl.current);
  }, [stopCamera]);

  // A video that did not finish uploading last time is still on this phone: offer to finish it.
  useEffect(() => {
    void pendingRecording().then((p) => {
      if (p && p.blob.size) setLeftover(p);
    });
  }, []);

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
    uploadId.current = undefined;
    void forgetRecording();
    void startCamera();
  };

  const makeJob = async (uploadId: string, startS?: number) => {
    const job = await api<Job>("/api/v1/jobs", { method: "POST", json: { upload_id: uploadId, start_s: startS ?? null } });
    navigate(`/jobs/${job.id}`);
  };

  const send = async (blob: Blob, resumeId?: string) => {
    setPhase("uploading");
    setError("");
    setPaused(false);
    setProgress(0);
    try {
      // Keep the video on the phone until the server has all of it.
      if (!resumeId) await keepRecording(blob);
      const upload = await resumableUpload(blob, {
        onProgress: setProgress,
        resumeId: resumeId ?? uploadId.current,
        onSession: (id) => {
          uploadId.current = id;
          void rememberUpload(id);
        },
      });
      uploadId.current = undefined;
      await forgetRecording();
      setLeftover(null);
      if (upload.needs_clip) {
        setLong({ id: upload.id, duration: upload.duration_s, clip: upload.max_clip_s });
        setStart(0);
        setPhase("clip");
        return;
      }
      await makeJob(upload.id);
    } catch (err) {
      const offline = !(err instanceof ApiError) || err.status === 0;
      if (!offline) {
        // The server refused the video: start fresh next time, and drop the saved copy.
        uploadId.current = undefined;
        await forgetRecording();
      }
      setPaused(offline);
      setError(offline ? t("record.upload_paused") : err.message);
      // Always come back to the video with the reason shown (never silently to the camera).
      setPhase("preview");
    }
  };

  const resumeLeftover = () => {
    if (!leftover) return;
    stopCamera();
    setVideo(leftover.blob);
    if (previewUrl.current) URL.revokeObjectURL(previewUrl.current);
    previewUrl.current = URL.createObjectURL(leftover.blob);
    uploadId.current = leftover.uploadId;
    void send(leftover.blob, leftover.uploadId);
  };

  const discardLeftover = async () => {
    await forgetRecording();
    setLeftover(null);
  };

  const chooseClip = async () => {
    if (!long) return;
    setError("");
    try {
      await makeJob(long.id, start);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("record.upload_failed"));
    }
  };

  const pick = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) {
      stopCamera();
      setVideo(file);
      uploadId.current = undefined;
      if (previewUrl.current) URL.revokeObjectURL(previewUrl.current);
      previewUrl.current = URL.createObjectURL(file);
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
        <section className="paper-note" aria-labelledby="rc">
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
        <section className="paper-note" role="alert">
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

  if (phase === "clip" && long) {
    const latest = Math.max(0, long.duration - long.clip);
    const end = Math.min(long.duration, start + long.clip);
    const move = (value: number) => {
      setStart(value);
      if (clipRef.current) clipRef.current.currentTime = value;
    };
    return (
      <Shell
        title={t("record.clip_title")}
        footer={
          <>
            <button type="button" className="btn" onClick={retake}>{t("record.other_video")}</button>
            <button type="button" className="btn primary" onClick={() => void chooseClip()}>{t("record.use_minute")}</button>
          </>
        }
      >
        <p>{t("record.clip_body", { length: clockText(long.duration), clip: Math.round(long.clip) })}</p>
        {previewUrl.current ? (
          <video ref={clipRef} src={previewUrl.current} controls playsInline className="preview"
            onLoadedMetadata={(e) => { e.currentTarget.currentTime = start; }} />
        ) : null}
        <div className="field">
          <label htmlFor="clip-start">{t("record.clip_from", { from: clockText(start), to: clockText(end) })}</label>
          <input id="clip-start" type="range" min={0} max={Math.floor(latest)} step={1} value={Math.floor(start)}
            onChange={(e) => move(Number(e.target.value))} style={{ width: "100%" }} />
          <span className="hint">{t("record.clip_hint")}</span>
        </div>
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
              <button type="button" className="btn primary" onClick={() => video && void send(video, uploadId.current)}>
                {paused ? t("record.resume") : t("record.use")}
              </button>
            </>
          )
        }
      >
        {previewUrl.current ? <video src={previewUrl.current} controls playsInline className="preview" /> : null}
        {paused ? <p className="muted">{t("record.saved_on_phone")}</p> : <p>{t("record.preview_hint")}</p>}
        {error ? <p className="error" role="alert">{error}</p> : null}
      </Shell>
    );
  }

  const recording = phase === "recording";
  if (leftover && !recording) {
    return (
      <Shell
        title={t("record.leftover_title")}
        footer={
          <>
            <button type="button" className="btn" onClick={() => void discardLeftover()}>{t("record.discard")}</button>
            <button type="button" className="btn primary" onClick={resumeLeftover}>{t("record.resume")}</button>
          </>
        }
      >
        <p>{t("record.leftover_body", { when: new Date(leftover.savedAt).toLocaleString(), size: Math.max(1, Math.round(leftover.blob.size / 1048576)) })}</p>
      </Shell>
    );
  }
  return (
    <div className="recorder dark">
      <div className="bar">
        <span className="count" aria-live="polite">
          {recording ? t("record.left", { seconds: left }) : t("record.up_to")}
        </span>
        {recording ? null : (
          <Link to="/home" className="icon-btn" aria-label={t("record.close")} style={{ color: "inherit" }}>
            <Icon name="close" />
          </Link>
        )}
      </div>
      <video ref={liveRef} autoPlay playsInline muted aria-label={t("record.title")} />
      <div className="guide">
        <span className="cue">{t("record.guide_move")}</span>
        <span className="cue">{t("record.guide_say")}</span>
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
