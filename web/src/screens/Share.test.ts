import { describe, expect, it } from "vitest";

import { dataUrlBlob, qrDataUrl } from "./Share";

describe("status picture", () => {
  it("reads the QR code without fetch(), which the site's CSP forbids for data: addresses", async () => {
    const url = await qrDataUrl("https://shop.example/s/sharma", 300);
    const blob = dataUrlBlob(url);
    expect(blob.type).toBe("image/png");
    const head = new Uint8Array(await blob.slice(0, 8).arrayBuffer());
    expect([...head]).toEqual([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]); // PNG signature
  });
});
