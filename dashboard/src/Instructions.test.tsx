import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { Instructions } from "./Instructions";
import { stubApi } from "./testing";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("shows the instructions with nothing to edit", async () => {
  stubApi({
    "GET /api/instructions": { text: "# UnderCover Agent\n\nDecide claims." },
  });
  const { container } = render(<Instructions />);
  expect((await screen.findByText(/Decide claims\./)).textContent).toBe(
    "# UnderCover Agent\n\nDecide claims.",
  );
  expect(
    container.querySelectorAll("input, textarea, select, [contenteditable]"),
  ).toHaveLength(0);
});

it("says when the instructions cannot load", async () => {
  stubApi({});
  render(<Instructions />);
  expect(
    await screen.findByText(
      "Could not load the instructions: No route GET /api/instructions",
    ),
  ).toBeDefined();
});
