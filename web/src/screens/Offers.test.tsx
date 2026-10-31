import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../i18n";
import { api, type Item, type Offer, type Offers as OffersData, type ShopSection } from "../api";
import { Offers } from "./Offers";

vi.mock("../session", () => ({
  useSession: () => ({
    me: { name: "", workspace: { name: "Sharma General Store" } },
    loading: false,
    refresh: vi.fn(),
    setMe: vi.fn(),
  }),
}));
// Only the network call is replaced; ApiError and the helpers stay real.
vi.mock("../api", async (importOriginal) => ({ ...(await importOriginal<typeof import("../api")>()), api: vi.fn() }));

const URL_ = "https://shop.example/s/sharma-general-store";
const SECTIONS: ShopSection[] = [
  { id: "s1", name_en: "Snacks", name_hi: "स्नैक्स", items: 2 },
  { id: "s2", name_en: "Cold drinks", name_hi: "ठंडे पेय", items: 1 },
];
const item = (id: string, title: string, price: number, live = true) =>
  ({ id, title_en: title, title_hi: title, price_inr: price, live, brand: null, on_offer: false }) as unknown as Item;
const ITEMS = [item("i1", "Nut Cracker", 4), item("i2", "Slice 600 ml", 40), item("i3", "Old stock", 9, false)];

const running = (over: Partial<Offer> = {}): Offer => ({
  id: "o1",
  kind: "diwali",
  title_en: "Diwali sale",
  title_hi: "दिवाली सेल",
  percent_off: 10,
  scope: "section",
  section_id: "s1",
  item_ids: [],
  items_count: 2,
  ends_on: "2026-11-03",
  started_at: "2026-11-01T05:00:00Z",
  ended_at: null,
  active: true,
  ...over,
});

function serve(offers: OffersData, post?: (path: string, body: unknown) => unknown) {
  vi.mocked(api).mockImplementation(async (path: string, opts?: { method?: string; json?: unknown }) => {
    if (opts?.method === "POST" && post) return post(path, opts.json) as never;
    if (path === "/api/v1/offers") return offers as never;
    if (path === "/api/v1/sections") return { sections: SECTIONS } as never;
    if (path === "/api/v1/items") return { items: ITEMS } as never;
    throw new Error(`unexpected ${path}`);
  });
}

const page = () =>
  render(
    <MemoryRouter>
      <Offers />
    </MemoryRouter>,
  );

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2026, 10, 1, 10, 0));
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.mocked(api).mockReset();
  vi.restoreAllMocks();
});

describe("offers screen", () => {
  it("shows the form when nothing is running, with a live message preview", async () => {
    serve({ active: null, past: [], shop_url: URL_ });
    page();
    expect(await screen.findByRole("heading", { name: "Run an offer" })).toBeTruthy();
    expect(screen.getByRole("radio", { name: "Diwali" }).getAttribute("aria-checked")).toBe("true");
    expect((screen.getByLabelText("Offer name in English") as HTMLInputElement).value).toBe("Diwali sale");
    expect((screen.getByLabelText("Offer name in Hindi") as HTMLInputElement).value).toBe("दिवाली सेल");
    expect((screen.getByLabelText("Last day of the offer") as HTMLInputElement).value).toBe("2026-11-04");
    expect((screen.getByLabelText("Last day of the offer") as HTMLInputElement).min).toBe("2026-11-01");
    expect(screen.getByText(`Diwali sale at Sharma General Store: 10% off on everything until 4 Nov. See the offers and order on WhatsApp: ${URL_}`))
      .toBeTruthy();
    expect(screen.getByRole("button", { name: "Start offer" })).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Tell customers on WhatsApp" })).toBeNull();
  });

  it("makes new stock an announcement with prices unchanged", async () => {
    serve({ active: null, past: [], shop_url: URL_ });
    page();
    fireEvent.click(await screen.findByRole("radio", { name: "New stock" }));
    expect((screen.getByLabelText("Offer name in English") as HTMLInputElement).value).toBe("New stock");
    expect(screen.getByRole("radio", { name: "Announcement only, no discount" }).getAttribute("aria-checked")).toBe("true");
    expect((screen.getByRole("radio", { name: "10%" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/^New stock at Sharma General Store, until 4 Nov\. See the shop/)).toBeTruthy();
  });

  it("starts an offer on chosen items and then shows it running", async () => {
    const posted: { path: string; body: unknown }[] = [];
    serve({ active: null, past: [], shop_url: URL_ }, (path, body) => {
      posted.push({ path, body });
      return { offer: running({ scope: "items", section_id: null, item_ids: ["i2"], items_count: 1, percent_off: 15 }), shop_version: 7 };
    });
    page();
    fireEvent.click(await screen.findByRole("radio", { name: "15%" }));
    fireEvent.click(screen.getByRole("radio", { name: "Chosen items" }));
    // Only items on the shop can be chosen.
    expect(screen.queryByText("Old stock")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Start offer" }));
    expect(screen.getByRole("alert").textContent).toBe("Pick at least one item for the offer.");
    expect(posted).toHaveLength(0);

    fireEvent.change(screen.getByRole("searchbox", { name: "Search items" }), { target: { value: "slice" } });
    expect(screen.queryByText("Nut Cracker")).toBeNull();
    fireEvent.click(screen.getByRole("checkbox", { name: /Slice 600 ml/ }));
    expect(screen.getByText("1 item chosen")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Start offer" }));

    expect(await screen.findByText("Offer started. Your shop page shows it now.")).toBeTruthy();
    expect(posted).toEqual([{
      path: "/api/v1/offers",
      body: {
        kind: "diwali", title_en: "Diwali sale", title_hi: "दिवाली सेल", percent_off: 15, scope: "items",
        item_ids: ["i2"], ends_on: "2026-11-04",
      },
    }]);
    expect(screen.getByText("1 chosen item")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Tell customers on WhatsApp" })).toBeTruthy();
  });

  it("asks for a section before starting a section offer", async () => {
    const post = vi.fn(() => ({ offer: running(), shop_version: 3 }));
    serve({ active: null, past: [], shop_url: URL_ }, post);
    page();
    fireEvent.click(await screen.findByRole("radio", { name: "One section" }));
    fireEvent.click(screen.getByRole("button", { name: "Start offer" }));
    expect(screen.getByRole("alert").textContent).toBe("Pick a section for the offer.");
    fireEvent.change(screen.getByLabelText("Section"), { target: { value: "s1" } });
    expect(screen.getByText(/10% off on Snacks until 4 Nov/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Start offer" }));
    await waitFor(() => expect(post).toHaveBeenCalledOnce());
    expect(post).toHaveBeenCalledWith("/api/v1/offers", expect.objectContaining({ scope: "section", section_id: "s1", percent_off: 10 }));
  });

  it("shows the running offer, opens WhatsApp with the message, and ends it after asking", async () => {
    const post = vi.fn(() => ({ offer: running({ active: false, ended_at: "2026-11-02T09:00:00Z" }), shop_version: 8 }));
    serve({ active: running(), past: [], shop_url: URL_ }, post);
    page();
    expect(await screen.findByRole("heading", { name: "Diwali sale" })).toBeTruthy();
    expect(screen.getByText("On until 3 Nov. It ends by itself after that day.")).toBeTruthy();
    expect(screen.getByText("Snacks")).toBeTruthy();
    expect(screen.getByText("2 prices lowered")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Start offer" })).toBeNull();

    const text = `Diwali sale at Sharma General Store: 10% off on Snacks until 3 Nov. See the offers and order on WhatsApp: ${URL_}`;
    const wa = screen.getByRole("link", { name: "Tell customers on WhatsApp" });
    expect(wa.getAttribute("href")).toBe(`https://wa.me/?text=${encodeURIComponent(text)}`);
    expect(wa.getAttribute("target")).toBe("_blank");
    expect(screen.getByText(text)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Copy message" })).toBeTruthy();
    expect(screen.getByText(/Shelf-to-Shop never sends messages for you\./)).toBeTruthy();

    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    fireEvent.click(screen.getByRole("button", { name: "End offer now" }));
    expect(post).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "End offer now" }));
    expect(confirm).toHaveBeenCalledTimes(2);
    expect(await screen.findByText("Offer ended. Prices on your shop page are back to normal.")).toBeTruthy();
    expect(post).toHaveBeenCalledWith("/api/v1/offers/o1/end", undefined);
    // The form is back, and the ended offer is listed with the day it really ended.
    expect(screen.getByRole("heading", { name: "Run an offer" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Past offers" })).toBeTruthy();
    expect(screen.getByText("1 Nov to 2 Nov")).toBeTruthy();
  });

  it("does not offer WhatsApp before the shop is published", async () => {
    serve({ active: running({ percent_off: null, kind: "new_stock", title_en: "New stock", title_hi: null }), past: [], shop_url: null });
    page();
    expect(await screen.findByRole("heading", { name: "New stock" })).toBeTruthy();
    expect(screen.getByText("Unchanged, announcement only")).toBeTruthy();
    expect(screen.getByText(/once your shop is published/)).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Tell customers on WhatsApp" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Copy message" })).toBeNull();
    expect(screen.getByRole("button", { name: "End offer now" })).toBeTruthy();
  });
});
