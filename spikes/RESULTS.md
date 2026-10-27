# Spike results

Raw outputs live in `spikes/out/` (gitignored). Prices are from dev.meta.ai/docs/pricing-rate-limits.md
(read 2026-10-27). Total spend on Day 1: about $0.06.

## Spike 0: auth check (2026-10-27)
- **Meta Model API works from India** with our key: `muse-spark-1.3` via `POST /v1/responses` returned
  `completed`, echoed the model id, and answered "OK" in 5.0 s.
- A one-word answer used 15 input / 182 output tokens, 172 of them reasoning. **Implication:** cheap text
  steps (enrich, repair retries) must request low reasoning effort, or cost and latency balloon. Check the
  exact parameter on Day 2.
- Rate-limit headers match the docs: `x-ratelimit-limit-requests: 3000`,
  `x-ratelimit-limit-tokens: 4000000`. The provider base class will read them.
- Baseten: **not run yet**, no `BASETEN_API_KEY` in `.env`.

## Spike 4: background replacement with pixel-exact product (2026-10-27)
Run: `make spike-4` (Muse Image generated a test shelf photo of a folded blue cotton saree among other fabrics).

| Step | Result | Latency | Cost |
|---|---|---|---|
| Muse Image test photo (`size: 1024x1024`) | returned **1600×1600** (size sets aspect ratio only, as documented) | 10.8 s | $0.01 |
| SAM 3.1 concept "saree", one_bit masks, confidence on | 9 objects (the target saree plus 8 neighbouring fabrics); target conf 0.84 | 14–16 s | $0.0025 |
| Muse Image backdrop (fixed prompt) | clean seamless grey sweep, 1600×1600 | 25–32 s | $0.01 |
| Composite (ours) | **masked pixels byte-identical: yes** (asserted) | <1 s | $0 |
| Control: `/images/edits` "replace only the background" | **not usable**: 43% of product pixels changed by >10 levels, 0.08% identical; it also kept the neighbouring fabrics | 18–23 s | $0.01 |

Findings:
1. **Muse Image cannot preserve product pixels** (also documented: no mask parameter). Compositing original
   masked pixels over a generated backdrop is the method, as planned.
2. **SAM mask rasters are downscaled for large objects**: a 1071×1060 box came back as a 1024×1013 raster
   (longest side capped at 1024). Rasters must be resized (nearest) to the box before placement; the first
   run placed it unscaled and misaligned the mask. The engine needs a test for this.
3. SAM mask quality on a folded saree is good: tight edges, folds and border kept. Stacked/folded textile
   edge cases still need the real clips (spike 2).
4. **Concept prompts are too broad for shelves** ("saree" matched every fabric). The pipeline should prompt
   SAM with **boxes** from Muse Spark's per-product detection, one object id per product.
5. Quality gaps to fix in the backgrounds stage, on backdrop pixels only: the product looks like it floats
   (add a soft contact shadow derived from the mask), and it needs framing (crop around the mask with
   padding, square, ≥500×500 for the Meta feed).
6. Latency: ~25–30 s per backdrop. Generate one backdrop per category per job and reuse it, in parallel with
   SAM, so it doesn't sit on the critical path.

## Spike 5: recorder on a real phone
Pending: needs your Android phone. Instructions: `spikes/05_recorder/README.md`; run `make spike-5`.

## Spikes 1, 1b, 2, 3
Pending: run on Day 2 (Oct 28) on your two clips (`spikes/SHOOTING.md`).
