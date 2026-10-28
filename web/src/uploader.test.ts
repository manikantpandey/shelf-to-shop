import { describe, expect, it } from "vitest";

import { ApiError } from "./api";
import { resumableUpload } from "./uploader";

/** A tiny in-memory upload server that behaves like /api/v1/uploads. */
function server(opts: { chunk?: number; dropRequests?: number[]; loseReplies?: number[]; startAt?: number } = {}) {
  const state = { size: 0, offset: opts.startAt ?? 0, bytes: [] as number[], calls: 0, status: "receiving" };
  const chunk = opts.chunk ?? 10;
  const reply = (status: number, body: unknown) =>
    new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
  const fetchImpl = (async (url: string, init: RequestInit) => {
    state.calls += 1;
    const n = state.calls;
    if (opts.dropRequests?.includes(n)) throw new TypeError("network down");
    const method = init.method ?? "GET";
    if (method === "POST" && url.endsWith("/uploads/sessions")) {
      state.size = JSON.parse(String(init.body)).size;
      return reply(201, { id: "u1", status: "receiving", offset: 0, chunk_size: chunk, size_bytes: state.size });
    }
    if (method === "GET") {
      state.size = state.size || 40;
      return reply(200, { id: "u1", status: state.status, offset: state.offset });
    }
    const offset = Number((init.headers as Record<string, string>)["upload-offset"]);
    if (offset !== state.offset) return reply(409, { code: "offset_mismatch", offset: state.offset });
    const data = new Uint8Array(await (init.body as Blob).arrayBuffer());
    state.bytes.push(...data);
    state.offset += data.length;
    if (state.offset >= state.size) state.status = "ready";
    if (opts.loseReplies?.includes(n)) throw new TypeError("reply lost");
    return reply(200, { id: "u1", status: state.status, offset: state.offset, duration_s: 8, needs_clip: false, max_clip_s: 60 });
  }) as unknown as typeof fetch;
  return { state, fetchImpl };
}

const video = (n: number) => new Blob([new Uint8Array(Array.from({ length: n }, (_, i) => i % 251))]);

describe("resumable upload", () => {
  it("sends the video in pieces and reports progress", async () => {
    const { state, fetchImpl } = server();
    const seen: number[] = [];
    const done = await resumableUpload(video(35), { onProgress: (f) => seen.push(f), fetchImpl, backoff: [] });
    expect(done.status).toBe("ready");
    expect(state.bytes).toHaveLength(35);
    expect(seen.at(-1)).toBe(1);
  });

  it("retries a piece after the connection drops", async () => {
    const { state, fetchImpl } = server({ dropRequests: [3] });
    const done = await resumableUpload(video(30), { onProgress: () => undefined, fetchImpl, backoff: [0, 0] });
    expect(done.status).toBe("ready");
    expect(state.bytes).toHaveLength(30);
  });

  it("never writes a piece twice when the server got it but the reply was lost", async () => {
    const { state, fetchImpl } = server({ loseReplies: [2] });
    const done = await resumableUpload(video(30), { onProgress: () => undefined, fetchImpl, backoff: [0, 0] });
    expect(done.status).toBe("ready");
    expect(state.bytes).toEqual(Array.from({ length: 30 }, (_, i) => i % 251));
  });

  it("carries on with an upload saved on the phone", async () => {
    const { state, fetchImpl } = server({ startAt: 20 });
    state.bytes.push(...Array.from({ length: 20 }, (_, i) => i % 251));
    state.size = 40;
    const sessions: string[] = [];
    const done = await resumableUpload(video(40), {
      onProgress: () => undefined,
      fetchImpl,
      resumeId: "u1",
      onSession: (id) => sessions.push(id),
      backoff: [],
    });
    expect(done.status).toBe("ready");
    expect(sessions).toEqual([]); // no new session was started
    expect(state.bytes).toEqual(Array.from({ length: 40 }, (_, i) => i % 251));
  });

  it("gives up after the retries and says the connection is down", async () => {
    const { fetchImpl } = server({ dropRequests: [2, 3, 4] });
    await expect(
      resumableUpload(video(30), { onProgress: () => undefined, fetchImpl, backoff: [0, 0] }),
    ).rejects.toMatchObject({ code: "offline" });
  });

  it("passes on a refusal from the server", async () => {
    const fetchImpl = (async () =>
      new Response(JSON.stringify({ code: "too_many", title: "Too many tries" }), { status: 429 })) as unknown as typeof fetch;
    await expect(resumableUpload(video(10), { onProgress: () => undefined, fetchImpl, backoff: [] })).rejects.toBeInstanceOf(ApiError);
  });
});
