# Progress

Updated at the end of every session. Newest session first.

## Build order (approved Oct 27; demo first, hardening second; code freeze Nov 4, 4 PM IST)
| Day | Date | Focus |
|---|---|---|
| 1 | Oct 27 | Repo setup + hooks, spikes 4 and 5, Meta/Baseten auth check |
| 2 | Oct 28 | Spikes 1, 1b, 2, 3 on the seller clips → report, **wait for go-ahead**. Meanwhile backend skeleton, provider base, fakes, price parser, ffmpeg ingest |
| 3 | Oct 29 | Pipeline end-to-end from a CLI (video → products JSON → feed CSV + images); test-upload a real feed to Commerce Manager |
| 4 | Oct 30 | Web vertical slice (flag-gated demo login, simple upload, processing, review + flags, publish, public shop page with wa.me); HTTPS deploy |
| 5 | Oct 31 | Hardening: email-code auth, refresh rotation, CSRF, isolation tests, resumable uploads, headers, limits, audit log; demo login off in prod |
| 6 | Nov 1 | Real shop videos, fixes, backgrounds + provenance polish, recorder edge states |
| 7 | Nov 2 | Evals, privacy export/delete + retention sweeper, settings, 360×800 screenshots + critique |
| 8 | Nov 3 | CI security scans, Playwright e2e, docs; socialpulse plugin only if all core items are green |
| 9 | Nov 4 | README with eval table, final fixes, freeze 4 PM IST |

Working rules: small conventional commits, authored by the configured git user only, with no AI attribution
trailers (a commit-msg hook strips them). Push `main` at the end of each day after tests and a
full-history gitleaks scan pass; never force-push. Secrets only in `.env`. No parallel worktree agents
for engine/shelf/web code.

---

## Session 5: Oct 27 late (Day 4 web slice and deploy kit, pulled forward)

### Done
- Segment tries nearby frames when a cut-out is weak; your confirmed prices saved as eval labels for
  the three kirana clips (`evals/labels/real_kirana_{a,b,c}.json`).
- **Seller backend** (`src/shelf/api/v1/seller.py`): flag-gated demo sign-in, cookie sessions with
  double-submit CSRF, shop setup, recording consent, uploads (200 MB, magic-byte sniff, ffprobe), jobs
  on the DB queue running the engine `Pipeline`, review edits and flag answers (set price / dismiss /
  remove item), publish (needs a WhatsApp number and no open questions; versioned public folder),
  feed CSV and photo zip downloads, public shop and media endpoints with path guards. An intruder
  workspace gets 404 on every job, review, image and catalog endpoint (test).
- Feed problems now leave the item out of the feed only; the shop page still publishes and the
  Catalog screen says which items were left out.
- **Web app** (`web/`): sign in, shop setup, consent, recorder (rear camera, MP4/WebM pick, 60 s
  countdown, mic meter, torch, gallery fallback, permission / no-camera / insecure-context screens),
  processing, review with yellow price tags, catalog, settings, public shop page in English and Hindi.
  12 screenshots at 360×800 critiqued and fixed (`docs/screenshots/`).
- Playwright journey with fake providers: sign in → record → process → fix prices → publish → public
  page in en/hi with wa.me links and loaded photos. CI runs it, plus a web job and cfn-lint.
- **Deploy kit** (`deploy/`): CloudFormation (EC2 t3.medium in Mumbai, IMDSv2, encrypted disk, ports
  80/443 only, Session Manager instead of SSH, read access to `/shelf-to-shop/*` parameters only,
  Elastic IP), Docker images, Caddy (automatic HTTPS, CSP without unsafe-inline, HSTS, camera and
  mic for our origin only), prod and dev compose files, bootstrap and update scripts. Verified
  locally: images build, Caddyfile valid, cfn-lint clean, dev compose on Postgres ran the migrations
  and a fake job to review.
- `docs/runbook.md` (deploy, operate, rotate keys, incidents, teardown) and `make dev`.

### Broken / risks
- Not deployed yet: needs your AWS steps (runbook section 1).
- R2 not built: published photos are served by the API from the machine's disk (fine for the demo).
- Daily spend caps are not enforced across jobs yet (per-job cap only) until the DB spend ledger.
- Uploads are one request (not resumable) and the recording is not kept in IndexedDB; no recorder
  component tests yet; no rate limits; email-code sign-in has no sender (demo uses demo sign-in).
- Retention sweeper and data export/delete not built.
- Commerce Manager `link` domain question still open (test after deploy).

### Test results
- `make check`: ruff, mypy strict, import-linter 2/2, pytest **192 passed**.
- Web: vitest 7 passed, `tsc -b` clean, production build OK. Playwright journey **1 passed**.
- gitleaks full history (38 commits): no leaks. `claude.md` and `.env` untracked.

### Next 3 tasks
1. You deploy (runbook section 1); then I prepare the Commerce Manager feed test and click-path.
2. Day 5 hardening: rate and size limits, resumable chunked uploads + IndexedDB keep, refresh-token
   rotation, audit coverage, recorder component tests.
3. DB spend ledger for daily caps; R2 storage for published photos; retention sweeper.

### Needed from you
- AWS: create the Parameter Store secrets and the CloudFormation stack, then the GoDaddy `shop` record.
- Baseten key; spike 5 phone results; original-quality clips when you reshoot.

---

## Session 4: Oct 27 night (first real clips)

### Done
- Ran the full pipeline on your three kirana clips: **14/14 spoken prices right** (after fixing
  "बारह बारह" = 12 each), tag ₹5 vs spoken ₹4 flagged, brands read from packs. Write-up in
  `spikes/RESULTS.md` ("First real seller clips").
- Fixes: number repetition, prices re-read from cached transcripts (versioned parser), mask fragment
  cleanup, brand from the pack in the feed, 9 more verified Meta categories, readable CLI feed errors.
- Hosting decided: AWS EC2 (Mumbai) via CloudFormation you deploy + Cloudflare R2; DNS stays at
  GoDaddy (`shop.shankhyaai.com`); demo login only for the hackathon.

### Broken / risks
- Photos: 9/14 clean; wrong object on 1, fragmentary transparent bottle, 1 jar not segmented.
- WhatsApp-compressed video (478×850) makes soft product photos.
- Bundle prices ("2 for ₹8") are stored as a plain price.

### Test results
- `make check` green: pytest **181 passed**, mypy strict, import-linter 2/2, ruff.

### Next 3 tasks
1. Segment: try 2–3 frames per item and keep the best mask; add quantity ("2 for ₹8") to pairing.
2. Day 4 web slice + `demo` environment; jobs table and worker handler calling `Pipeline`.
3. `deploy/`: CloudFormation (EC2, EIP, SG, IAM role with SSM), Docker Compose, Caddy, R2 settings.

### Needed from you
- Confirm the ground-truth prices in `spikes/RESULTS.md`.
- Original (not WhatsApp-compressed) copies of the clips if possible.
- AWS + Cloudflare R2 setup (steps given in chat); Baseten key; spike 5 phone results.

---

## Session 3: Oct 27 evening (Day 3 pipeline pulled forward, on your go-ahead)

Decisions taken with you: build the pipeline now on the synthetic clip and re-check on real clips;
hosting = one India VPS (docker-compose + Caddy for HTTPS) with Cloudflare R2 for media; `claude.md`
stays local (now gitignored); clips, Baseten key and phone results promised tonight.

### Done
- **Pipeline end to end** (`src/engine/pipeline/`): ingest → detect ∥ transcribe → segment → enrich
  → match → verify → backgrounds, each stage cached by input hash (rerun resumes at the failed stage).
- **Meta providers** (`src/engine/providers/meta.py`): Muse Spark vision-only listing, then a
  separate pairing call keyed by on-screen time; whole-file ASR placed on the timeline by chunk ↔
  pause-span alignment; SAM point prompts inside the Spark box with concept fallback, buffered SSE,
  hole filling; Muse Image backdrop with a plain fallback. Fakes replay a labelled clip.
- **Matcher + verifier**: time window ±4 s, colour words (Hindi/English, from the product photo),
  direction words (agla/peeche), Spark's pairing as a second opinion; near-ties become questions.
  Flags: missing, conflict (tag / vision / multiple), ambiguous, implausible outlier, uncertain
  (bare "hazaar"), duplicate, weak mask.
- **Publish**: public catalog JSON (no internal fields), Meta feed CSV, photo zip, wa.me links.
- **CLI**: `uv run python -m shelf.cli process VIDEO --shop NAME --whatsapp NUMBER [--fake LABELS]`.
- Real run on synth_a: 4/5 spoken prices right, the 2 misheard ones asked as questions, tag conflict
  flagged, no silent wrong price; **$0.09 and 144 s per 32 s clip** (details in `spikes/RESULTS.md`).

### Broken / risks
- Detect is the slow stage (two Muse Spark video calls, ~77 s); segment ~40 s. Fine for a queue,
  but the processing screen must say "a few minutes".
- ASR quality on the TTS clip varies run to run; real seller speech still untested.
- Baseten text path not built (no key yet); all text steps use Muse Spark.
- Composite polish still pending (faint shadow, jagged one_bit edges).

### Test results
- `make check`: ruff, mypy strict (66 files), import-linter 2/2, **pytest 176 passed** (incl. an
  offline end-to-end pipeline run with real ffmpeg, cached reruns, resume after failure, spend cap).

### Next 3 tasks
1. Re-run spikes 1–3 and the CLI on your real clips (tonight), then tune thresholds.
2. Day 4 web vertical slice: demo login, upload, processing screen fed by `events.jsonl`, review with
   flag resolution, publish, public shop page; jobs table + worker handler calling `Pipeline`.
3. VPS deploy: docker-compose (api, worker, Postgres) + Caddy + R2; you'll need to create the VM and
   R2 bucket and give me SSH access or run the commands I prepare.

### Decided after the session (supersedes the DigitalOcean choice: it is not in the Student Pack)
- **Hosting: AWS + Cloudflare.** One EC2 VM in Mumbai (ap-south-1) running Docker Compose (API,
  worker, Postgres) and Caddy for HTTPS, created by a CloudFormation template that you deploy.
  Cloudflare R2 stores videos (private) and catalog photos. DNS stays at GoDaddy.
- **URL: https://shop.shankhyaai.com.** GoDaddy A record `shop` -> the EC2 Elastic IP. The Vercel site
  on `shankhyaai.com` / `www` is untouched. No CAA record exists, so Let's Encrypt can issue.
- **Login: demo login only for the hackathon.** The deployed environment will be `demo` (production
  security settings, demo login allowed, visible "Demo" banner). Email-code auth is still built and
  tested (Day 5); it gets a sender after Nov 4.
- **Feed test:** right after the deploy is up (Meta must fetch `link`/`image_link` from the domain);
  I prepare the CSV and a Commerce Manager click-path, you upload and paste back the result.

### Needed from you
1. AWS: an account/IAM user that can deploy CloudFormation in ap-south-1.
2. Cloudflare: an account with R2 enabled (R2 asks for a payment method even on the free tier).
3. GoDaddy: add the `shop` A record once the stack outputs its Elastic IP.

---

## Session 2: Oct 27 (Day 1 continued; Day 2 work pulled forward)

### Done
- Pushed `main` to github.com/manikantpandey/shelf-to-shop (agreed cadence: push at the end of each day
  after tests and a full-history gitleaks scan; never force-push).
- Backend skeleton (`src/shelf`): settings with production guards (no demo login / fake providers in
  prod, no contributor models), app factory, plugin loading by module path, request ids, JSON logs with
  a scrubber (keys, emails, Indian mobile numbers), problem+json errors that never echo input,
  SQLAlchemy base with UUIDv7 ids, Alembic env (batch mode), health/ready endpoints.
- Engine foundations (`src/engine`): typed provider errors per Meta's documented status codes; retries
  with full jitter honouring Retry-After (no retry on 4xx/504); circuit breaker; outbound host allowlist
  (https only); Meta client (Responses, streaming with failure events, Files with 1 h expiry, images,
  ASR); spend estimates from published prices with job/workspace-day/instance-day caps; run log;
  schema-strict structured calls with untrusted-data framing, `store: false` and one repair retry.
- Hinglish price parser (Roman + Devanagari words, digits, fractions, colloquial pairs) with property
  tests; INR formatting (Indian grouping, feed price `1200.00 INR`).
- Hardened ffmpeg ingest: magic-byte sniff, ffprobe rules, H.264/AAC normalisation (≤1280 px, ≤30 fps,
  GPS/metadata stripped), 24 kHz mono WAV, frames, RMS pause detection.
- Export: Meta feed CSV with a validator for every catalog-reference rule; `fb_product_category`
  mapping for our verticals verified against Meta's published taxonomy
  (`scripts/verify_fb_categories.py`, 24/24 match); wa.me order links.
- Compositing: product pixels copied last and asserted identical; contact shadow and the optional
  "AI background" corner mark only touch backdrop pixels; hole filling; 1024 px JPEG with XMP
  `DigitalSourceType = compositeSynthetic`, no EXIF.
- DB-backed task queue (`src/shelf/jobs`): leased claims via conditional UPDATE (one winner even on
  SQLite), lease takeover after a crash, jittered retries then dead, worker loop; first Alembic
  migration (tasks table, portable DDL).
- **Preliminary spikes 1, 1b, 2, 3 on a synthetic clip** (Muse Image products + Indian-English TTS at
  known times; `spikes/make_synthetic_clip.py`). Full write-up and the proposed pipeline are in
  `spikes/RESULTS.md`. Headlines: Muse Spark 6/6 items + tag read; one-call price pairing 5/6;
  SAM point prompts beat Spark boxes, video tracking swaps identities; whole-file transcript +
  pause-span chunk alignment times prices within 0.01 s; ~$0.08 per 32 s clip.
- `docs/design-plan.md` being written (docs agent), required before any UI code.

### Broken / risks
- Synthetic clip ≠ real seller speech: TTS mispronunciations caused 2/5 ASR price misses (one read as
  10,000). Real clips must confirm spikes 1–3; the verifier needs an outlier check.
- `meta-sam-parser` drops long video streams unless SSE events are buffered first (handled in spikes;
  the engine's segmenter must do the same).
- Composite polish (Day 6): the contact shadow is faint and one_bit mask edges look slightly jagged.
- Baseten still unverified (`BASETEN_API_KEY` empty).
- API spend so far: about $0.35 (all spikes, synthetic images, failed video attempts).

### Test results
- `make check`: ruff, mypy (strict, 52 files), import-linter (2 contracts kept), pytest **160 passed**
  in ~19 s (media tests use real ffmpeg on synthetic lavfi clips; queue tests include a 6-thread race).
- gitleaks full history: no leaks.

### Next 3 tasks
1. **Your go-ahead on the proposed pipeline** (`spikes/RESULTS.md`), then the Day 3 CLI end to end:
   provider implementations (detect, transcribe+align, segment, backdrop), stages with cache/resume,
   match_prices + verify, export.
2. Re-run spikes 1–3 on your two real clips the moment they are in `evals/videos/`.
3. Fake providers driven by a labelled clip (offline pipeline + e2e tests), wired to the queue worker.

### Open questions
1. Go-ahead on the pipeline design in `spikes/RESULTS.md`, or wait for real-clip spike results?
2. Hosting target for the Day 4 HTTPS deploy (needed by Oct 28).
3. Commerce Manager access before Oct 29.
4. `BASETEN_API_KEY`, the two clips, and the spike 5 phone results.
5. `claude.md` is untracked: commit the brief to the public repo, or keep it local?

---

## Session 1: Oct 27 (Day 1)

### Done
- Plan approved (repo structure, deps, data model, API, design plan, day order). Key decisions:
  DB-backed job queue; models `muse-spark-1.3`, `sam-3.1`, `muse-voice-transcribe-1.0`, `muse-image-1.0`
  (contributor variants refused by config); Baseten `meta-models/muse-spark-open` for optional text steps;
  transcription split on pauses (API gives turn-level timestamps only); backdrop generated + our own
  composite; AI corner-mark toggle default ON; C2PA deferred (needs a trust-list certificate).
- Tooling: GNU make 4.4.1 and gitleaks 8.30.1 via winget, uv 0.13.6.
- Repo: Apache-2.0 LICENSE + NOTICE, .gitignore/.gitattributes (LF everywhere), .editorconfig,
  .env.example, pre-commit (gitleaks with custom rules for `LLM_…` and `sts_…` keys, file hygiene, ruff,
  commit-msg trailer stripper `scripts/strip-ai-trailers.sh`), uv project skeleton (`src/engine`,
  `src/shelf`, `src/integrations`), smoke test, CI (gitleaks full history + ruff + pytest, actions pinned by
  SHA), Dependabot (uv, github-actions), Makefile.
- `meta-sam-parser==0.1.0` added as a dependency (SAM License, recorded in NOTICE): the docs don't specify
  the mask payload encoding, and that licence forbids reverse engineering, so no own decoder.
- Spike 0 (auth): Meta key works from India. Spike 4 (backgrounds): composite keeps product pixels
  byte-identical; Muse Image edits alone change 43% of them. Details in `spikes/RESULTS.md`.
- Spike 5 page + phone HTTPS how-to (`spikes/05_recorder/`), shooting guide (`spikes/SHOOTING.md`), label
  template (`evals/labels/_template.json`).

### Broken / risks
- Baseten not verified: `BASETEN_API_KEY` is empty in `.env`.
- SAM concept prompts match every similar item on a shelf; the pipeline must use box prompts from detection.
- SAM rasters for large objects are downscaled; they must be resized to the box (bug caught in spike 4).
- Muse Spark spends ~170 reasoning tokens even on trivial answers; check the reasoning-effort parameter.

### Test results
- `make check`: ruff lint + format clean; pytest 1 passed.
- pre-commit `--all-files`: all hooks pass. Commit-msg hook verified on a sample message (AI trailers removed,
  human co-author kept).

### Next 3 tasks
1. Spikes 1, 1b, 2, 3 on clips A and B (once in `evals/videos/`), write `spikes/RESULTS.md`, report, wait.
2. Backend skeleton: config (pydantic-settings, contributor-model guard), app factory, DB + Alembic,
   structlog JSON logging, problem+json errors.
3. Engine foundations: provider base (timeout, jittered retries honouring Retry-After, 504 → background
   mode, circuit breaker, cost), fakes, strict-schema transformer, Hinglish price parser + property tests,
   ffmpeg ingest (H.264/AAC 720p, 16 kHz WAV, silence split).

### Open questions
1. Hosting target for the Day 4 HTTPS deploy: please confirm by Oct 28.
2. Commerce Manager access before Oct 29 (tests whether the feed `link` may point at our hosted domain).
3. `BASETEN_API_KEY` for the Baseten check.
4. `claude.md` is untracked. Should the brief be committed to the public repo, or stay local only?
5. Spike 5 needs your Android phone; paste the "Copy results" JSON when done.
6. Later: confirm with SocialPulse that `create_catalog_job` returns an upload URL (we never fetch URLs),
   and the webhook event semantics.
