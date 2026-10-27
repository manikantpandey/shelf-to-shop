import { describe, expect, it } from "vitest";

import { formatINR, formatPhone } from "./format";

describe("formatPhone", () => {
  it("shows Indian numbers the way people write them", () => {
    expect(formatPhone("919876543210")).toBe("+91 98765 43210");
    expect(formatPhone("447700900123")).toBe("+447700900123");
    expect(formatPhone(null)).toBe("");
  });
});

describe("formatINR", () => {
  it("uses Indian digit grouping and no paise", () => {
    expect(formatINR(850)).toBe("₹850");
    expect(formatINR(1200)).toBe("₹1,200");
    expect(formatINR(120000)).toBe("₹1,20,000");
  });
});
