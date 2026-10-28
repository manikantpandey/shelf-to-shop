// API client. The base URL is absolute (VITE_API_BASE_URL) so the same build can run inside a
// native shell later; cookies carry the session and the CSRF token goes in a header.
const BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
let csrfToken = "";

export function setCsrf(token: string | undefined): void {
  csrfToken = token ?? "";
}

export function csrfHeaders(): Record<string, string> {
  return csrfToken ? { "x-csrf-token": csrfToken } : {};
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

export type UploadResult = { id: string; duration_s: number; needs_clip: boolean; max_clip_s: number; status?: string };

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
  created_at?: string;
};

export type ReviewProduct = {
  id: string;
  idx: number;
  title_en: string;
  title_hi: string;
  price_inr: number | null;
  price_display: string | null;
  mrp_inr: number | null;
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
  price_paise: number;
  mrp_display: string | null;
  section: string | null;
  featured: boolean;
  image_url: string;
  ai_background: boolean;
  sold_out: boolean;
  image_credit: string | null;
  image_credit_url: string | null;
  order_link_en: string;
  order_link_hi: string;
};

export type Profile = {
  address: string | null;
  hours: string | null;
  delivery: "pickup" | "delivery" | "both";
  delivery_note: string | null;
  min_order_inr: number | null;
  upi_id: string | null;
  about: string | null;
  notice: string | null;
  logo_url: string | null;
};

export type ShopSection = { id: string; name_en: string; name_hi: string; items?: number };

export type PublicShop = {
  version: number;
  shop: { name: string; slug: string; whatsapp: string };
  products: PublicProduct[];
  profile: Profile;
  sections: ShopSection[];
};

export type OrderLine = { id: string; title: string; qty: number; price_inr: number };

export type Order = {
  id: string;
  number: number;
  created_at: string;
  customer_name: string | null;
  note: string | null;
  items: OrderLine[];
  total_inr: number;
  total_display: string;
  status: "new" | "packed" | "delivered" | "cancelled";
  paid: boolean;
};

export type OrderSummary = {
  counts: Record<Order["status"], number>;
  today_orders: number;
  today_total_inr: number;
  today_paid_inr: number;
};

export type MyCatalog =
  | { published: false }
  | {
      published: true;
      version: number;
      items: number;
      url: string;
      published_at: string;
      feed_url: string | null;
      feed_left_out: number;
      photos_url: string;
    };

export type Item = {
  id: string;
  public_id: string;
  job_id: string;
  idx: number;
  title_en: string;
  title_hi: string;
  price_inr: number | null;
  price_display: string | null;
  mrp_inr: number | null;
  sold_out: boolean;
  hidden: boolean;
  featured: boolean;
  section_id: string | null;
  from_video: boolean;
  live: boolean;
  published: boolean;
  category: string;
  brand: string | null;
  image_url: string | null;
  image_source: "video" | "frame" | "upload" | "openfoodfacts";
  image_credit: string | null;
  ai_background: boolean;
  added_at: string;
};

export type ItemSaved = { item: Item; shop_version: number | null };

export type Stats = {
  items_live: number;
  items_sold_out: number;
  views_7d: number;
  orders_7d: number;
  by_day: { day: string; views: number; orders: number }[];
  top_items: { id: string; title: string; orders: number }[];
  videos: number;
  videos_to_check: number;
  videos_processing: number;
  questions_open: number;
  spend_usd: string;
  shop_url: string | null;
  published_at: string | null;
  orders: OrderSummary;
};

export type VideoSummary = {
  id: string;
  status: Job["status"];
  created_at: string;
  duration_s: number | null;
  items: number;
  titles: string[];
  open_flags: number;
  cost_usd: string;
  thumb_url: string | null;
  error_message: string | null;
};

export type Evidence = { kind: string; value_inr: number | null; t_s: number | null; snippet: string | null };

export type JobDetails = {
  id: string;
  status: Job["status"];
  created_at: string;
  duration_s: number | null;
  total_seconds: number | null;
  cost_usd: string;
  stages: {
    stage: string;
    status: string;
    seconds: number | null;
    calls: number;
    models: string[];
    cost_usd: string;
    input_tokens: number;
    output_tokens: number;
    errors: number;
  }[];
  transcript: { start_s: number | null; end_s: number | null; text: string }[];
  items: {
    idx: number;
    title_en: string;
    title_hi: string;
    price_inr: number | null;
    source: string;
    confidence: number;
    removed: boolean;
    first_seen_s: number | null;
    last_seen_s: number | null;
    evidence: Evidence[];
    image_url: string | null;
    frame_url: string | null;
  }[];
};

export type Moment = { i: number; t_s: number; image_url: string };
export type PackResult = { code: string; name: string; brand: string | null; image_url: string };

/** POST a raw image body (the server checks it is really a photo). */
export async function uploadImage(path: string, file: Blob): Promise<unknown> {
  const headers: Record<string, string> = { "content-type": file.type || "image/jpeg" };
  if (csrfToken) headers["x-csrf-token"] = csrfToken;
  let res: Response;
  try {
    res = await fetch(apiUrl(path), { method: "POST", headers, body: file, credentials: "include" });
  } catch {
    throw new ApiError(0, "offline", "No internet connection.");
  }
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  if (!res.ok) throw new ApiError(res.status, String(data.code ?? "http_error"), String(data.title ?? res.statusText), data);
  return data;
}

export async function uploadPhoto(itemId: string, file: Blob): Promise<ItemSaved> {
  return (await uploadImage(`/api/v1/items/${itemId}/photo`, file)) as ItemSaved;
}

/** Public shop page counters (views, order taps). Best effort: never blocks the buyer. */
export function countShopEvent(slug: string, kind: "view" | "order", item?: string): void {
  try {
    void fetch(apiUrl(`/api/v1/public/shops/${encodeURIComponent(slug)}/events`), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(item ? { kind, item } : { kind }),
      keepalive: true,
      credentials: "omit",
    }).catch(() => undefined);
  } catch {
    /* counting is optional */
  }
}
