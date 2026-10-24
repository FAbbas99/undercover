import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ClaimPage } from "./ClaimPage";
import { claim, stubApi } from "./testing";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("shows the claim in full", async () => {
  stubApi({ "GET /api/claims/CLM-1001": claim() });
  render(<ClaimPage claimId="CLM-1001" />);
  await screen.findByText("My flight home from Rome was canceled.");
  expect(screen.getByText("Airport hotel")).toBeDefined();
  expect(screen.getByText("Cancellation notice")).toBeDefined();
  expect(screen.getByText("UnderCover Premium")).toBeDefined();
  expect(screen.getByText("Electronics Plus")).toBeDefined();
  expect(screen.getByText("CLM-0412")).toBeDefined();
  expect(screen.getByText("$3,100.00")).toBeDefined();
  expect(
    screen.getByText("The agent has not decided this claim yet."),
  ).toBeDefined();
});

it("shows the decision, reason and policy section", async () => {
  stubApi({
    "GET /api/claims/CLM-1002": claim({
      claim_id: "CLM-1002",
      status: "decided",
      decision: {
        outcome: "approve",
        payout: 1250,
        reason: "The theft was reported and the items are covered.",
        policy_section: "5. Baggage and Personal Effects",
      },
      payment: { amount: 1250, signed_off_by: "HND-01" },
    }),
  });
  render(<ClaimPage claimId="CLM-1002" />);
  const decision = await screen.findByRole("region", { name: "Decision" });
  await within(decision).findByText("Approved");
  expect(screen.getAllByText("$1,250.00").length).toBeGreaterThan(0);
  expect(
    screen.getByText("The theft was reported and the items are covered."),
  ).toBeDefined();
  expect(
    screen.getByText("Policy section: 5. Baggage and Personal Effects"),
  ).toBeDefined();
  expect(
    screen.getByText("Paid $1,250.00 after sign-off by HND-01"),
  ).toBeDefined();
});

it("shows a customer with no earlier claims and no add-ons", async () => {
  const base = claim();
  stubApi({
    "GET /api/claims/CLM-1001": claim({
      add_ons: [],
      customer: { ...base.customer, previous_claims: [] },
    }),
  });
  render(<ClaimPage claimId="CLM-1001" />);
  expect(await screen.findByText("No earlier claims.")).toBeDefined();
  expect(screen.getByText("None")).toBeDefined();
});

it("says when the claim cannot load", async () => {
  stubApi({});
  render(<ClaimPage claimId="CLM-9999" />);
  expect(
    await screen.findByText(
      "Could not load the claim: No route GET /api/claims/CLM-9999",
    ),
  ).toBeDefined();
});
