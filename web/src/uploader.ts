// Resumable upload: the video goes in pieces; after a drop we ask the server where to carry on.
import { apiUrl, ApiError, csrfHeaders, type UploadResult } from "./api";

type Fetch = typeof fetch;

export type Progress = (fraction: number) => void;

type Options = {
  onProgress: Progress;
  /** An upload started earlier (saved on the phone): carry on with it if the server still has it. */
  resumeId?: string;
  onSession?: (id: string) => void;
  fetchImpl?: Fetch;
  /** Waits between retries of one piece, in ms. */
  backoff?: number[];
};

type UploadState = UploadResult & { status: "receiving" | "ready" | "rejected"; offset: number; chunk_size?: number };

const DEFAULT_CHUNK = 4 * 1024 * 1024;
const BACKOFF = [1000, 2000, 4000, 8000, 15000];

async function call(fetchImpl: Fetch, path: string, init: RequestInit): Promise<{ status: number; body: Record<string, unknown> }> {
  let res: Response;
  try {
    res = await fetchImpl(apiUrl(path), { ...init, credentials: "include" });
  } catch {
    return { status: 0, body: {} };
  }
  const body = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  return { status: res.status, body };
}

function refuse(status: number, body: Record<string, unknown>): never {
  throw new ApiError(status, String(body.code ?? "http_error"), String(body.title ?? "Upload failed"), body);
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export async function resumableUpload(blob: Blob, opts: Options): Promise<UploadResult> {
  const fetchImpl = opts.fetchImpl ?? fetch.bind(window);
  const backoff = opts.backoff ?? BACKOFF;
  const json = { "content-type": "application/json", ...csrfHeaders() };
  let state: UploadState | null = null;

  if (opts.resumeId) {
    const r = await call(fetchImpl, `/api/v1/uploads/${opts.resumeId}`, { method: "GET" });
    if (r.status === 200 && (r.body.status === "receiving" || r.body.status === "ready")) state = r.body as UploadState;
  }
  if (!state) {
    const r = await call(fetchImpl, "/api/v1/uploads/sessions", {
      method: "POST",
      headers: json,
      body: JSON.stringify({ size: blob.size }),
    });
    if (r.status !== 201) {
      if (r.status === 0) throw new ApiError(0, "offline", "No internet connection.");
      refuse(r.status, r.body);
    }
    state = r.body as UploadState;
    opts.onSession?.(state.id);
  }
  const chunk = state.chunk_size ?? DEFAULT_CHUNK;
  let offset = state.offset;
  opts.onProgress(offset / blob.size);

  while (state.status !== "ready") {
    const piece = blob.slice(offset, Math.min(blob.size, offset + chunk));
    let attempt = 0;
    for (;;) {
      const r = await call(fetchImpl, `/api/v1/uploads/${state.id}`, {
        method: "PATCH",
        headers: { "content-type": "application/octet-stream", "upload-offset": String(offset), ...csrfHeaders() },
        body: piece,
      });
      if (r.status === 200) {
        state = r.body as UploadState;
        offset = state.offset;
        break;
      }
      if (r.status === 409 && typeof r.body.offset === "number") {
        // The server has a different amount than we thought (a retried piece had arrived): carry on there.
        offset = r.body.offset;
        break;
      }
      if (r.status !== 0 && r.status < 500 && r.status !== 429) refuse(r.status, r.body);
      if (attempt >= backoff.length) throw new ApiError(0, "offline", "No internet connection.");
      await sleep(backoff[attempt]);
      attempt += 1;
    }
    opts.onProgress(Math.min(1, offset / blob.size));
  }
  return state;
}
