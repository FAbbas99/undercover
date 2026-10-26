import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ClaimPage } from "./ClaimPage";
import { claim, handlers, stubApi } from "./testing";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const started = { at: "2026-10-24T19:00:00Z", name: "started", detail: "" };
const readClaim = {
  at: "2026-10-24T19:00:01Z",
  name: "get_claim",
  detail: "CLM-1001",
};
const finished = {
  at: "2026-10-24T19:00:05Z",
  name: "finished",
  detail: "Approved and paid $420.00.",
};
const approved = {
  outcome: "approve" as const,
  payout: 420,
  reason: "The delay was covered.",
  policy_section: "3. Trip Delay",
};

it("runs the agent and follows its steps until it decides", async () => {
  const routes: Record<string, unknown> = {
    "GET /api/claims/CLM-1001": claim(),
    "POST /api/claims/CLM-1001/run": claim({
      status: "in_progress",
      steps: [started],
    }),
  };
  const fetchMock = stubApi(routes);
  render(<ClaimPage claimId="CLM-1001" />);
  fireEvent.click(await screen.findByRole("button", { name: "Run agent" }));
  expect(
    await screen.findByText("The agent is working on this claim."),
  ).toBeDefined();
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/claims/CLM-1001/run",
    expect.objectContaining({ method: "POST" }),
  );

  routes["GET /api/claims/CLM-1001"] = claim({
    status: "in_progress",
    steps: [started, readClaim],
  });
  expect(
    await screen.findByText("Read the claim, policy and history"),
  ).toBeDefined();

  routes["GET /api/claims/CLM-1001"] = claim({
    status: "decided",
    decision: approved,
    payment: { amount: 420, signed_off_by: null },
    steps: [started, readClaim, finished],
  });
  expect(
    await screen.findByText("Approved and paid $420.00.", undefined, {
      timeout: 3000,
    }),
  ).toBeDefined();
  const steps = within(screen.getByRole("region", { name: "Agent steps" }));
  expect(steps.getAllByRole("listitem").map((li) => li.textContent)).toEqual([
    "19:00:00Started work on the claim",
    "19:00:01Read the claim, policy and historyCLM-1001",
    "19:00:05FinishedApproved and paid $420.00.",
  ]);
  expect(screen.queryByRole("button", { name: "Run agent" })).toBeNull();
  const calls = fetchMock.mock.calls.length;
  await new Promise((resolve) => setTimeout(resolve, 1500));
  expect(fetchMock.mock.calls).toHaveLength(calls);
});

it("shows the sections of the documents the agent read", async () => {
  stubApi({
    "GET /api/claims/CLM-1001": claim({
      status: "decided",
      decision: approved,
      steps: [
        started,
        readClaim,
        {
          at: "2026-10-24T19:00:02Z",
          name: "read_wording",
          detail: "3. Trip Delay",
        },
        {
          at: "2026-10-24T19:00:03Z",
          name: "read_manual",
          detail: "10. Meals without receipts",
        },
      ],
    }),
  });
  render(<ClaimPage claimId="CLM-1001" />);
  const steps = within(
    await screen.findByRole("region", { name: "Agent steps" }),
  );
  expect(steps.getByText("Read a section of the policy wording")).toBeDefined();
  expect(steps.getByText("3. Trip Delay")).toBeDefined();
  expect(steps.getByText("Read a section of the claims manual")).toBeDefined();
  expect(steps.getByText("10. Meals without receipts")).toBeDefined();
});

it("says when the agent cannot start", async () => {
  stubApi({ "GET /api/claims/CLM-1001": claim() });
  render(<ClaimPage claimId="CLM-1001" />);
  fireEvent.click(await screen.findByRole("button", { name: "Run agent" }));
  expect(
    await screen.findByText("No route POST /api/claims/CLM-1001/run"),
  ).toBeDefined();
});

const awaiting = claim({
  claim_id: "CLM-1002",
  status: "awaiting_signoff",
  decision: { ...approved, payout: 1250 },
});

it("signs off with a handler who may approve over the limit", async () => {
  const fetchMock = stubApi({
    "GET /api/claims/CLM-1002": awaiting,
    "GET /api/handlers": handlers,
    "POST /api/claims/CLM-1002/sign-off": {
      ...awaiting,
      status: "decided",
      payment: { amount: 1250, signed_off_by: "HND-01" },
    },
  });
  render(<ClaimPage claimId="CLM-1002" />);
  const select = await screen.findByLabelText("Handler");
  await screen.findByRole("option", { name: "Dana Whitfield" });
  expect(
    within(select)
      .getAllByRole("option")
      .map((o) => o.textContent),
  ).toEqual(["Choose a handler", "Dana Whitfield"]);
  const button = screen.getByRole("button", { name: "Sign off and pay" });
  expect((button as HTMLButtonElement).disabled).toBe(true);
  fireEvent.change(select, { target: { value: "HND-01" } });
  fireEvent.click(button);
  expect(
    await screen.findByText("Paid $1,250.00 after sign-off by HND-01"),
  ).toBeDefined();
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/claims/CLM-1002/sign-off",
    expect.objectContaining({ body: JSON.stringify({ handler_id: "HND-01" }) }),
  );
  expect(screen.queryByRole("region", { name: "Sign-off" })).toBeNull();
});

it("says when sign-off fails", async () => {
  stubApi({
    "GET /api/claims/CLM-1002": awaiting,
    "GET /api/handlers": handlers,
  });
  render(<ClaimPage claimId="CLM-1002" />);
  await screen.findByRole("option", { name: "Dana Whitfield" });
  fireEvent.change(screen.getByLabelText("Handler"), {
    target: { value: "HND-01" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Sign off and pay" }));
  expect(
    await screen.findByText("No route POST /api/claims/CLM-1002/sign-off"),
  ).toBeDefined();
});

it("says when the handlers cannot load", async () => {
  stubApi({ "GET /api/claims/CLM-1002": awaiting });
  render(<ClaimPage claimId="CLM-1002" />);
  await waitFor(() => {
    expect(screen.getByText("No route GET /api/handlers")).toBeDefined();
  });
});
