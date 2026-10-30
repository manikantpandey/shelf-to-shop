import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import "../i18n";
import type { Stats, VideoSummary } from "../api";
import { DemoPath } from "./Home";

vi.mock("../session", () => ({ useSession: () => ({ me: null, loading: false, refresh: vi.fn(), setMe: vi.fn() }) }));

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
    expect(screen.getByRole("link", { name: "Fix prices" }).getAttribute("href")).toBe("/jobs/v3/review");
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

  it("offers Check instead of Fix prices when the newest video has no questions", () => {
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
