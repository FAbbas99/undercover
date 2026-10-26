import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { Instructions } from "./Instructions";
import { stubApi } from "./testing";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("shows both documents with nothing to edit", async () => {
  stubApi({
    "GET /api/instructions/queue": { text: "Work the run's to-do list." },
    "GET /api/instructions/claim": { text: "Decide the claim." },
  });
  const { container } = render(<Instructions />);
  expect(
    (await screen.findByText("Work the run's to-do list.")).textContent,
  ).toBe("Work the run's to-do list.");
  expect(screen.getByText("Decide the claim.")).toBeDefined();
  expect(screen.getByText("Running the queue")).toBeDefined();
  expect(screen.getByText("Working a claim")).toBeDefined();
  expect(
    container.querySelectorAll("input, textarea, select, [contenteditable]"),
  ).toHaveLength(0);
});

it("says when the instructions cannot load", async () => {
  stubApi({});
  render(<Instructions />);
  expect(
    await screen.findByText(
      "Could not load the instructions: No route GET /api/instructions/queue",
    ),
  ).toBeDefined();
});
