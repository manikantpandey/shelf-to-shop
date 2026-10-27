"""Spike 0: confirm the Meta and Baseten keys work with the documented endpoints and model ids.

Run: uv run python spikes/00_auth_check.py
Prints status, latency, echoed model, token usage and rate-limit headers. Never prints keys.
"""

from __future__ import annotations

import os

import httpx

from _common import (
    OUT,
    PRICE_SPARK_INPUT_PER_M,
    PRICE_SPARK_OUTPUT_PER_M,
    Timer,
    describe_error,
    load_env,
    meta_base_url,
    meta_headers,
    model_id,
    write_json,
)

PROMPT = "Reply with the single word OK."


def check_meta() -> dict[str, object]:
    model = model_id("META_VISION_MODEL", "muse-spark-1.3")
    with Timer() as t:
        r = httpx.post(
            f"{meta_base_url()}/responses",
            headers=meta_headers(),
            json={"model": model, "input": PROMPT},
            timeout=60,
        )
    result: dict[str, object] = {"provider": "meta", "model": model, "latency_ms": t.ms}
    if r.status_code != 200:
        result["error"] = describe_error(r)
        return result
    body = r.json()
    text = "".join(
        part.get("text", "")
        for item in body.get("output", [])
        if item.get("type") == "message"
        for part in item.get("content", [])
        if part.get("type") == "output_text"
    )
    usage = body.get("usage", {})
    cost = (
        usage.get("input_tokens", 0) * PRICE_SPARK_INPUT_PER_M
        + usage.get("output_tokens", 0) * PRICE_SPARK_OUTPUT_PER_M
    ) / 1_000_000
    result.update(
        status=body.get("status"),
        echoed_model=body.get("model"),
        output_text=text[:60],
        usage=usage,
        cost_usd=round(cost, 6),
        rate_limit_headers={k: v for k, v in r.headers.items() if k.startswith("x-ratelimit")},
    )
    return result


def check_baseten() -> dict[str, object]:
    key = os.environ.get("BASETEN_API_KEY", "")
    model = os.environ.get("BASETEN_MODEL_ID", "meta-models/muse-spark-open")
    if not key:
        return {"provider": "baseten", "model": model, "skipped": "BASETEN_API_KEY not set"}
    base = os.environ.get("BASETEN_BASE_URL", "https://inference.baseten.co/v1")
    with Timer() as t:
        r = httpx.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": PROMPT}],
                "max_tokens": 512,
            },
            timeout=90,
        )
    result: dict[str, object] = {"provider": "baseten", "model": model, "latency_ms": t.ms}
    if r.status_code != 200:
        result["error"] = describe_error(r)
        return result
    body = r.json()
    choice = (body.get("choices") or [{}])[0]
    result.update(
        echoed_model=body.get("model"),
        output_text=(choice.get("message", {}).get("content") or "")[:60],
        finish_reason=choice.get("finish_reason"),
        usage=body.get("usage"),
    )
    return result


def main() -> None:
    load_env()
    results = [check_meta(), check_baseten()]
    for res in results:
        print(res)
    write_json(OUT / "00_auth_check.json", results)


if __name__ == "__main__":
    main()
