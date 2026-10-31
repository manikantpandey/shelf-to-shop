# Phoenix integration (socialpulse mode)

> **Status: design, not implemented; the socialpulse mode code is a follow-up.** Nothing in this
> document is shipped behaviour. Today `APP_MODE=socialpulse` stops at start-up with "APP_MODE=socialpulse
> needs integrations.socialpulse.plugin, which is not in this build" (`src/shelf/plugins.py`). Where this
> design depends on code that exists, it names the file. Where it needs new code, section 11 lists it.

This is for engineers at SocialPulse who connect their assistant, Phoenix, to Shelf-to-Shop. Phoenix
talks to sellers. Shelf-to-Shop turns a seller's shelf video into a catalog. Phoenix starts the job and
reads the results; the seller approves the catalog in Shelf-to-Shop's review screen.

Terms used below:

- **Workspace**: one seller's shop in Shelf-to-Shop. Every key, job, flag and catalog belongs to one.
- **Operator**: whoever runs the Shelf-to-Shop instance.
- **Executor**: SocialPulse's server code that runs Phoenix's tool calls. It holds the API keys, signs
  requests and uploads video bytes. The model never sees keys or bytes.

Contents

1. [What Phoenix can and cannot do](#1-what-phoenix-can-and-cannot-do)
2. [Enabling the mode](#2-enabling-the-mode)
3. [Tool manifest](#3-tool-manifest)
4. [Authentication, signing and idempotency](#4-authentication-signing-and-idempotency)
5. [Webhooks](#5-webhooks)
6. [The review link](#6-the-review-link)
7. [Sinks](#7-sinks)
8. [Error codes](#8-error-codes)
9. [Worked example](#9-worked-example)
10. [Verification code and test vectors](#10-verification-code-and-test-vectors)
11. [Security notes and implementation checklist](#11-security-notes-and-implementation-checklist)

---

## 1. What Phoenix can and cannot do

| Phoenix can | Phoenix cannot |
|---|---|
| Start a catalog job from a video the seller sent (`create_catalog_job`) | Publish a catalog. Only the seller can, by tapping "Publish" in the review screen |
| Upload that video in resumable pieces | Make Shelf-to-Shop fetch a URL. Shelf-to-Shop never downloads from a URL a caller supplies |
| Follow the job and get the seller's private review link (`get_job_status`) | Give consent for the seller. The seller agrees to the notices in Shelf-to-Shop's own screens |
| Read the questions about prices, duplicates and photos (`list_flags`) | Change the seller's WhatsApp number, shop name, settings or retention |
| Pass on the seller's answer to a question (`resolve_flag`) | See videos, frames, transcripts, price evidence, costs or the seller's email |
| Read the published catalog: page link, items, prices (`get_catalog`) | Reach another workspace. A key belongs to one workspace |
| Receive signed webhooks when a job needs review, completes or fails, and when a catalog is published | Pay, send messages or post anywhere. No tool does any of these |

Shelf-to-Shop runs its own AI engine in this mode, exactly as in standalone mode: the same pipeline,
the same spend caps per job, per shop per day and per service per day, and the same run log. Phoenix
runs the conversation. Shelf-to-Shop does the work.

Answers given through `resolve_flag` do not publish anything. The seller still sees every item and
price in the review screen, and answers that came through Phoenix are marked "Answered in SocialPulse"
there.

## 2. Enabling the mode

### 2.1 Configuration

The mode is chosen by configuration, never by a code fork. `shelf.plugins.load_integration` imports
`integrations.socialpulse.plugin` by name when `APP_MODE=socialpulse`, so the core package never
imports `integrations` (import-linter contract `core-without-integrations` enforces this). Demo sign-in
is already refused outside standalone mode (`shelf/config.py`).

| Variable | Required | Meaning |
|---|---|---|
| `APP_MODE` | yes | `socialpulse` |
| `API_KEY_PEPPER` | yes | 32+ random characters. Key for hashing API key secrets. Separate from `SECRET_KEY` |
| `API_KEY_PEPPER_PREVIOUS` | no | The old pepper during a pepper rotation (section 4.1) |
| `REVIEW_LINK_TTL_HOURS` | no | Review link lifetime, default 24, allowed 1 to 72 |
| `SOCIALPULSE_WEBHOOK_URL` | yes | Where webhooks go. `https` only. Its host is added to the outbound allowlist |
| `SOCIALPULSE_WEBHOOK_SECRET` | yes | 32+ random characters. Signs webhooks |
| `SOCIALPULSE_WEBHOOK_SECRET_PREVIOUS` | no | The old webhook secret during a rotation |
| `SOCIALPULSE_WEBHOOK_SECRET_PREVIOUS_UNTIL` | no | ISO 8601 time after which the old secret is no longer used |
| `SOCIALPULSE_SINK_URL` | no | Full `https` URL that receives approved catalogs (section 7). Unset means no push |
| `SOCIALPULSE_SINK_KEY` | with sink URL | Bearer key sent to the sink URL |
| `TOOLS_RATE_PER_KEY_PER_MIN` | no | Tool calls per key per minute, default 120 |

The plugin validates these at start-up and refuses to start on a missing or short secret, a non-https
URL, or a pepper equal to `SECRET_KEY`. In production they come from AWS Parameter Store under
`/shelf-to-shop/*`, like the other secrets (`docs/runbook.md`).

### 2.2 Where the code goes

Everything that knows about SocialPulse lives in `src/integrations/socialpulse/`:

```
src/integrations/socialpulse/
  plugin.py        register(app, settings): routes, event handlers, task handlers, sink
  settings.py      the variables above, validated at start-up
  models.py        sp_* tables, on their own Alembic branch label "socialpulse"
  auth.py          key parsing and checking, request signatures, nonce store, scopes
  idempotency.py   Idempotency-Key records
  tools.py         the five tools and the manifest (schemas generated from the pydantic models)
  uploads.py       GET and PATCH /tools/uploads/{id}, on the core upload functions
  questions.py     flag questions in English and Hindi (same strings as the review screen)
  webhooks.py      events to deliveries, the delivery task, signing
  sink.py          SocialPulseSink
  admin.py         operator command line
```

The core needs a few small seams. None of them names SocialPulse or imports `integrations`, and each is
useful on its own:

1. **Events** (`shelf/events.py`): `on(event, handler)` and `emit(db, event, **data)`. The core emits,
   inside the same transaction as the change, `job.needs_review` and `job.failed`
   (`jobs/service.py: run_pipeline_job`), `job.published` (`catalog/publish.py: publish_job`; sent to
   SocialPulse as the `job.completed` webhook) and `catalog.published` (`publish_shop`). With no handlers registered (standalone) it does nothing.
   Because handlers write their rows in the same transaction, an event is never lost or sent for a
   change that rolled back.
2. **Signed links and job-scoped review sessions** (`shelf/auth/links.py`): section 6. Review routes in
   `api/v1/seller.py` and the photo routes in `api/v1/items.py` accept either a full seller session or
   a review session for that job; `current_seller` refuses review sessions everywhere else.
3. **Jobs and uploads**: `create_job(..., job_id=None)` so a job id can be handed out before the video
   arrives, and the piece-append logic in `api/v1/uploads.py: upload_piece` moved into a function both
   upload routes call.
4. **Worker hooks**: `shelf.jobs.worker.main` loads the plugin and adds its task handlers (webhook
   delivery, sink push, failing jobs whose upload expired, nonce and idempotency clean-up). Today only
   the API process loads plugins.
5. **Sinks** (`shelf/sinks/`): the `Sink` protocol and `LocalSink` (section 7).

### 2.3 Setting up a seller

Real seller sign-in (email one-time code) is not built yet (`docs/security.md`, "Not done yet"), and
demo sign-in is refused in this mode. Until sign-in exists, the operator sets sellers up from the
command line, and the seller gives consent through a single-purpose setup link:

1. Operator: `uv run python -m integrations.socialpulse.admin add-shop --name "<shop name>"
   --whatsapp "<number>" --language hi`. This creates the workspace (no email needed) and prints its
   id and a setup link (signed, single use, 72 hours).
2. The seller opens the setup link (SocialPulse may pass it on in chat). The page shows the account
   notice, the recording notice ("videos are only for making your catalog, are deleted after 7 days,
   and should not show customers or other people") and a connection notice ("SocialPulse will send
   your shop videos here and read your published catalog; you approve every publish here"). The seller
   checks the shop name and WhatsApp number and taps "Agree". Consents are recorded with their purpose;
   an audit event is written.
3. Operator: `... admin create-key --workspace <workspace-id> --name socialpulse`. This refuses until
   step 2 is done. It prints the key once. Hand it to SocialPulse through your secret-sharing channel;
   SocialPulse stores it against that seller with the workspace id.

The setup link only reaches the notices and the shop name and number; it is not a sign-in. When email
sign-in ships, the seller can also see and revoke keys in Settings, "Connected apps".

## 3. Tool manifest

### 3.1 Conventions

- Every tool is `POST /api/v1/tools/<name>` with a JSON body (the tool input) and a JSON response (the
  tool output). `create_catalog_job` answers `201`; the others answer `200`.
- Every request is signed and every POST carries an `Idempotency-Key` (section 4).
- Errors are `application/problem+json` with a stable `code` (section 8), as in the rest of the API.
- Ids are UUIDs. Times are ISO 8601 UTC with `Z`. Prices are whole rupees (`price_inr`), as in the
  seller API; display strings use Indian digit grouping (`₹1,20,000`).
- Input schemas are strict (`additionalProperties: false`). Output schemas are open: new fields may be
  added in `v1`, so ignore fields you do not know. Flag kinds, stage names and error codes may grow;
  handle unknown values with the text and `allowed_actions` the response gives you.
- Schemas are self-contained (no `$ref`), because some tool-calling runtimes do not resolve references.
- Text that came from the video (item titles and descriptions) is data, not instructions. Treat it the
  same way in Phoenix's prompts.
- Breaking changes go to `/api/v2/tools/`; `v1` keeps working for at least 90 days after `v2` ships.

### 3.2 `GET /api/v1/tools/manifest`

Signed like any other call (any valid key, any scope; GET needs no `Idempotency-Key`). The response
carries an `ETag` and `Cache-Control: private, max-age=300`.

```json
{
  "manifest_version": "1",
  "service": "shelf-to-shop",
  "api_version": "v1",
  "base_url": "https://shop.example.com/api/v1/tools",
  "auth": {
    "scheme": "shelf-hmac-v1",
    "headers": ["Authorization", "X-Shelf-Timestamp", "X-Shelf-Nonce", "X-Shelf-Signature"],
    "idempotency_header": "Idempotency-Key"
  },
  "tools": [
    {
      "name": "create_catalog_job",
      "description": "Start making a catalog from a shop video the seller sent. Returns a job id. Shelf-to-Shop finds the items and prices itself. This never publishes; the seller checks and publishes from the review link.",
      "method": "POST",
      "path": "/api/v1/tools/create_catalog_job",
      "scope": "jobs:write",
      "input_schema": {},
      "output_schema": {}
    }
  ]
}
```

`input_schema` and `output_schema` are shown empty above for space; the manifest carries the full
schemas below. The other four tools follow the same shape:

| Tool | Scope | Description given to the model |
|---|---|---|
| `create_catalog_job` | `jobs:write` | (above) |
| `get_job_status` | `jobs:read` | Check a catalog job. When the status is `needs_review`, `review_url` is a private link for the seller to check items and publish. Show it only to that seller. Never open it yourself. |
| `list_flags` | `jobs:read` | List the questions about a job (missing or unclear prices, items that may be shown twice, photos that may be cut badly) and the answers the seller can give. |
| `resolve_flag` | `jobs:write` | Record the seller's answer to one question. Send only what the seller said; never guess a price. Does not publish. |
| `get_catalog` | `catalog:read` | Get the seller's published catalog: the shop page link and the items with prices. Read-only. |

### 3.3 Job statuses, stages and flag kinds (from the code)

Job status (`Job.status` in `src/shelf/db/models/core.py`, plus one integration-only value):

| Status | Meaning | Next |
|---|---|---|
| `awaiting_upload` | Integration only: the job id is reserved, the video has not fully arrived. No core job row yet | `queued`, or `failed` with an upload error |
| `queued` | Waiting for a worker | `running` |
| `running` | The pipeline is working | `needs_review` or `failed` |
| `needs_review` | Items and questions are ready. The seller must open the review link and publish | `published` |
| `published` | The seller approved; the items are on the shop page, in the feed and the photo zip | (final) |
| `failed` | Stopped; `error.code` says why | a new job, as `next_step` says (section 3.5) |

A job in `needs_review` always needs the seller's approval, even with zero open questions.

Stages, in order (`STAGE_ORDER` in `jobs/service.py`): `ingest`, `detect`, `transcribe`, `segment`,
`enrich`, `match`, `verify`, `backgrounds`. Each is `waiting`, `running`, `done`, `cached` or `failed`.

Flag kinds (`FlagKind` in `engine/pipeline/schemas.py`) and the answers the tool accepts. These match
the buttons the review screen offers (`web/src/screens/Review.tsx`); `resolve_flag` refuses others.

| Kind | Asked when | Allowed actions |
|---|---|---|
| `missing_price` | No price was heard or seen for an item | `set_price`, `remove_item` |
| `price_conflict` | Two prices for one item (spoken against tag, two spoken, or speech against the video model) | `set_price` |
| `ambiguous_price` | A price could belong to more than one item | `set_price` with a `product_idx` from `candidates` and the price from `options`, or `dismiss` ("none of these") |
| `implausible_price` | A price far from the others, or above the absolute limit | `set_price` |
| `uncertain_price` | The price may have been misheard | `set_price` |
| `duplicate` | The same item may appear twice | `remove_item` (removes this one), `dismiss` (keep both) |
| `low_conf_mask` | The photo may be cut badly | `dismiss` (photo is fine), `remove_item`. A new photo can only be chosen in the review screen |

### 3.4 `create_catalog_job`

Send exactly one of `upload_id` (a video already in Shelf-to-Shop) or `video` (one you are about to
upload). With `video`, the response has an upload slot; the job starts by itself when the last byte
arrives and the file passes the checks. Shelf-to-Shop never fetches a URL to get a video.

The `video` object is filled in by the executor from the media the seller sent, not by the model. The
executor should finish the upload (section 3.9) before it returns the tool result to the model.

Video rules are the core's (`engine/media/probe.py`, `api/v1/seller.py`): MP4, MOV or WebM by content
(not by name), at most 200 MB, 2 to 75 seconds used as is. Videos up to 600 seconds are accepted with
`start_s`, which picks the 60-second part to use; without it a long video fails with `pick_part`.
The seller must have agreed to the recording notice, or the call answers `403 consent_required`.
Creating a job counts against the shop's upload limit (30 per hour).

Input:

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["client_ref"],
  "properties": {
    "client_ref": {
      "type": "string",
      "minLength": 1,
      "maxLength": 100,
      "pattern": "^[A-Za-z0-9._:-]+$",
      "description": "Your reference for this request (for example a conversation id). Echoed in status and webhooks. No names, phone numbers or other personal data."
    },
    "upload_id": {
      "type": "string",
      "format": "uuid",
      "description": "A video already in Shelf-to-Shop with status ready. Send this or video, not both."
    },
    "video": {
      "type": "object",
      "additionalProperties": false,
      "required": ["size_bytes"],
      "description": "Filled in by the executor: the video it will upload.",
      "properties": {
        "size_bytes": {"type": "integer", "minimum": 1, "maximum": 209715200},
        "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$", "description": "Optional. Checked when the last byte arrives."}
      }
    },
    "start_s": {
      "type": "number",
      "minimum": 0,
      "description": "Only for videos longer than 75 seconds: where the 60-second part to use starts."
    }
  }
}
```

Output:

```json
{
  "type": "object",
  "required": ["job_id", "client_ref", "status", "upload"],
  "properties": {
    "job_id": {"type": "string", "format": "uuid"},
    "client_ref": {"type": "string"},
    "status": {"enum": ["awaiting_upload", "queued"]},
    "upload": {
      "type": ["object", "null"],
      "description": "Where to send the bytes, when you sent video. Null when you sent upload_id.",
      "required": ["id", "url", "offset", "size_bytes", "chunk_size", "max_chunk_size", "expires_at"],
      "properties": {
        "id": {"type": "string", "format": "uuid"},
        "url": {"type": "string", "format": "uri"},
        "offset": {"type": "integer", "minimum": 0},
        "size_bytes": {"type": "integer"},
        "chunk_size": {"type": "integer", "description": "Suggested piece size: 4194304 (4 MB)."},
        "max_chunk_size": {"type": "integer", "description": "Largest piece accepted: 8388608 (8 MB)."},
        "expires_at": {"type": "string", "format": "date-time", "description": "24 hours after creation. Unfinished uploads are deleted then."}
      }
    }
  }
}
```

Trying again after a failure: call `create_catalog_job` with the same `upload_id` (the video is kept
until the shop's retention period ends, default 7 days). An upload can back only one job that has not
failed; otherwise the answer is `409 upload_in_use`.

### 3.5 `get_job_status`

Input:

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["job_id"],
  "properties": {
    "job_id": {"type": "string", "format": "uuid"}
  }
}
```

Output:

```json
{
  "type": "object",
  "required": ["job_id", "client_ref", "status", "stages", "products_found", "open_flags", "error", "review_url", "review_url_expires_at", "catalog_version", "page_url", "created_at", "updated_at"],
  "properties": {
    "job_id": {"type": "string", "format": "uuid"},
    "client_ref": {"type": ["string", "null"], "description": "Null for jobs the seller started in the app."},
    "status": {"enum": ["awaiting_upload", "queued", "running", "needs_review", "published", "failed"]},
    "stages": {
      "type": "object",
      "description": "Stage name to state, in pipeline order. More stages may be added.",
      "additionalProperties": {"enum": ["waiting", "running", "done", "cached", "failed"]}
    },
    "products_found": {"type": ["integer", "null"], "minimum": 0},
    "open_flags": {"type": "integer", "minimum": 0},
    "error": {
      "type": ["object", "null"],
      "required": ["code", "message", "next_step"],
      "properties": {
        "code": {"type": "string"},
        "message": {"type": "string", "description": "Plain English for the seller."},
        "next_step": {"enum": ["retry", "retry_tomorrow", "record_again", "upload_again"]}
      }
    },
    "review_url": {
      "type": ["string", "null"],
      "format": "uri",
      "description": "Only when status is needs_review. Private: show it only to this seller. Never open it yourself."
    },
    "review_url_expires_at": {"type": ["string", "null"], "format": "date-time"},
    "catalog_version": {"type": ["integer", "null"], "description": "Set when published."},
    "page_url": {"type": ["string", "null"], "format": "uri", "description": "Public shop page, set when published."},
    "created_at": {"type": "string", "format": "date-time"},
    "updated_at": {"type": "string", "format": "date-time"}
  }
}
```

`next_step` for each failure code:

| `next_step` | Codes | What to tell the seller |
|---|---|---|
| `retry` | `model_unavailable`, `internal`, `pick_part` | Try again in a few minutes (`create_catalog_job` with the same `upload_id`; add `start_s` for `pick_part`) |
| `retry_tomorrow` | `daily_cap`, `service_daily_cap` | Today's limit is used up |
| `record_again` | `spend_cap`, `video_deleted`, `not_a_video`, `unreadable`, `no_video_stream`, `too_short`, `too_long`, `bad_resolution`, `too_large` | Record a new video (shorter, for `spend_cap` and `too_long`) |
| `upload_again` | `checksum_mismatch`, `upload_expired` | Send the same video again |

Poll at most every 10 seconds, or wait for webhooks. Processing a 60-second video takes minutes.

### 3.6 `list_flags`

Input:

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["job_id"],
  "properties": {
    "job_id": {"type": "string", "format": "uuid"},
    "status": {"enum": ["open", "all"], "default": "open"}
  }
}
```

Output:

```json
{
  "type": "object",
  "required": ["job_id", "flags"],
  "properties": {
    "job_id": {"type": "string", "format": "uuid"},
    "flags": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["flag_id", "kind", "status", "question", "product", "options", "candidates", "allowed_actions", "answered_by"],
        "properties": {
          "flag_id": {"type": "string", "format": "uuid"},
          "kind": {"type": "string", "description": "See the flag kinds table. More may be added."},
          "status": {"enum": ["open", "resolved", "dismissed"]},
          "question": {
            "type": "object",
            "required": ["en", "hi"],
            "properties": {"en": {"type": "string"}, "hi": {"type": "string"}},
            "description": "The question as the review screen asks it, with item names and prices filled in."
          },
          "product": {
            "type": ["object", "null"],
            "required": ["idx", "title_en", "title_hi", "price_inr"],
            "properties": {
              "idx": {"type": "integer", "minimum": 0},
              "title_en": {"type": "string"},
              "title_hi": {"type": "string"},
              "price_inr": {"type": ["integer", "null"]}
            }
          },
          "options": {"type": "array", "items": {"type": "integer"}, "description": "Suggested prices in rupees."},
          "candidates": {
            "type": "array",
            "description": "Items the question may be about.",
            "items": {
              "type": "object",
              "required": ["idx", "title_en", "title_hi"],
              "properties": {
                "idx": {"type": "integer", "minimum": 0},
                "title_en": {"type": "string"},
                "title_hi": {"type": "string"}
              }
            }
          },
          "allowed_actions": {"type": "array", "items": {"enum": ["set_price", "dismiss", "remove_item"]}},
          "answered_by": {"enum": ["seller", "api", null]}
        }
      }
    }
  }
}
```

Questions are rendered from the same strings as the review screen (`review.q.*` in
`web/src/locales/en.json` and `hi.json`); a test keeps the Python copy in step with them.

### 3.7 `resolve_flag`

Allowed only while the job is `needs_review`. The same rules as the review screen's
`POST /jobs/{id}/flags/{flag_id}/resolve` apply (prices 1 to 1 crore; answering one price question for
an item also closes that item's other open price questions). The answer is recorded with
`answered_by: "api"`, the key prefix, and an audit event.

Input:

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["job_id", "flag_id", "action"],
  "properties": {
    "job_id": {"type": "string", "format": "uuid"},
    "flag_id": {"type": "string", "format": "uuid"},
    "action": {"enum": ["set_price", "dismiss", "remove_item"], "description": "One of the flag's allowed_actions."},
    "price_inr": {"type": "integer", "minimum": 1, "maximum": 10000000, "description": "Whole rupees, for set_price. Only a price the seller said."},
    "product_idx": {"type": "integer", "minimum": 0, "description": "Which item, when the flag has candidates."}
  }
}
```

Output:

```json
{
  "type": "object",
  "required": ["flag", "job_status", "open_flags"],
  "properties": {
    "flag": {"type": "object", "description": "The flag after the answer, in the list_flags item shape."},
    "job_status": {"type": "string"},
    "open_flags": {"type": "integer", "minimum": 0}
  }
}
```

### 3.8 `get_catalog`

Reads the latest published version of the shop: the same allowlisted snapshot the public page serves
(`catalog/publish.py`). Every new version counts, including ones the seller makes by editing items.

Input:

```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 100},
    "offset": {"type": "integer", "minimum": 0, "default": 0}
  }
}
```

Output:

```json
{
  "type": "object",
  "required": ["published", "version", "published_at", "page_url", "feed_url", "photos_url", "total_items", "feed_left_out", "products"],
  "properties": {
    "published": {"type": "boolean"},
    "version": {"type": ["integer", "null"]},
    "published_at": {"type": ["string", "null"], "format": "date-time"},
    "page_url": {"type": ["string", "null"], "format": "uri", "description": "Public shop page. Safe to share with anyone."},
    "feed_url": {"type": ["string", "null"], "format": "uri", "description": "Meta catalog feed CSV. Needs a signed request with catalog:read. Null when no item passed Meta's feed rules."},
    "photos_url": {"type": ["string", "null"], "format": "uri", "description": "Zip of item photos. Needs a signed request with catalog:read."},
    "total_items": {"type": "integer", "minimum": 0},
    "feed_left_out": {"type": "integer", "minimum": 0, "description": "Items on the page that Meta's feed rules left out."},
    "products": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "title_en", "title_hi", "description_en", "description_hi", "price_inr", "price_display", "mrp_display", "image_url", "ai_background", "sold_out", "product_url"],
        "properties": {
          "id": {"type": "string", "description": "Public item id, the same as the feed's id column."},
          "title_en": {"type": "string"},
          "title_hi": {"type": "string"},
          "description_en": {"type": "string"},
          "description_hi": {"type": "string"},
          "price_inr": {"type": "integer"},
          "price_display": {"type": "string"},
          "mrp_display": {"type": ["string", "null"], "description": "Printed price, when the item sells below it."},
          "image_url": {"type": "string", "format": "uri"},
          "ai_background": {"type": "boolean", "description": "True when the background was generated. Show an AI background label wherever you show this photo."},
          "sold_out": {"type": "boolean"},
          "product_url": {"type": "string", "format": "uri"}
        }
      }
    }
  }
}
```

`feed_url` and `photos_url` point at `GET /api/v1/tools/catalog/feed.csv` and
`GET /api/v1/tools/catalog/photos.zip`, which serve the same files as the seller's catalog screen.

### 3.9 Upload endpoints (not tools)

The executor uses these; they are not in the tool list and the model never calls them. They reuse the
core resumable upload logic (`api/v1/uploads.py`): a piece must start exactly where the last one
ended, and a mismatch answers `409 offset_mismatch` with the right `offset`, so a retried piece is never
written twice.

| Call | Scope | Body | Answer |
|---|---|---|---|
| `GET /api/v1/tools/uploads/{id}` | `jobs:write` | none | `{id, status, offset, size_bytes, duration_s, job_id, job_status}` |
| `PATCH /api/v1/tools/uploads/{id}` | `jobs:write` | raw bytes, at most 8 MB, `Content-Type: application/octet-stream`, `Upload-Offset: <n>` | the same shape |

Both are signed (the body hash covers the piece). PATCH is not a POST, so it needs no
`Idempotency-Key`; `Upload-Offset` makes it safe to repeat. Upload `status` is `receiving`, `ready` or
`rejected`. When the last byte arrives, the file is checked as in the app (content sniffed, ffprobe);
if it passes, the job is created and `job_status` becomes `queued`. If it fails, the answer is `422`
with the media code (for example `too_long`) and the job becomes `failed` with that code.

"Pre-authorised" here means the slot is already created, sized, tied to this job and workspace and
time-limited. It does not carry its own credential: each piece is signed with the workspace key. Tool
results go into the model's context and transcripts, and a URL that worked on its own would leak
through them.

A key can also revoke itself, for example after a suspected leak: `DELETE /api/v1/tools/key` (signed,
any scope). The answer is `204`, and the key stops working at once.

## 4. Authentication, signing and idempotency

### 4.1 API keys

Format: `sts_<env>_<prefix>.<secret>`

- `<env>` is `live` (demo and production) or `test` (dev and test). A key only works in its own
  environment.
- `<prefix>` is 8 random characters from `a-z0-9`. It is the key's public id: shown in the app, in the
  CLI and in logs.
- `<secret>` is 32 random bytes, base64url without padding (43 characters).

The format matches the existing gitleaks rule `shelf-to-shop-api-key` (`.gitleaks.toml`) and the log
scrubber (`core/logging.py`), so a leaked key is caught before commit and redacted from logs.

Storage (`sp_api_keys`): `workspace_id`, `name`, `prefix` (unique), `secret_hmac`, `scopes`,
`created_at`, `created_by`, `last_used_at`, `revoked_at`. `secret_hmac` is
`HMAC-SHA256(API_KEY_PEPPER, secret)` in hex. The raw secret is shown once at creation and never
stored. A slow hash such as argon2 adds nothing for a 256-bit random secret; the pepper means a copy of
the database alone cannot even test guesses.

Scopes:

| Scope | Allows |
|---|---|
| `jobs:write` | `create_catalog_job`, `resolve_flag`, upload endpoints |
| `jobs:read` | `get_job_status`, `list_flags` |
| `catalog:read` | `get_catalog`, feed and photo downloads |

The manifest and self-revoke need any valid key. No scope allows publishing; there is no such route
for keys.

- **Revocation**: `admin revoke-key --prefix <prefix>`, `DELETE /api/v1/tools/key`, or (once seller
  sign-in exists) Settings, "Connected apps". It takes effect on the next request. It also revokes the
  review links that key created. Webhooks and sink pushes for a workspace stop when it has no active key.
- **last_used_at**: updated at most once a minute per key, so a busy key does not write on every call.
- **Rotating a key**: create a second key, switch the executor to it, revoke the first. Keys are
  independent, so there is no gap.
- **Rotating the pepper**: set the new pepper in `API_KEY_PEPPER` and the old one in
  `API_KEY_PEPPER_PREVIOUS`. A key that matches only the old pepper is accepted and re-hashed with the
  new one. Remove the old pepper once `last_used_at` shows every active key has been used since.
- **Audit**: `api_key.created`, `api_key.revoked` with the prefix and actor, never the secret.

### 4.2 Request signing

Every call to `/api/v1/tools/*`, GET included, carries these headers:

| Header | Value |
|---|---|
| `Authorization` | `Bearer sts_<env>_<prefix>.<secret>` |
| `X-Shelf-Timestamp` | Unix time in seconds, decimal digits |
| `X-Shelf-Nonce` | 16 to 64 characters from `A-Za-z0-9_-`, new for every request, including retries. 32 hex characters from a secure random source is fine |
| `X-Shelf-Signature` | `v1=` followed by the lowercase hex HMAC-SHA256 below |
| `Idempotency-Key` | on every POST (section 4.4) |

The canonical string is five lines joined by a single `\n`, with no newline at the end:

```
<X-Shelf-Timestamp>
<X-Shelf-Nonce>
<HTTP method, upper case>
<request path, with ?query if there is one, exactly as sent>
<lowercase hex SHA-256 of the exact body bytes>
```

- The path starts at `/api/v1/`. No scheme, host or port. No re-encoding or sorting of the query.
- For an empty body (GET, DELETE) the hash is
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
- The HMAC key is the `<secret>` part of the API key (the text after the first `.`), as ASCII bytes.

Signature = `HMAC-SHA256(secret, canonical string)`, sent as `X-Shelf-Signature: v1=<hex>`.

The secret travels in `Authorization` (over TLS) because the server keeps only a peppered hash of it
and so needs the presented secret to check the HMAC. The signature adds three things a bare bearer key
does not: the body, method and path cannot be changed in transit or by a proxy; a captured request
cannot be replayed (nonce) or used later (timestamp); and a request that a proxy logged without its
`Authorization` header is useless to whoever reads the log.

### 4.3 What the server checks, in order

1. Body size: 64 KB for tool JSON, 8 MB for upload pieces. Over it: `413 too_large`.
2. `Authorization` parses as `Bearer sts_<env>_<prefix>.<secret>` for this environment. Look up the
   prefix and compare `HMAC-SHA256(pepper, secret)` with `hmac.compare_digest`. An unknown prefix runs
   the same HMAC so timing does not reveal which prefixes exist. Either failure: `401 api_key_invalid`.
3. Revoked: `401 api_key_revoked` (only said after the secret matched).
4. All three signing headers present and well formed, or `401 signature_missing`.
5. `|server time - X-Shelf-Timestamp| <= 300` seconds, or `401 signature_expired` (the body includes
   `server_time` to help find clock drift).
6. Signature matches (constant-time compare), or `401 signature_invalid`.
7. Store the nonce: insert `(api_key_id, nonce, expires_at = timestamp + 600)` into
   `sp_request_nonces`, which has a unique index on `(api_key_id, nonce)`. A conflict means
   `401 nonce_reused`. Nonces are stored only after the signature checks out, so unsigned junk cannot
   fill the table. Rows are removed after 10 minutes. The table is in the database, so this holds with
   several API processes and on Postgres.
8. Scope, or `403 scope_missing` with `required_scope`.
9. Rate limits, or `429 too_many` with `Retry-After`.
10. `Idempotency-Key` (POST only), section 4.4.
11. The tool runs. Every query filters on the key's `workspace_id`; another workspace's job, flag or
    upload answers `404 not_found`, exactly like an id that does not exist.

Tool routes ignore cookies. Cookie routes refuse `Authorization: Bearer sts_...`. So a key never acts
as a seller session, and a seller's browser never acts as a key.

### 4.4 Idempotency-Key

Required on every POST under `/api/v1/tools/` (missing: `400 idempotency_key_missing`). 8 to 128
characters from `A-Za-z0-9_-`; a random UUID or 32 hex characters is fine. Keys are scoped to the API
key that sent them and kept for 24 hours (`sp_idempotency`).

The request fingerprint is the SHA-256 of method, path and the body hash from the signature.

| Situation | Answer |
|---|---|
| New key | The request runs. A `2xx` response (status and body) is stored |
| Same key, same fingerprint, first request finished with `2xx` | The stored response, with `Idempotent-Replayed: true` |
| Same key, same fingerprint, first request still running | `409 idempotency_in_progress` with `Retry-After: 1` |
| Same key, different fingerprint | `409 idempotency_key_reused` |
| First request ended in an error | Nothing was stored, and the request changed nothing (every tool runs in one transaction), so the same key can be sent again and runs again |

Read tools (`get_job_status`, `list_flags`, `get_catalog`) follow the same rules, with one difference:
only the fingerprint is stored, and a replay is answered with freshly read data. Reads have no side
effects, a stored status would be stale, and a stored status could hold a review link at rest.

A new signature and nonce are still needed on every retry; idempotency is about the request body, not
the signature.

### 4.5 Limits

| Limit | Value |
|---|---|
| Tool calls per key | 120 per minute (`TOOLS_RATE_PER_KEY_PER_MIN`) |
| Upload pieces per key | 120 per minute |
| New jobs per shop | 30 per hour (the core `UPLOAD_PER_SELLER` limit, shared with the app) |
| All tool routes per IP address | 600 per minute |
| Opening a review link, per IP address | 20 per 10 minutes (same as sign-in) |

The rate limiter is in memory in one API process (`core/ratelimit.py`), right for the current single
server. With several API processes it moves to the database or Redis, as `docs/security.md` notes.

## 5. Webhooks

### 5.1 Events

Shelf-to-Shop sends `job.*` events for jobs created through the tool API, and `catalog.published` for
every new catalog version of a workspace that has an active key. Every event goes to
`SOCIALPULSE_WEBHOOK_URL`.

Envelope:

```json
{
  "id": "evt_0192f3c4-0000-7000-8000-000000000001",
  "type": "job.needs_review",
  "api_version": "v1",
  "created_at": "2026-11-01T10:04:12Z",
  "workspace_id": "0192f3c4-1111-7000-8000-00000000000a",
  "data": {}
}
```

`data` by type:

| Type | When | `data` |
|---|---|---|
| `job.needs_review` | The pipeline finished; the seller must review and publish | `{"job_id", "client_ref", "status": "needs_review", "products_found", "open_flags"}` |
| `job.completed` | The seller published this job's items | `{"job_id", "client_ref", "status": "published", "catalog_version", "items_from_job", "page_url"}` |
| `job.failed` | The job stopped (pipeline error, cap, or the upload was rejected or expired) | `{"job_id", "client_ref", "status": "failed", "error": {"code", "message", "next_step"}}` |
| `catalog.published` | Any new shop version: from a job, or from a later change such as the seller editing items | `{"catalog_version", "published_at", "page_url", "items", "feed_available", "feed_left_out", "job_id"}` (`job_id` is null when no job made the version) |

When the seller publishes a job, `job.completed` and `catalog.published` come from the same
transaction.

Webhooks never carry the review link. Call `get_job_status` for it, so the link never sits in the
delivery log. Payloads carry ids, counts, error codes and public page URLs only: no item text, no
personal data.

### 5.2 Headers and signature

| Header | Value |
|---|---|
| `Content-Type` | `application/json` |
| `User-Agent` | `ShelfToShop-Webhooks/1` |
| `X-Shelf-Event` | the event type |
| `X-Shelf-Delivery` | the event `id`; the same on every retry, so use it to drop duplicates |
| `X-Shelf-Signature` | `t=<unix seconds>,v1=<hex>` and, during a secret rotation, a second `,v1=<hex>` |

`v1 = lowercase hex HMAC-SHA256(webhook secret, "<t>.<raw body bytes>")`. `t` is the time of this
attempt; every retry is signed again, so a receiver can refuse anything more than 5 minutes old.
Verify against the raw bytes received, before parsing JSON (section 10).

### 5.3 Delivery and retries

- A delivery succeeds on any `2xx` within 10 seconds. Anything else, including a redirect (redirects are
  not followed) or a timeout, is a failure.
- After a failure, the next attempt waits 1 minute, then 5 minutes, 30 minutes, 2 hours, 6 hours and 12
  hours, each with plus or minus 20% jitter. That is 7 attempts over about 21 hours. After the last one,
  the delivery is marked `failed`.
- Deliveries run as tasks on the core's database-backed queue (`shelf/jobs/queue.py`). The delivery
  row is written in the same transaction as the event, so a crash cannot lose it.
- Order is not guaranteed. Use `created_at`, and treat `get_job_status` as the truth.
- Outbound requests go through `AllowlistTransport` (`engine/net.py`: https only, the configured host
  only, no redirects). Before each attempt the host's addresses are resolved and refused if any is
  private, loopback, link-local or a cloud metadata address, and the connection uses the checked address.

Delivery log (`sp_webhook_deliveries`, kept 30 days): `event_id`, `type`, `workspace_id`, `payload`,
`attempt`, `status` (`pending`, `delivered`, `failed`), `next_attempt_at`, `last_status_code`,
`last_latency_ms`, `last_error` (short, scrubbed), `created_at`, `delivered_at`. The operator reads it
with `admin deliveries --since 24h [--status failed]` and sends one again with
`admin redeliver <event-id>` (same id and payload, new signature).

### 5.4 Rotating the webhook secret

1. Generate a new secret: `openssl rand -base64 48`.
2. Operator: set `SOCIALPULSE_WEBHOOK_SECRET` to the new secret, `SOCIALPULSE_WEBHOOK_SECRET_PREVIOUS`
   to the old one, and `SOCIALPULSE_WEBHOOK_SECRET_PREVIOUS_UNTIL` to 24 hours from now. Restart the
   API and worker. Every delivery now carries two signatures: new secret first, old second.
3. SocialPulse adds the new secret to its accepted list. Steps 2 and 3 can happen in either order,
   because the verifier accepts any `v1` that matches any secret it holds.
4. After the overlap, SocialPulse drops the old secret and the operator removes the two `PREVIOUS`
   variables.

## 6. The review link

Publishing always needs the seller. The review link takes the seller straight to the review screen
for one job, without a full sign-in.

**Format**: `https://shop.example.com/review#rl1.<jti>.<exp>.<sig>`

| Part | Content |
|---|---|
| `rl1` | Format version |
| `<jti>` | 16 random bytes, base64url (22 characters). Primary key of the `review_links` row |
| `<exp>` | Expiry, Unix seconds |
| `<sig>` | base64url of `HMAC-SHA256(K_link, "rl1.<jti>.<exp>")`, where `K_link = HMAC-SHA256(SECRET_KEY, "shelf-to-shop/links/v1")` |

The link holds no workspace id, job id, shop name or personal data. The token sits after `#`, so
browsers do not send it to the server with the page request, it is not in access logs and it never
appears in a `Referer` header.

**Stored** (`review_links`): `jti`, `purpose` (`review` or `setup`), `workspace_id`, `job_id`,
`created_by` (the key prefix), `expires_at`, `revoked_at`, `revoke_reason`, `open_count`,
`last_opened_at`. The token itself is not stored. Because it is built from `jti` and `exp`, the server
can rebuild the same link, so `get_job_status` returns the same URL on every call while the link is
valid.

**Lifetime**: `REVIEW_LINK_TTL_HOURS`, default 24. `get_job_status` mints a link the first time it sees
the job in `needs_review`, returns it while more than an hour is left, and then mints a new one. An
older link keeps working until its own expiry.

**Opening**: the web app's `/review` route reads the fragment, sends it to
`POST /api/v1/links/open` in the body, and removes it from the address bar with
`history.replaceState`. The server checks the signature (constant time), then the row: it exists, has
not expired and is not revoked, its job belongs to its workspace and is `needs_review`. If all hold, it
sets a review session cookie (`sts_review`: HttpOnly, Secure, SameSite=Lax, ends with the link) and
returns a CSRF token, as a seller sign-in does. Each open writes an audit event `link.opened`.

**What a review session can do**: only the review screen's calls for that one job: read the job,
items and questions; item photos and the photo tools for items in that job; edit those items; answer
questions; read the run details; publish that job. Everything else answers `401 signed_out`:
settings, other jobs, the items list, orders, export, delete, keys. The seller still has to answer the
open questions (`409 questions_open`) and the shop needs a WhatsApp number (`409 whatsapp_missing`),
as in the app.

**Publishing through the link** is the same `POST /api/v1/jobs/{id}/publish` the app uses. The catalog
version records the workspace owner as `approved_by`; the audit event `catalog.published` records
`via: review_link` and the link's `jti`.

**Revocation**: a link stops working when the job is published (or otherwise leaves `needs_review`),
when the key that minted it is revoked, when the shop is deleted, or when the operator runs
`admin revoke-link --job <job-id>`. Revoking a link also ends the review sessions opened from it.
Errors in the seller's browser: `401 link_invalid`, `410 link_expired`, `410 link_revoked`; the page
says what happened ("This link has expired. Ask for a new one in SocialPulse.").

**Forwarding**: whoever holds the link can publish that one job until it expires. Phoenix must show it
only to the seller, in their own conversation. The review screen shows the shop name at the top, so a
wrong recipient sees at once that it is not their shop.

The setup link in section 2.3 uses the same format and checks with `purpose: setup`. It reaches only the
notices and the shop name and WhatsApp number, and works once.

## 7. Sinks

A sink receives a copy of each approved catalog version. It runs after the publish has committed, from
a task on the durable queue, so a slow or failing sink never blocks or undoes a publish.

```python
class ApprovedCatalog(BaseModel):
    """Only what the public shop page already shows."""

    workspace_id: uuid.UUID
    shop_slug: str
    version: int
    published_at: datetime
    page_url: str
    products: list[PublicProduct]  # the published snapshot entries (catalog/publish.py)
    feed_csv: str | None  # the Meta feed text; None when no item passed Meta's rules
    job_id: uuid.UUID | None  # None for versions made by editing items


class SinkResult(BaseModel):
    ok: bool
    retryable: bool
    detail: str | None = None  # short, no personal data


class Sink(Protocol):
    name: str

    async def push(self, catalog: ApprovedCatalog) -> SinkResult: ...
```

- **`LocalSink`** (`src/shelf/sinks/local.py`, default, always on). Publishing already writes the
  version to storage under `public/<slug>/v<version>/` (page data, feed CSV, photo zip, images).
  `LocalSink` checks that the folder is complete and reports `ok`. It makes no network calls.
- **`SocialPulseSink`** (`src/integrations/socialpulse/sink.py`). Enabled when `SOCIALPULSE_SINK_URL`
  is set. It sends `POST <SOCIALPULSE_SINK_URL>` with the `ApprovedCatalog` as JSON, and the headers
  `Authorization: Bearer <SOCIALPULSE_SINK_KEY>` and
  `Idempotency-Key: catalog-<workspace_id>-v<version>`, so a retry is recognised. It goes through
  `AllowlistTransport` with only that host allowed (https, no redirects, 10-second timeout), plus the
  same address check as webhooks. `2xx` is success; `408`, `429`, `5xx` and timeouts are retried on the
  webhook schedule; any other `4xx` is not retried and is logged for the operator. It knows a URL, a
  key and this payload, and nothing else about SocialPulse.

The plugin registers its sink at start-up (`register_sink`). On `catalog.published`, one `sink.push`
task per extra sink is queued in the publish transaction, only for workspaces with an active key. Push
results are kept in `sp_sink_pushes` for 30 days.

The webhook and the sink differ in purpose: `catalog.published` says a new version exists; the sink
delivers its contents for SocialPulse to store. Use either or both.

## 8. Error codes

Every error is `application/problem+json` (`core/errors.py`):

```json
{
  "type": "https://shelf-to-shop.dev/errors/scope_missing",
  "title": "This key cannot do that.",
  "status": 403,
  "code": "scope_missing",
  "request_id": "6f1d0c2e9a4b4f7d",
  "required_scope": "jobs:write"
}
```

Match on `code`, never on `title`. Every response, error or not, carries `X-Request-ID`; quote it when
reporting a problem. Codes marked "core" already exist in the API.

Authentication and transport:

| Code | HTTP | Meaning and what to do |
|---|---|---|
| `api_key_invalid` | 401 | Missing, malformed, unknown or wrong key, or a key for the other environment |
| `api_key_revoked` | 401 | The key was revoked. Ask the operator for a new one |
| `signature_missing` | 401 | A signing header is missing or malformed |
| `signature_expired` | 401 | Timestamp more than 300 seconds from `server_time`. Fix the clock (NTP) |
| `signature_invalid` | 401 | Check the canonical string: path with query, exact body bytes, secret after the first `.` |
| `nonce_reused` | 401 | Nonce seen in the last 10 minutes for this key. Use a new nonce on every request |
| `scope_missing` | 403 | The key lacks `required_scope` |
| `idempotency_key_missing` | 400 | POST without `Idempotency-Key` |
| `idempotency_key_reused` | 409 | Same `Idempotency-Key`, different request |
| `idempotency_in_progress` | 409 | The first request with this key is still running. Retry after `Retry-After` |
| `too_many` (core) | 429 | Rate limit. Wait `Retry-After` seconds |
| `too_large` (core) | 413 | Body over its limit, or an upload larger than declared or than 200 MB |
| `validation_failed` (core) | 422 | `errors` lists the fields and why (submitted values are never echoed) |
| `not_found` (core) | 404 | No such job, flag or upload in this workspace (other workspaces' ids answer the same) |
| `internal_error` (core) | 500 | Retry later; quote `request_id` |

Jobs and uploads:

| Code | HTTP | Meaning and what to do |
|---|---|---|
| `consent_required` (core) | 403 | The seller has not agreed to the recording notice. The seller must open their setup link |
| `not_ready` (core) | 409 | `upload_id` has not finished uploading |
| `upload_in_use` | 409 | That upload already backs a job that has not failed |
| `pick_part` (core) | 422 | Video over 75 seconds: send `start_s` |
| `bad_offset` (core) | 400 | `Upload-Offset` missing or not a number |
| `offset_mismatch` (core) | 409 | Carry on from the `offset` in the body |
| `upload_expired` | 410 | The upload slot is over 24 hours old and its data is deleted. Start again |
| `checksum_mismatch` | 422 | The bytes received do not match the declared `sha256` |
| `not_a_video`, `unreadable`, `no_video_stream`, `too_short`, `too_long`, `bad_resolution` (core) | 422 | The finished file failed the checks. The job fails with the same code |

Questions:

| Code | HTTP | Meaning and what to do |
|---|---|---|
| `not_in_review` | 409 | The job is not `needs_review` |
| `flag_closed` | 409 | Already answered, in the review screen or by an earlier call. Read `list_flags` again |
| `action_not_allowed` | 422 | Not one of the flag's `allowed_actions` (listed in the body) |
| `pick_item` (core) | 422 | `product_idx` missing, or not one of the flag's candidates |
| `price_required` (core) | 422 | `set_price` without `price_inr` |

Catalog downloads:

| Code | HTTP | Meaning and what to do |
|---|---|---|
| `not_published` (core) | 404 | Nothing published yet (`get_catalog` answers `published: false` instead) |
| `no_feed` (core) | 404 | No item passed Meta's feed rules |

In the seller's browser (review link), for completeness:

| Code | HTTP | Meaning |
|---|---|---|
| `link_invalid` | 401 | Bad signature or unknown link |
| `link_expired` | 410 | Ask Phoenix for a new link (`get_job_status` mints one) |
| `link_revoked` | 410 | Already published, the key was revoked, or the operator revoked it |
| `signed_out`, `csrf_failed` (core) | 401, 403 | The review session ended, or the page is stale |
| `questions_open`, `whatsapp_missing`, `nothing_to_publish` (core) | 409, 409, 422 | Publish is blocked; the screen says what to fix |

Job failure codes (in `error.code` and `job.failed`, not HTTP statuses): the core's `spend_cap`,
`daily_cap`, `service_daily_cap`, `model_unavailable`, `internal` and `video_deleted`
(`jobs/service.py`), the media codes above, and `upload_expired`, `checksum_mismatch`, `pick_part`.

## 9. Worked example

Shell placeholders: replace `shop.example.com` with your Shelf-to-Shop host and keep the key in an
environment variable from your secret store. The helper below signs with `openssl` and is for trying
things out; production executors sign in code (section 10.3). It passes the secret on the command line,
which other users of the same machine can see. It uses GNU `sha256sum` and `split` (Linux, Git Bash);
on macOS use `shasum -a 256` and `gsplit`.

```bash
API_HOST=https://shop.example.com
KEY="$SHELF_API_KEY"          # sts_live_<prefix>.<secret>

# shelf METHOD PATH BODY_FILE [extra curl arguments...]   (use /dev/null for no body)
shelf() {
  local method=$1 path=$2 body=$3 ts nonce body_hash sig
  shift 3
  ts=$(date +%s)
  nonce=$(openssl rand -hex 16)
  body_hash=$(sha256sum "$body" | cut -d' ' -f1)
  sig=$(printf '%s\n%s\n%s\n%s\n%s' "$ts" "$nonce" "$method" "$path" "$body_hash" \
    | openssl dgst -sha256 -hmac "${KEY#*.}" | sed 's/^.*= //')
  if [ "$body" != /dev/null ]; then set -- --data-binary "@$body" "$@"; fi
  curl -sS -X "$method" "$API_HOST$path" \
    -H "Authorization: Bearer $KEY" \
    -H "X-Shelf-Timestamp: $ts" -H "X-Shelf-Nonce: $nonce" \
    -H "X-Shelf-Signature: v1=$sig" "$@"
}
```

**1. Create the job** for a video the seller sent (`shelf.mp4`):

```bash
SIZE=$(wc -c < shelf.mp4 | tr -d ' ')
SHA=$(sha256sum shelf.mp4 | cut -d' ' -f1)
printf '{"client_ref":"conv-<your-conversation-id>","video":{"size_bytes":%s,"sha256":"%s"}}' \
  "$SIZE" "$SHA" > create.json
shelf POST /api/v1/tools/create_catalog_job create.json \
  -H "Content-Type: application/json" -H "Idempotency-Key: $(openssl rand -hex 16)"
```

```json
{
  "job_id": "0192f3c4-5b6a-7c8d-9e0f-1a2b3c4d5e6f",
  "client_ref": "conv-<your-conversation-id>",
  "status": "awaiting_upload",
  "upload": {
    "id": "0192f3c4-6c7d-7e8f-9a0b-1c2d3e4f5a6b",
    "url": "https://shop.example.com/api/v1/tools/uploads/0192f3c4-6c7d-7e8f-9a0b-1c2d3e4f5a6b",
    "offset": 0,
    "size_bytes": 18874368,
    "chunk_size": 4194304,
    "max_chunk_size": 8388608,
    "expires_at": "2026-11-02T10:00:00Z"
  }
}
```

**2. Upload** in 4 MB pieces. After a dropped connection, `GET` the upload to learn where to carry on.

```bash
UPLOAD=/api/v1/tools/uploads/0192f3c4-6c7d-7e8f-9a0b-1c2d3e4f5a6b
split -b 4194304 -d shelf.mp4 piece-
offset=0
for piece in piece-*; do
  shelf PATCH "$UPLOAD" "$piece" \
    -H "Content-Type: application/octet-stream" -H "Upload-Offset: $offset"
  offset=$(( offset + $(wc -c < "$piece") ))
done
```

The answer to the last piece:

```json
{
  "id": "0192f3c4-6c7d-7e8f-9a0b-1c2d3e4f5a6b",
  "status": "ready",
  "offset": 18874368,
  "size_bytes": 18874368,
  "duration_s": 48.2,
  "job_id": "0192f3c4-5b6a-7c8d-9e0f-1a2b3c4d5e6f",
  "job_status": "queued"
}
```

**3. Follow the job** (or wait for `job.needs_review`):

```bash
printf '{"job_id":"0192f3c4-5b6a-7c8d-9e0f-1a2b3c4d5e6f"}' > status.json
shelf POST /api/v1/tools/get_job_status status.json \
  -H "Content-Type: application/json" -H "Idempotency-Key: $(openssl rand -hex 16)"
```

```json
{
  "job_id": "0192f3c4-5b6a-7c8d-9e0f-1a2b3c4d5e6f",
  "client_ref": "conv-<your-conversation-id>",
  "status": "needs_review",
  "stages": {"ingest": "done", "detect": "done", "transcribe": "done", "segment": "done", "enrich": "done", "match": "done", "verify": "done", "backgrounds": "done"},
  "products_found": 12,
  "open_flags": 2,
  "error": null,
  "review_url": "https://shop.example.com/review#rl1.<jti>.<exp>.<sig>",
  "review_url_expires_at": "2026-11-02T10:06:00Z",
  "catalog_version": null,
  "page_url": null,
  "created_at": "2026-11-01T10:00:05Z",
  "updated_at": "2026-11-01T10:06:00Z"
}
```

**4. Optionally ask the questions in chat.** `list_flags` gives each question in English and Hindi
with its `allowed_actions`. When the seller answers ("neela wala 1200 hai"), pass it on:

```bash
printf '{"job_id":"0192f3c4-5b6a-7c8d-9e0f-1a2b3c4d5e6f","flag_id":"0192f3c4-7d8e-7f90-8a1b-2c3d4e5f6a7b","action":"set_price","price_inr":1200}' > answer.json
shelf POST /api/v1/tools/resolve_flag answer.json \
  -H "Content-Type: application/json" -H "Idempotency-Key: $(openssl rand -hex 16)"
```

**5. The seller approves.** Phoenix sends the seller `review_url`. The seller checks the items and
prices, answers any open questions and taps "Publish". Shelf-to-Shop sends `job.completed` and
`catalog.published`. Neither the executor nor the model takes part in this step.

**6. Read the catalog:**

```bash
printf '{"limit":2}' > catalog.json
shelf POST /api/v1/tools/get_catalog catalog.json \
  -H "Content-Type: application/json" -H "Idempotency-Key: $(openssl rand -hex 16)"
```

```json
{
  "published": true,
  "version": 4,
  "published_at": "2026-11-01T10:21:40Z",
  "page_url": "https://shop.example.com/s/<shop-slug>",
  "feed_url": "https://shop.example.com/api/v1/tools/catalog/feed.csv",
  "photos_url": "https://shop.example.com/api/v1/tools/catalog/photos.zip",
  "total_items": 38,
  "feed_left_out": 1,
  "products": [
    {
      "id": "<shop-slug>-9e0f1a2b",
      "title_en": "Blue cotton saree",
      "title_hi": "नीली सूती साड़ी",
      "description_en": "Blue cotton saree with a printed border.",
      "description_hi": "छपे बॉर्डर वाली नीली सूती साड़ी।",
      "price_inr": 1200,
      "price_display": "₹1,200",
      "mrp_display": null,
      "image_url": "https://shop.example.com/api/v1/public/media/<shop-slug>/v4/<shop-slug>-9e0f1a2b.jpg",
      "ai_background": true,
      "sold_out": false,
      "product_url": "https://shop.example.com/s/<shop-slug>/p/<shop-slug>-9e0f1a2b"
    }
  ]
}
```

The feed file needs a signed GET: `shelf GET /api/v1/tools/catalog/feed.csv /dev/null -o feed.csv`.

## 10. Verification code and test vectors

### 10.1 Webhook verifier, Python

```python
import hashlib
import hmac
import time

TOLERANCE_S = 300  # refuse deliveries signed more than 5 minutes from now


def verify_shelf_webhook(
    raw_body: bytes, header: str, secrets: list[str], now: float | None = None
) -> bool:
    """True if X-Shelf-Signature is fresh and matches one of `secrets`."""
    ts: int | None = None
    sigs: list[str] = []
    for part in header.split(","):
        key, sep, value = part.strip().partition("=")
        if not sep:
            continue
        if key == "t" and value.isascii() and value.isdigit():
            ts = int(value)
        elif key == "v1":
            sigs.append(value)
    if ts is None or not sigs:
        return False
    if abs((time.time() if now is None else now) - ts) > TOLERANCE_S:
        return False
    signed = str(ts).encode() + b"." + raw_body
    for secret in secrets:
        expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
        if any(hmac.compare_digest(expected, s) for s in sigs):
            return True
    return False
```

Call it with the raw request bytes (for example `await request.body()` in FastAPI) and all secrets you
currently accept. After it returns `True`, drop the delivery if you have already processed its
`X-Shelf-Delivery` id.

### 10.2 Webhook verifier, Node.js

```js
const crypto = require("node:crypto");

const TOLERANCE_S = 300; // refuse deliveries signed more than 5 minutes from now

// rawBody: the exact bytes received, as a Buffer (for example express.raw({ type: "application/json" })).
function verifyShelfWebhook(rawBody, header, secrets, nowS = Math.floor(Date.now() / 1000)) {
  let ts = null;
  const sigs = [];
  for (const part of String(header ?? "").split(",")) {
    const i = part.indexOf("=");
    if (i < 0) continue;
    const key = part.slice(0, i).trim();
    const value = part.slice(i + 1).trim();
    if (key === "t" && /^\d+$/.test(value)) ts = Number(value);
    else if (key === "v1") sigs.push(Buffer.from(value));
  }
  if (ts === null || sigs.length === 0 || Math.abs(nowS - ts) > TOLERANCE_S) return false;
  const signed = Buffer.concat([Buffer.from(`${ts}.`), rawBody]);
  for (const secret of secrets) {
    const expected = Buffer.from(crypto.createHmac("sha256", secret).update(signed).digest("hex"));
    for (const given of sigs) {
      if (given.length === expected.length && crypto.timingSafeEqual(given, expected)) return true;
    }
  }
  return false;
}

module.exports = { verifyShelfWebhook };
```

### 10.3 Request signer, Python (for the executor)

```python
import hashlib
import hmac
import secrets
import time


def shelf_headers(
    api_key: str, method: str, path: str, body: bytes, idempotency_key: str | None = None
) -> dict[str, str]:
    """Headers for one call. `path` is exactly what goes on the wire, with any ?query."""
    secret = api_key.split(".", 1)[1]
    ts = str(int(time.time()))
    nonce = secrets.token_hex(16)
    canonical = "\n".join([ts, nonce, method.upper(), path, hashlib.sha256(body).hexdigest()])
    signature = hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "X-Shelf-Timestamp": ts,
        "X-Shelf-Nonce": nonce,
        "X-Shelf-Signature": f"v1={signature}",
    }
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers
```

Send exactly the `body` bytes you hashed (serialise JSON once, then sign and send that string).

### 10.4 Test vectors

These secrets are made up for testing and are not keys. Both sides' test suites should include them.

Request signature:

| Input | Value |
|---|---|
| Secret (the part after the `.`) | `test-vector-secret-not-a-real-key` |
| Timestamp | `1793527200` (2026-11-01 10:00:00 UTC) |
| Nonce | `3f9a1c0e7b2d4e6f8a9b0c1d2e3f4a5b` |
| Method and path | `POST`, `/api/v1/tools/get_job_status` |
| Body (exact bytes) | `{"job_id":"0192f3c4-5b6a-7c8d-9e0f-1a2b3c4d5e6f"}` |
| Body SHA-256 | `9068f13bb1fc27212e36d9924dfc624a84fc3718967395c1554d62b771cd285c` |
| `X-Shelf-Signature` | `v1=17ce6a2c7d5a6f3cff9f321069f79bed677f736667282902275fc98e5e89179f` |

Webhook signature:

| Input | Value |
|---|---|
| Secret | `test-vector-webhook-secret-not-real` |
| `t` | `1793527260` |
| Body (exact bytes) | `{"id":"evt_0192f3c4-0000-7000-8000-000000000001","type":"job.needs_review"}` |
| `X-Shelf-Signature` | `t=1793527260,v1=4e558178a7012ff3e731687ad1d107669f1765c9c0ac502f2dff18689fb25e51` |

With these, the verifiers above must accept at `now = 1793527260 ± 300` and refuse at `± 301`, refuse
if one byte of the body changes, and accept when the header also carries a second, non-matching `v1`.

## 11. Security notes and implementation checklist

### 11.1 How this maps to the controls in `docs/security.md`

| Area | What this design adds | What it reuses |
|---|---|---|
| Access control (V8) | A key belongs to one workspace; every tool query filters on it; other workspaces' ids answer `404`. A review session sees one job | The `workspace_id` filters, the 404 rule and the isolation tests |
| Authentication (V6) | 256-bit key secrets, stored as HMAC-SHA256 with a pepper, constant-time compare, revocation, `last_used_at`; signed requests with a 5-minute window and a database nonce store | The session-token HMAC pattern (`auth/sessions.py`) |
| Sessions and CSRF (V3, V7) | Job-scoped review sessions: HttpOnly, Secure, SameSite=Lax cookie, double-submit CSRF, ending with the link. Tool routes ignore cookies; cookie routes refuse keys | `auth/sessions.py`, `current_seller` |
| Input validation (V2, V5) | Strict pydantic inputs (`extra="forbid"`), bounds, `client_ref` pattern, prices 1 to 1 crore | Models in `api/v1/*` |
| File uploads (V5) | The same checks: size limits, magic-byte sniff, ffprobe, ffmpeg limits, random storage keys; optional `sha256` | `engine/media/*`, `check_upload` |
| SSRF (V13) | No request ever makes the server fetch a URL. Webhook and sink hosts come only from configuration, go through the allowlist transport, and are refused if they resolve to private addresses | `engine/net.py` |
| Rate limits (V2) | Per key, per IP; new jobs share the shop's upload limit | `core/ratelimit.py` (in memory, one server) |
| Errors (V16) | The same problem+json; new stable codes (section 8) | `core/errors.py` |
| Logging and audit (V16) | Logs show the key prefix only. The scrubber also covers `X-Shelf-Signature` and `rl1.` tokens. Audit events: `api_key.created`, `api_key.revoked`, `link.minted`, `link.opened`, `link.revoked`, `flag.answered_via_api`, `catalog.published` with `via` | `core/logging.py`, `audit_events` |
| AI inputs (prompt injection) | No tool publishes, pays or messages. Tool outputs carry model-made text (titles, descriptions), which Phoenix must also treat as data | `engine/agents/structured.py` |
| Secrets (V13) | Pepper, webhook and sink secrets from the environment (Parameter Store in production); the existing gitleaks rule already matches the key format | `.gitleaks.toml`, `docs/runbook.md` |
| Privacy (DPDP) | Consent comes from the seller in Shelf-to-Shop's screens, never from Phoenix. Tools return no videos, frames, transcripts, evidence or costs. Deleting a shop deletes its keys, links, idempotency records and deliveries | `docs/privacy.md`, `privacy/retention.py` |

When this ships, `docs/privacy.md` needs SocialPulse in "Who else processes data" (it receives
catalog data and job status; sellers' videos come from it), and `docs/security.md` needs these rows.

### 11.2 Implementation checklist

| # | Work | Where | Effort |
|---|---|---|---|
| 1 | Core seams: events, `create_job(job_id=)`, shared upload-piece function, worker loads plugin task handlers, `Sink` protocol and `LocalSink`, `app_mode` in `/me` | `src/shelf` | 1 day |
| 2 | Signed links (review and setup), job-scoped review sessions on the review and photo routes, `/review` and setup screens, "Answered in SocialPulse" label, English and Hindi strings | `src/shelf`, `web` | 1.5 days |
| 3 | `sp_*` tables and an Alembic branch (`sp_api_keys`, `sp_request_nonces`, `sp_idempotency`, `sp_job_requests`, `sp_webhook_deliveries`, `sp_sink_pushes`); `review_links` in core | `integrations/socialpulse/models.py`, `migrations` | 0.5 day |
| 4 | Key check, request signatures, nonce store, scopes, per-key limits, self-revoke | `auth.py` | 1 day |
| 5 | Idempotency records | `idempotency.py` | 0.5 day |
| 6 | Five tools, manifest generated from the pydantic models, upload endpoints, feed and photo downloads, question rendering | `tools.py`, `uploads.py`, `questions.py` | 1.5 days |
| 7 | Webhooks: event handlers, delivery task with backoff, two-secret signing, delivery log | `webhooks.py` | 1 day |
| 8 | `SocialPulseSink` | `sink.py` | 0.5 day |
| 9 | Operator commands: `add-shop`, `create-key`, `list-keys`, `revoke-key`, `revoke-link`, `deliveries`, `redeliver` | `admin.py` | 0.5 day |
| 10 | Tests (below) | `tests/integrations/` | 1.5 days |
| 11 | Docs: security, privacy and runbook entries (rotate pepper and webhook secret, leaked key), this file's status line | `docs/` | 0.5 day |
| | **Total** | | **about 10 days** |

Tests to write:

- Isolation: every tool and upload call with another workspace's ids answers `404`.
- Scopes: each tool refuses a key without its scope.
- Signatures: the vectors in section 10.4; timestamp at ±300 accepted and ±301 refused; reused nonce
  refused; changed body, path or method refused; revoked key refused.
- Idempotency: replay, different body, in-flight request, error then retry.
- Boundaries: no route reachable with a key publishes or changes a published job (checked over the
  route table); keys refused on cookie routes and cookies ignored on tool routes.
- Review links: forged, expired, revoked, other job, other workspace; a review session refused outside
  its job; publish through a review session; link revoked after publish.
- Webhooks: two-signature rotation, retry schedule with a fake clock, no review link in any payload.
- Sink and webhooks refuse hosts outside the allowlist and private addresses.
- Manifest: every real tool response validates against its output schema.
- Question strings stay in step with `web/src/locales`.

### 11.3 Open questions for SocialPulse

1. Confirm the upload model: Shelf-to-Shop returns an upload slot and the executor sends the bytes;
   Shelf-to-Shop never fetches a URL.
2. Confirm one webhook endpoint for all sellers (events carry `workspace_id` and `client_ref`), rather
   than one per seller.
3. Confirm how Phoenix shows the review and setup links to the seller (chat message, button), and that
   they are never logged on the SocialPulse side.
4. Does SocialPulse want the sink push, the `catalog.published` webhook, or both?
