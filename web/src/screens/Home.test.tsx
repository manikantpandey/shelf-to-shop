import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import "../i18n";
import { api, type Offers, type Stats, type VideoSummary } from "../api";
import { DemoPath, Home } from "./Home";

vi.mock("../session", () => ({ useSession: () => ({ me: null, loading: false, refresh: vi.fn(), setMe: vi.fn() }) }));
// Only the network call is replaced; the rest of the module stays real.
vi.mock("../api", async (importOriginal) => ({ ...(await importOriginal<typeof import("../api")>()), api: vi.fn() }));

const stats = (counts: Partial<Stats["orders"]["counts"]>) =>
  ({ orders: { counts: { new: 0, packed: 0, delivered: 0, cancelled: 0, ...counts } } }) as unknown as Stats;
const video = (id: string, status: VideoSummary["status"]) => ({ id, status }) as VideoSummary;

const path = (s: Stats, videos: VideoSummary[], onHide = vi.fn()) =>
  render(
    <MemoryRouter>
      <DemoPath stats={s} videos={videos} url="https://shop.example/s/sharma" onHide={onHide} />
    </MemoryRouter>,
  );

afterEach(() => {
  cleanup();
  localStorage.clear();
});

describe("demo path", () => {
  it("links each open step to where it is done, and ticks the rest", () => {
    path(stats({ new: 1 }), [{ ...video("v3", "needs_review"), open_flags: 2 }, video("v1", "published")]);
    expect(screen.getByRole("link", { name: "Check" }).getAttribute("href")).toBe("/jobs/v3/review");
    expect(screen.getByRole("link", { name: "Open the video" }).getAttribute("href")).toBe("/videos/v1");
    expect(screen.getByRole("link", { name: "See orders" }).getAttribute("href")).toBe("/orders");
    expect(screen.getAllByText("Done")).toHaveLength(1); // the order was sent
    expect(screen.queryByRole("link", { name: "Record" })).toBeNull();
  });

  it("offers recording once all four are done", () => {
    localStorage.setItem("sts_path_read", "1");
    path(stats({ packed: 1 }), [video("v1", "published")]);
    expect(screen.getAllByText("Done")).toHaveLength(4);
    expect(screen.getByText("That is the whole loop. Next: record your own shelf.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Record" }).getAttribute("href")).toBe("/record");
  });

  it("says Check whatever the questions are about, since Home only knows how many there are", () => {
    path(stats({}), [{ ...video("v3", "needs_review"), open_flags: 0 }]);
    expect(screen.queryByRole("link", { name: "Fix prices" })).toBeNull();
    expect(screen.getByRole("link", { name: "Check" }).getAttribute("href")).toBe("/jobs/v3/review");
  });

  it("can be hidden", () => {
    const onHide = vi.fn();
    path(stats({}), [video("v1", "needs_review")], onHide);
    fireEvent.click(screen.getByRole("button", { name: "Hide" }));
    expect(onHide).toHaveBeenCalledOnce();
  });
});

describe("home offer notice", () => {
  const week = {
    items_live: 2, items_sold_out: 0, views_7d: 0, orders_7d: 0, by_day: [], top_items: [], videos: 0, videos_to_check: 0,
    videos_processing: 0, questions_open: 0, spend_usd: "0.00", shop_url: null, published_at: null,
    orders: { counts: { new: 0, packed: 0, delivered: 0, cancelled: 0 }, today_orders: 0, today_total_inr: 0, today_paid_inr: 0 },
  } as Stats;
  const offers: Offers = {
    active: {
      id: "o1", kind: "diwali", title_en: "Diwali sale", title_hi: "दिवाली सेल", percent_off: 10, scope: "all", section_id: null,
      item_ids: [], items_count: 12, ends_on: "2026-11-03", started_at: "2026-11-01T05:00:00Z", ended_at: null, active: true,
    },
    past: [],
    shop_url: "https://shop.example/s/sharma",
  };
  const serve = (offersCall: () => Promise<unknown>) =>
    vi.mocked(api).mockImplementation(async (path: string) => {
      if (path === "/api/v1/stats") return week as never;
      if (path === "/api/v1/videos") return { videos: [] } as never;
      if (path === "/api/v1/catalog") return { published: false } as never;
      if (path === "/api/v1/items") return { items: [] } as never;
      if (path === "/api/v1/offers") return (await offersCall()) as never;
      throw new Error(`unexpected ${path}`);
    });
  const home = () =>
    render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>,
    );

  afterEach(() => vi.mocked(api).mockReset());

  it("says which offer is on until when, and links to telling customers", async () => {
    serve(async () => offers);
    home();
    const note = await screen.findByRole("link", { name: /^Diwali sale is on until 3 Nov\./ });
    expect(note.getAttribute("href")).toBe("/offers");
    expect(note.textContent).toContain("Tell customers");
  });

  it("opens without the notice when no offer is on, or when the offers call fails", async () => {
    serve(async () => ({ ...offers, active: null }));
    home();
    expect(await screen.findByRole("heading", { name: "Your shop" })).toBeTruthy();
    expect(screen.queryByText(/is on until/)).toBeNull();
    cleanup();

    serve(() => Promise.reject(new Error("offers are down")));
    home();
    expect(await screen.findByRole("heading", { name: "Your shop" })).toBeTruthy();
    expect(screen.queryByText(/is on until/)).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
