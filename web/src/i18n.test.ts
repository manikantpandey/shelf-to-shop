import { describe, expect, it } from "vitest";

import en from "./locales/en.json";
import hi from "./locales/hi.json";

function keys(obj: object, prefix = ""): string[] {
  return Object.entries(obj).flatMap(([k, v]) =>
    v && typeof v === "object" ? keys(v as object, `${prefix}${k}.`) : [`${prefix}${k}`],
  );
}

describe("translations", () => {
  it("Hindi has every English key and no extras", () => {
    expect(keys(hi).sort()).toEqual(keys(en).sort());
  });

  it("no string is empty and interpolations match", () => {
    const enMap = new Map(keys(en).map((k) => [k, k.split(".").reduce<any>((o, p) => o[p], en)]));
    for (const k of keys(hi)) {
      const h: string = k.split(".").reduce<any>((o, p) => o[p], hi);
      expect(h.trim(), k).not.toBe("");
      const vars = (s: string) => (s.match(/{{\s*\w+\s*}}/g) ?? []).sort();
      expect(vars(h), k).toEqual(vars(enMap.get(k)));
    }
  });

  it("UI copy has no emoji", () => {
    const all = JSON.stringify(en) + JSON.stringify(hi);
    expect(/\p{Extended_Pictographic}/u.test(all)).toBe(false);
  });
});
