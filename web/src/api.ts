// API client. The base URL is absolute (VITE_API_BASE_URL) so the same build can run inside a
// native shell later; cookies carry the session and the CSRF token goes in a header.
const BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
let csrfToken = "";

export function setCsrf(token: string | undefined): void {
  csrfToken = token ?? "";
}

export function apiUrl(path: string): string {
  return path.startsWith("http") ? path : `${BASE}${path}`;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public body: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

type Options = { method?: string; json?: unknown; signal?: AbortSignal };

export async function api<T>(path: string, opts: Options = {}): Promise<T> {
  const method = (opts.method ?? "GET").toUpperCase();
  const headers: Record<string, string> = {};
  let body: string | undefined;
  if (opts.json !== undefined) {
    headers["content-type"] = "application/json";
    body = JSON.stringify(opts.json);
  }
  if (method !== "GET" && csrfToken) headers["x-csrf-token"] = csrfToken;
  let res: Response;
  try {
    res = await fetch(apiUrl(path), { method, headers, body, credentials: "include", signal: opts.signal });
  } catch {
    throw new ApiError(0, "offline", "No internet connection.");
  }
  if (!res.ok) {
    let data: Record<string, unknown> = {};
    try {
      data = await res.json();
    } catch {
      /* non-JSON error */
    }
    throw new ApiError(res.status, String(data.code ?? "http_error"), String(data.title ?? res.statusText), data);
  }
  return (await res.json()) as T;
}

export function uploadVideo(blob: Blob, onProgress: (fraction: number) => void): Promise<{ id: string }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", apiUrl("/api/v1/uploads"));
    xhr.withCredentials = true;
    xhr.setRequestHeader("content-type", blob.type || "video/mp4");
    if (csrfToken) xhr.setRequestHeader("x-csrf-token", csrfToken);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onload = () => {
      let data: Record<string, unknown> = {};
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        /* ignore */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data as { id: string });
      else reject(new ApiError(xhr.status, String(data.code ?? "http_error"), String(data.title ?? "Upload failed")));
    };
    xhr.onerror = () => reject(new ApiError(0, "offline", "No internet connection."));
    xhr.send(blob);
  });
}

// --- Shapes returned by the API ---------------------------------------------------------
export type Workspace = {
  name: string;
  slug: string;
  whatsapp: string | null;
  language: "en" | "hi";
  ai_mark: boolean;
  raw_retention_days: number;
  consent_account: boolean;
  consent_recording: boolean;
};

export type Me = { name: string; workspace: Workspace; environment: string; csrf_token: string };

export type Job = {
  id: string;
  status: "queued" | "running" | "needs_review" | "published" | "failed";
  stages: Record<string, string>;
  error_code: string | null;
  error_message: string | null;
  open_flags: number;
};

export type ReviewProduct = {
  idx: number;
  title_en: string;
  title_hi: string;
  price_inr: number | null;
  price_display: string | null;
  source: string;
  confidence: number;
  brand: string | null;
  image_url: string | null;
  ai_background: boolean;
  removed: boolean;
};

export type Flag = {
  id: string;
  kind: string;
  product_idx: number | null;
  question_key: string;
  params: Record<string, string | number>;
  options: number[];
  candidates: number[];
  status: "open" | "resolved" | "dismissed";
};

export type Review = { job: Job; products: ReviewProduct[]; flags: Flag[] };

export type PublicProduct = {
  id: string;
  title_en: string;
  title_hi: string;
  description_en: string;
  description_hi: string;
  price_display: string;
  image_url: string;
  ai_background: boolean;
  order_link_en: string;
  order_link_hi: string;
};

export type PublicShop = { version: number; shop: { name: string; slug: string }; products: PublicProduct[] };

export type MyCatalog =
  | { published: false }
  | {
      published: true;
      version: number;
      items: number;
      url: string;
      feed_url: string | null;
      feed_left_out: number;
      photos_url: string;
    };
