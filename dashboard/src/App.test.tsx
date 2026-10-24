import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { App } from "./App";
import { claim, stubApi, summaries } from "./testing";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.location.hash = "";
});

it("shows the queue by default", async () => {
  stubApi({ "GET /api/claims": summaries });
  render(<App />);
  expect(await screen.findByRole("link", { name: "CLM-1001" })).toBeDefined();
});

it("opens a claim from its link", async () => {
  stubApi({
    "GET /api/claims": summaries,
    "GET /api/claims/CLM-1001": claim(),
  });
  window.location.hash = "#/claims/CLM-1001";
  render(<App />);
  const heading = await screen.findByRole("heading", { level: 1 });
  expect(heading.textContent).toBe("CLM-1001");
  window.location.hash = "#/";
  window.dispatchEvent(new HashChangeEvent("hashchange"));
  const queue = await screen.findByRole("region", { name: "Claims queue" });
  expect(within(queue).getByText("Maya Patel")).toBeDefined();
});
