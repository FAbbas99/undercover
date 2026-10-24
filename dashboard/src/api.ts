export type Status = "waiting" | "in_progress" | "awaiting_signoff" | "decided";
export type Outcome = "approve" | "decline" | "refer";

export interface ClaimSummary {
  claim_id: string;
  status: Status;
  customer_name: string;
  claim_type: string;
  summary: string;
  amount_claimed: number;
  submitted_on: string;
  outcome: Outcome | null;
  payout: number | null;
}

export interface Item {
  description: string;
  category: string;
  amount: number;
}

export interface ClaimDocument {
  name: string;
  type: string;
  content: string;
}

export interface Policy {
  policy_id: string;
  plan: string;
  add_ons: string[];
  purchased_on: string;
  sold_through: string;
  trip: {
    destination: string;
    departs_on: string;
    returns_on: string;
    trip_cost: number;
  };
  travelers: string[];
}

export interface Plan {
  plan: string;
  name: string;
  trip_cancellation_max: number;
  trip_delay_waiting_hours: number;
  trip_delay_max: number;
  baggage_delay_waiting_hours: number;
  baggage_delay_max: number;
  baggage_max: number;
  per_item_limit: number;
  passport_max: number;
  emergency_medical_max: number;
  deductible: number;
  deductible_applies_to: string[];
}

export interface AddOn {
  add_on: string;
  name: string;
  effect: string;
}

export interface PreviousClaim {
  claim_id: string;
  filed_on: string;
  claim_type: string;
  summary: string;
  outcome: string;
  amount_paid: number;
}

export interface Decision {
  outcome: Outcome;
  payout: number;
  reason: string;
  policy_section: string;
}

export interface Payment {
  amount: number;
  signed_off_by: string | null;
}

export interface Step {
  at: string;
  name: string;
  detail: string;
}

export interface Claim {
  claim_id: string;
  status: Status;
  claim_type: string;
  summary: string;
  submitted_on: string;
  incident_date: string;
  incident_location: string;
  story: string;
  items: Item[];
  amount_claimed: number;
  documents: ClaimDocument[];
  policy: Policy;
  plan: Plan;
  add_ons: AddOn[];
  customer: {
    customer_id: string;
    name: string;
    customer_since: string;
    previous_claims: PreviousClaim[];
  };
  decision: Decision | null;
  payment: Payment | null;
  steps: Step[];
}

export interface Handler {
  handler_id: string;
  name: string;
  role: string;
  can_approve_over_limit: boolean;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    const body = (await response.json()) as { detail?: unknown };
    throw new Error(
      typeof body.detail === "string" ? body.detail : response.statusText,
    );
  }
  return (await response.json()) as T;
}

function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export const listClaims = () => request<ClaimSummary[]>("/api/claims");
export const getClaim = (id: string) => request<Claim>(`/api/claims/${id}`);
export const listHandlers = () => request<Handler[]>("/api/handlers");
export const getInstructions = () =>
  request<{ text: string }>("/api/instructions");
export const runAgent = (id: string) =>
  post<Claim>(`/api/claims/${id}/run`, {});
export const signOff = (id: string, handlerId: string) =>
  post<Claim>(`/api/claims/${id}/sign-off`, { handler_id: handlerId });
