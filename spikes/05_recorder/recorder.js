// Spike 5: measure what getUserMedia + MediaRecorder give us on a real phone.
const MAX_SECONDS = 60;
const VIDEO_BPS = 2_500_000;
const AUDIO_BPS = 96_000;
const CANDIDATE_TYPES = [
  'video/mp4;codecs=avc1.42E01E,mp4a.40.2',
  'video/mp4;codecs=avc1,opus',
  'video/mp4',
  'video/webm;codecs=vp8,opus',
  'video/webm;codecs=vp9,opus',
  'video/webm;codecs=h264,opus',
  'video/webm',
];

const $ = (id) => document.getElementById(id);
const report = { userAgent: navigator.userAgent, startedAt: new Date().toISOString() };
let stream = null;
let recorder = null;
let chunks = [];
let timer = null;
let torchOn = false;

function show(id, data) {
  $(id).textContent = JSON.stringify(data, null, 2);
}

function describeEnvironment() {
  const hasRecorder = typeof MediaRecorder !== 'undefined';
  report.environment = {
    isSecureContext: window.isSecureContext,
    origin: location.origin,
    hasMediaDevices: Boolean(navigator.mediaDevices?.getUserMedia),
    hasMediaRecorder: hasRecorder,
    supportedTypes: hasRecorder
      ? CANDIDATE_TYPES.filter((t) => MediaRecorder.isTypeSupported(t))
      : [],
  };
  show('env', report.environment);
  for (const type of report.environment.supportedTypes) {
    const opt = document.createElement('option');
    opt.value = type;
    opt.textContent = type;
    $('mime').append(opt);
  }
}

async function startCamera() {
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: {
        facingMode: { ideal: 'environment' },
        width: { ideal: 1280, max: 1280 },
        height: { ideal: 720, max: 720 },
        frameRate: { ideal: 30, max: 30 },
      },
      audio: { echoCancellation: true, noiseSuppression: true },
    });
  } catch (err) {
    report.cameraError = { name: err.name, message: err.message };
    show('result', report);
    $('copy').disabled = false;
    return;
  }
  $('live').srcObject = stream;
  const [videoTrack] = stream.getVideoTracks();
  const caps = videoTrack.getCapabilities ? videoTrack.getCapabilities() : {};
  report.camera = {
    label: videoTrack.label,
    settings: videoTrack.getSettings(),
    torchSupported: Boolean(caps.torch),
  };
  show('env', { ...report.environment, camera: report.camera });
  $('torch').disabled = !caps.torch;
  $('record').disabled = false;
  watchMic();
}

function watchMic() {
  const ctx = new AudioContext();
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 512;
  ctx.createMediaStreamSource(stream).connect(analyser);
  const buf = new Float32Array(analyser.fftSize);
  const tick = () => {
    analyser.getFloatTimeDomainData(buf);
    let peak = 0;
    for (const v of buf) peak = Math.max(peak, Math.abs(v));
    $('mic').value = peak;
    requestAnimationFrame(tick);
  };
  tick();
}

async function toggleTorch() {
  const [videoTrack] = stream.getVideoTracks();
  torchOn = !torchOn;
  try {
    await videoTrack.applyConstraints({ advanced: [{ torch: torchOn }] });
  } catch (err) {
    report.torchError = { name: err.name, message: err.message };
  }
}

function startRecording() {
  const mimeType = $('mime').value || undefined;
  chunks = [];
  recorder = new MediaRecorder(stream, {
    mimeType,
    videoBitsPerSecond: VIDEO_BPS,
    audioBitsPerSecond: AUDIO_BPS,
  });
  recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
  recorder.onstop = finishRecording;
  const startedAt = performance.now();
  recorder.start(1000);
  report.recording = { requestedType: mimeType, actualType: recorder.mimeType };
  $('record').disabled = true;
  $('stop').disabled = false;
  timer = setInterval(() => {
    const elapsed = (performance.now() - startedAt) / 1000;
    const left = Math.max(0, MAX_SECONDS - elapsed);
    $('countdown').textContent = `0:${String(Math.ceil(left)).padStart(2, '0')} left`;
    if (left <= 0) stopRecording();
  }, 250);
  report.recording.startedAtMs = startedAt;
}

function stopRecording() {
  clearInterval(timer);
  if (recorder?.state === 'recording') recorder.stop();
  $('stop').disabled = true;
}

function finishRecording() {
  const elapsedS = (performance.now() - report.recording.startedAtMs) / 1000;
  const blob = new Blob(chunks, { type: recorder.mimeType });
  const url = URL.createObjectURL(blob);
  $('preview').src = url;
  $('download').href = url;
  $('download').download = `spike5.${blob.type.includes('mp4') ? 'mp4' : 'webm'}`;
  $('download').hidden = false;
  $('preview').onloadedmetadata = () => {
    report.recording.videoElementDuration = $('preview').duration;
    report.recording.videoWidth = $('preview').videoWidth;
    report.recording.videoHeight = $('preview').videoHeight;
    show('result', report);
  };
  Object.assign(report.recording, {
    chunks: chunks.length,
    bytes: blob.size,
    megabytes: +(blob.size / 1e6).toFixed(2),
    wallClockSeconds: +elapsedS.toFixed(1),
    effectiveKbps: Math.round((blob.size * 8) / elapsedS / 1000),
  });
  delete report.recording.startedAtMs;
  show('result', report);
  $('copy').disabled = false;
  $('record').disabled = false;
}

async function copyResults() {
  const text = JSON.stringify(report, null, 2);
  try {
    await navigator.clipboard.writeText(text);
    $('copy').textContent = 'Copied';
  } catch {
    $('copy').textContent = 'Copy failed: select the text above';
  }
}

$('start').addEventListener('click', startCamera);
$('torch').addEventListener('click', toggleTorch);
$('record').addEventListener('click', startRecording);
$('stop').addEventListener('click', stopRecording);
$('copy').addEventListener('click', copyResults);
describeEnvironment();
