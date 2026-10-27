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
trailers (a commit-msg hook strips them). Never push without asking. Secrets only in `.env`. No parallel
worktree agents for engine/shelf/web code.

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
