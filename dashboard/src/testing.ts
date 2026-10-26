import { vi } from "vitest";
import type { Claim, ClaimSummary, Handler, Run } from "./api";

export const summaries: ClaimSummary[] = [
  {
    claim_id: "CLM-1001",
    status: "waiting",
    customer_name: "Maya Patel",
    claim_type: "trip_delay",
    summary: "Flight home canceled",
    amount_claimed: 420,
    submitted_on: "2026-06-24",
    outcome: null,
    payout: null,
    failures: 0,
  },
  {
    claim_id: "CLM-1002",
    status: "awaiting_signoff",
    customer_name: "Tom Becker",
    claim_type: "baggage",
    summary: "Suitcase stolen",
    amount_claimed: 1250,
    submitted_on: "2026-06-25",
    outcome: "approve",
    payout: 1250,
    failures: 0,
  },
  {
    claim_id: "CLM-1003",
    status: "decided",
    customer_name: "Ana Ruiz",
    claim_type: "emergency_medical",
    summary: "Broken wrist",
    amount_claimed: 3800,
    submitted_on: "2026-06-26",
    outcome: "refer",
    payout: 0,
    failures: 0,
  },
];

export const handlers: Handler[] = [
  {
    handler_id: "HND-01",
    name: "Dana Whitfield",
    role: "Senior Claims Handler",
    can_approve_over_limit: true,
  },
  {
    handler_id: "HND-04",
    name: "Sam Trainee",
    role: "Trainee",
    can_approve_over_limit: false,
  },
];

export function claim(overrides: Partial<Claim> = {}): Claim {
  return {
    claim_id: "CLM-1001",
    status: "waiting",
    failures: 0,
    claim_type: "trip_delay",
    summary: "Flight home canceled",
    submitted_on: "2026-06-24",
    incident_date: "2026-06-18",
    incident_location: "Rome, Italy",
    story: "My flight home from Rome was canceled.",
    items: [
      { description: "Airport hotel", category: "accommodation", amount: 245 },
      { description: "Dinner", category: "meals", amount: 95 },
    ],
    amount_claimed: 340,
    documents: [
      {
        name: "Cancellation notice",
        type: "carrier_report",
        content: "Flight canceled for crew availability.",
      },
    ],
    policy: {
      policy_id: "POL-2001",
      plan: "premium",
      add_ons: ["electronics_plus"],
      purchased_on: "2026-04-22",
      sold_through: "Meridian Air checkout",
      trip: {
        destination: "Rome, Italy",
        departs_on: "2026-06-10",
        returns_on: "2026-06-18",
        trip_cost: 3100,
      },
      travelers: ["Maya Patel"],
    },
    plan: {
      plan: "premium",
      name: "UnderCover Premium",
      trip_cancellation_max: 5000,
      trip_delay_waiting_hours: 6,
      trip_delay_max: 800,
      baggage_delay_waiting_hours: 12,
      baggage_delay_max: 300,
      baggage_max: 1500,
      per_item_limit: 300,
      passport_max: 250,
      emergency_medical_max: 100000,
      deductible: 50,
      deductible_applies_to: ["baggage", "emergency_medical"],
    },
    add_ons: [
      {
        add_on: "electronics_plus",
        name: "Electronics Plus",
        effect: "Raises the per-item limit for electronics.",
      },
    ],
    customer: {
      customer_id: "CUS-3001",
      name: "Maya Patel",
      customer_since: "2023-04-11",
      previous_claims: [
        {
          claim_id: "CLM-0412",
          filed_on: "2024-08-19",
          claim_type: "baggage_delay",
          summary: "Checked bag arrived 30 hours late",
          outcome: "approved",
          amount_paid: 140,
        },
      ],
    },
    decision: null,
    payment: null,
    steps: [],
    ...overrides,
  };
}

export const run: Run = {
  run_id: "RUN-1",
  started_at: "2026-10-24T19:00:00Z",
  finished_at: null,
  cap: 3,
  summary: null,
  items: [
    { claim_id: "CLM-1001", state: "done", note: "approve $420.00, decided" },
    { claim_id: "CLM-1002", state: "in_progress", note: "working" },
    { claim_id: "CLM-1003", state: "to_do", note: "" },
  ],
};

export function stubApi(routes: Record<string, unknown>) {
  const fetchMock = vi.fn((path: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${path}`;
    if (!(key in routes)) {
      return Promise.resolve(
        new Response(JSON.stringify({ detail: `No route ${key}` }), {
          status: 404,
        }),
      );
    }
    return Promise.resolve(new Response(JSON.stringify(routes[key])));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
