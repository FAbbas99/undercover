import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { RunPanel } from "./RunPanels";
import { run, stubApi } from "./testing";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

it("starts a run with the cap asked for", async () => {
  const fetchMock = stubApi({
    "GET /api/runs/current": null,
    "POST /api/runs": run,
  });
  render(<RunPanel />);
  await screen.findByText("No run has been started yet.");
  fireEvent.change(screen.getByLabelText("Claims to work"), {
    target: { value: "3" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Start run" }));
  await screen.findByText("CLM-1001");
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/runs",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ cap: 3 }),
    }),
  );
});

it("shows the to-do list, with where each claim has got to", async () => {
  stubApi({ "GET /api/runs/current": run });
  render(<RunPanel />);
  await screen.findByText("CLM-1001");
  expect(screen.getByText("Done")).toBeDefined();
  expect(screen.getByText("In progress")).toBeDefined();
  expect(screen.getByText("To do")).toBeDefined();
  expect(screen.getByText("approve $420.00, decided")).toBeDefined();
  expect(screen.getByText(/1 of 3 done/)).toBeDefined();
  expect(
    screen.getByRole("link", { name: "CLM-1002" }).getAttribute("href"),
  ).toBe("#/claims/CLM-1002");
});

it("shows the summary once the run has finished", async () => {
  stubApi({
    "GET /api/runs/current": {
      ...run,
      finished_at: "2026-10-24T19:05:00Z",
      summary: "Two claims approved, one left for a handler.",
    },
  });
  render(<RunPanel />);
  expect(
    await screen.findByText("Two claims approved, one left for a handler."),
  ).toBeDefined();
});

it("does not start a second run while one is going", async () => {
  stubApi({ "GET /api/runs/current": run });
  render(<RunPanel />);
  const button = await screen.findByRole("button", { name: "Start run" });
  expect(button.hasAttribute("disabled")).toBe(true);
});

it("refreshes the run", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const fetchMock = stubApi({ "GET /api/runs/current": run });
  render(<RunPanel />);
  await screen.findByText("CLM-1001");
  await vi.advanceTimersByTimeAsync(2100);
  expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(2);
});

it("says when the run cannot be started", async () => {
  stubApi({ "GET /api/runs/current": null });
  render(<RunPanel />);
  await screen.findByText("No run has been started yet.");
  fireEvent.click(screen.getByRole("button", { name: "Start run" }));
  expect(await screen.findByText("No route POST /api/runs")).toBeDefined();
});
