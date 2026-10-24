import { useEffect, useState } from "react";
import { RunPanel, SignOffPanel, StepsPanel } from "./AgentPanels";
import { getClaim, type Claim } from "./api";
import { OUTCOME_LABELS, label, message, money } from "./format";
import { StatusPill } from "./Queue";

const POLL_MS = 1000;

function Story({ claim }: Readonly<{ claim: Claim }>) {
  return (
    <section className="panel" aria-label="Story">
      <h2>What the customer told us</h2>
      <p className="story">{claim.story}</p>
      <dl className="facts">
        <dt>Incident</dt>
        <dd>
          {claim.incident_date}, {claim.incident_location}
        </dd>
        <dt>Submitted</dt>
        <dd>{claim.submitted_on}</dd>
      </dl>
    </section>
  );
}

function Items({ claim }: Readonly<{ claim: Claim }>) {
  return (
    <section className="panel" aria-label="Items">
      <h2>Items claimed</h2>
      <table>
        <thead>
          <tr>
            <th>Item</th>
            <th>Category</th>
            <th className="money">Amount</th>
          </tr>
        </thead>
        <tbody>
          {claim.items.map((item) => (
            <tr key={item.description}>
              <td>{item.description}</td>
              <td>{label(item.category)}</td>
              <td className="money">{money(item.amount)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <th>Total</th>
            <th />
            <th className="money">{money(claim.amount_claimed)}</th>
          </tr>
        </tfoot>
      </table>
    </section>
  );
}

function Documents({ claim }: Readonly<{ claim: Claim }>) {
  return (
    <section className="panel" aria-label="Documents">
      <h2>Documents</h2>
      {claim.documents.map((doc) => (
        <div className="document" key={doc.name}>
          <h3>{doc.name}</h3>
          <p className="muted">{label(doc.type)}</p>
          <p>{doc.content}</p>
        </div>
      ))}
    </section>
  );
}

function PolicyPanel({ claim }: Readonly<{ claim: Claim }>) {
  const { policy, plan } = claim;
  return (
    <section className="panel" aria-label="Policy">
      <h2>Policy and plan</h2>
      <dl className="facts">
        <dt>Policy</dt>
        <dd className="mono">{policy.policy_id}</dd>
        <dt>Plan</dt>
        <dd>{plan.name}</dd>
        <dt>Add-ons</dt>
        <dd>
          {claim.add_ons.length
            ? claim.add_ons.map((a) => a.name).join(", ")
            : "None"}
        </dd>
        <dt>Trip</dt>
        <dd>
          {policy.trip.destination}, {policy.trip.departs_on} to{" "}
          {policy.trip.returns_on}
        </dd>
        <dt>Trip cost</dt>
        <dd className="mono">{money(policy.trip.trip_cost)}</dd>
        <dt>Travelers</dt>
        <dd>{policy.travelers.join(", ")}</dd>
        <dt>Bought</dt>
        <dd>
          {policy.purchased_on}, through {policy.sold_through}
        </dd>
        <dt>Deductible</dt>
        <dd>
          <span className="mono">{money(plan.deductible)}</span>{" "}
          <span className="muted">
            ({plan.deductible_applies_to.map(label).join(", ")})
          </span>
        </dd>
        <dt>Per-item limit</dt>
        <dd className="mono">{money(plan.per_item_limit)}</dd>
      </dl>
    </section>
  );
}

function History({ claim }: Readonly<{ claim: Claim }>) {
  const { customer } = claim;
  return (
    <section className="panel" aria-label="Customer history">
      <h2>{customer.name}</h2>
      <p className="muted">Customer since {customer.customer_since}</p>
      {customer.previous_claims.length === 0 ? (
        <p>No earlier claims.</p>
      ) : (
        <ul className="history">
          {customer.previous_claims.map((prior) => (
            <li key={prior.claim_id}>
              <div>
                <span className="mono">{prior.claim_id}</span>{" "}
                <span className="muted">filed {prior.filed_on}</span>
              </div>
              <div>{prior.summary}</div>
              <div>
                {label(prior.outcome)},{" "}
                <span className="mono">{money(prior.amount_paid)}</span> paid
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function DecisionPanel({ claim }: Readonly<{ claim: Claim }>) {
  const { decision, payment } = claim;
  if (!decision) {
    return (
      <section className="panel" aria-label="Decision">
        <h2>Decision</h2>
        <p className="muted">The agent has not decided this claim yet.</p>
      </section>
    );
  }
  return (
    <section className="panel" aria-label="Decision">
      <h2>Decision</h2>
      <div className="actions">
        <span className={`pill ${decision.outcome}`}>
          {OUTCOME_LABELS[decision.outcome]}
        </span>
        <span className="decision-amount">{money(decision.payout)}</span>
      </div>
      <p>{decision.reason}</p>
      <p className="muted">Policy section: {decision.policy_section}</p>
      {payment && (
        <p className="positive">
          Paid {money(payment.amount)}
          {payment.signed_off_by &&
            ` after sign-off by ${payment.signed_off_by}`}
        </p>
      )}
    </section>
  );
}

export function ClaimPage({ claimId }: Readonly<{ claimId: string }>) {
  const [claim, setClaim] = useState<Claim | null>(null);
  const [error, setError] = useState<string | null>(null);

  const inProgress = claim?.status === "in_progress";

  useEffect(() => {
    const load = () => {
      getClaim(claimId).then(setClaim, (failure: unknown) => {
        setError(message(failure));
      });
    };
    load();
    if (!inProgress) return;
    const timer = setInterval(load, POLL_MS);
    return () => {
      clearInterval(timer);
    };
  }, [claimId, inProgress]);

  if (error) return <p className="error">Could not load the claim: {error}</p>;
  if (!claim) return <p className="muted">Loading {claimId}</p>;

  return (
    <article>
      <p>
        <a href="#/">Back to the queue</a>
      </p>
      <div className="claim-title">
        <h1>{claim.claim_id}</h1>
        <StatusPill status={claim.status} />
      </div>
      <p className="muted">
        {label(claim.claim_type)}, {claim.summary}. Claimed{" "}
        <span className="mono">{money(claim.amount_claimed)}</span>
      </p>
      {claim.status === "waiting" && (
        <RunPanel claim={claim} onChange={setClaim} />
      )}
      {claim.status === "awaiting_signoff" && (
        <SignOffPanel claim={claim} onChange={setClaim} />
      )}
      <DecisionPanel claim={claim} />
      <StepsPanel claim={claim} />
      <div className="grid">
        <Story claim={claim} />
        <Items claim={claim} />
        <PolicyPanel claim={claim} />
        <History claim={claim} />
      </div>
      <Documents claim={claim} />
    </article>
  );
}
