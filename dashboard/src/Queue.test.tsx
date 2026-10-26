import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { Queue } from "./Queue";
import { stubApi, summaries } from "./testing";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

const rows = () => screen.getAllByRole("row").slice(1);

it("lists every claim with its status and amount", async () => {
  stubApi({ "GET /api/claims": summaries, "GET /api/runs/current": null });
  render(<Queue />);
  await screen.findByText("CLM-1001");
  expect(rows()).toHaveLength(3);
  expect(screen.getAllByText("$1,250.00")).toHaveLength(2);
  expect(screen.getByText("Trip delay")).toBeDefined();
  expect(
    screen.getByRole("link", { name: "CLM-1002" }).getAttribute("href"),
  ).toBe("#/claims/CLM-1002");
});

it("counts the claims in each status", async () => {
  stubApi({ "GET /api/claims": summaries, "GET /api/runs/current": null });
  render(<Queue />);
  await screen.findByText("CLM-1001");
  expect(screen.getByTestId("count-waiting").textContent).toBe("1");
  expect(screen.getByTestId("count-in_progress").textContent).toBe("0");
  expect(screen.getByTestId("count-awaiting_signoff").textContent).toBe("1");
  expect(screen.getByTestId("count-decided").textContent).toBe("1");
});

it("filters by status", async () => {
  stubApi({ "GET /api/claims": summaries, "GET /api/runs/current": null });
  render(<Queue />);
  await screen.findByText("CLM-1001");
  fireEvent.click(screen.getByRole("button", { name: "Waiting for sign-off" }));
  expect(rows()).toHaveLength(1);
  expect(screen.getByText("CLM-1002")).toBeDefined();
  fireEvent.click(screen.getByRole("button", { name: "In progress" }));
  expect(screen.getByText("No claims here.")).toBeDefined();
  fireEvent.click(screen.getByRole("button", { name: "All" }));
  expect(rows()).toHaveLength(3);
});

it("refreshes the queue", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const fetchMock = stubApi({
    "GET /api/claims": summaries,
    "GET /api/runs/current": null,
  });
  render(<Queue />);
  await screen.findByText("CLM-1001");
  await vi.advanceTimersByTimeAsync(2100);
  expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(2);
});

it("shows the failed attempts on a claim", async () => {
  stubApi({
    "GET /api/claims": [{ ...summaries[0], failures: 2 }, summaries[1]],
    "GET /api/runs/current": null,
  });
  render(<Queue />);
  await screen.findByText("CLM-1001");
  expect(screen.getByText("2 failed attempts")).toBeDefined();
});

it("says when the queue cannot load", async () => {
  stubApi({});
  render(<Queue />);
  expect(
    await screen.findByText(
      "Could not load the queue: No route GET /api/claims",
    ),
  ).toBeDefined();
});

it("shows each claim's decision and payout", async () => {
  stubApi({ "GET /api/claims": summaries, "GET /api/runs/current": null });
  render(<Queue />);
  await screen.findByText("CLM-1001");
  const cells = (claimId: string) =>
    Array.from(
      screen.getByRole("link", { name: claimId }).closest("tr")?.cells ?? [],
    )
      .slice(-2)
      .map((cell) => cell.textContent);
  expect(cells("CLM-1001")).toEqual(["", ""]);
  expect(cells("CLM-1002")).toEqual(["Approved", "$1,250.00"]);
  expect(cells("CLM-1003")).toEqual(["Referred", "$0.00"]);
});
