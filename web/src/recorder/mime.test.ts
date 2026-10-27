import { describe, expect, it } from "vitest";

import { cameraProblem, pickMimeType } from "./mime";

describe("pickMimeType", () => {
  it("prefers MP4 where supported (iOS) and falls back to WebM (Android)", () => {
    expect(pickMimeType((t) => t.startsWith("video/mp4"))).toMatch(/^video\/mp4/);
    expect(pickMimeType((t) => t.startsWith("video/webm"))).toBe("video/webm;codecs=vp8,opus");
    expect(pickMimeType(() => false)).toBeUndefined();
    expect(pickMimeType(() => { throw new Error("old browser"); })).toBeUndefined();
  });
});

describe("cameraProblem", () => {
  it("explains why the camera is unavailable", () => {
    expect(cameraProblem(null, false, true)).toBe("insecure");
    expect(cameraProblem(null, true, false)).toBe("nocamera");
    expect(cameraProblem(new DOMException("x", "NotFoundError"), true, true)).toBe("nocamera");
    expect(cameraProblem(new DOMException("x", "NotAllowedError"), true, true)).toBe("denied");
  });
});
