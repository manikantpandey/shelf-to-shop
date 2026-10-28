import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import "../i18n";
import { EVALS, Landing } from "./Landing";

vi.mock("../session", () => ({ useSession: () => ({ me: null, loading: false, refresh: vi.fn(), setMe: vi.fn() }) }));

const page = () =>
  render(
    <MemoryRouter>
      <Landing />
    </MemoryRouter>,
  );

afterEach(cleanup);

describe("landing", () => {
  it("states the eval figures it was given", () => {
    page();
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Your shop's catalog from one video");
    expect(screen.getByText(`${EVALS.found} of ${EVALS.items}`)).toBeTruthy();
    expect(screen.getByText("wrong prices published without asking you").previousSibling?.textContent).toBe(String(EVALS.wrong));
  });

  it("switches demo steps on tap and stops playing", () => {
    page();
    const check = screen.getByRole("button", { name: /^2 Check$/ });
    fireEvent.click(check);
    expect(check.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText(/You check what it was not sure of\./)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Play" })).toBeTruthy();
  });

  it("plays, pauses, and offers to play again from the last step", () => {
    page();
    fireEvent.click(screen.getByRole("button", { name: "Play" }));
    fireEvent.click(screen.getByRole("button", { name: "Pause" }));
    fireEvent.click(screen.getByRole("button", { name: /^3 Share$/ }));
    fireEvent.click(screen.getByRole("button", { name: "Play again" }));
    expect(screen.getByRole("button", { name: /^1 Record$/ }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "Pause" })).toBeTruthy();
  });
});
