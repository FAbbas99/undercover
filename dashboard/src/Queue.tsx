import { useEffect, useState } from "react";
import { listClaims, type ClaimSummary, type Status } from "./api";
import { RunPanel } from "./RunPanels";
import {
  OUTCOME_LABELS,
  STATUS_LABELS,
  STATUSES,
  label,
  message,
  money,
} from "./format";

const REFRESH_MS = 2000;

export function StatusPill({ status }: Readonly<{ status: Status }>) {
  return <span className={`pill ${status}`}>{STATUS_LABELS[status]}</span>;
}

export function Queue() {
  const [claims, setClaims] = useState<ClaimSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Status | "all">("all");

  useEffect(() => {
    const load = () => {
      listClaims().then(
        (loaded) => {
          setClaims(loaded);
          setError(null);
        },
        (failure: unknown) => {
          setError(message(failure));
        },
      );
    };
    load();
    const timer = setInterval(load, REFRESH_MS);
    return () => {
      clearInterval(timer);
    };
  }, []);

  if (error) return <p className="error">Could not load the queue: {error}</p>;
  if (!claims) return <p className="muted">Loading the queue</p>;

  const shown =
    filter === "all" ? claims : claims.filter((c) => c.status === filter);

  return (
    <section aria-label="Claims queue">
      <RunPanel />
      <div className="counts">
        {STATUSES.map((status) => (
          <div className="count" key={status}>
            <StatusPill status={status} />
            <div className="number" data-testid={`count-${status}`}>
              {claims.filter((c) => c.status === status).length}
            </div>
          </div>
        ))}
      </div>
      <div className="filters" role="group" aria-label="Filter by status">
        <button
          type="button"
          aria-pressed={filter === "all"}
          onClick={() => {
            setFilter("all");
          }}
        >
          All
        </button>
        {STATUSES.map((status) => (
          <button
            type="button"
            key={status}
            aria-pressed={filter === status}
            onClick={() => {
              setFilter(status);
            }}
          >
            {STATUS_LABELS[status]}
          </button>
        ))}
      </div>
      <div className="panel">
        <table>
          <thead>
            <tr>
              <th>Claim</th>
              <th>Customer</th>
              <th>Type</th>
              <th>Summary</th>
              <th>Submitted</th>
              <th className="money">Claimed</th>
              <th>Status</th>
              <th>Decision</th>
              <th className="money">Payout</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((claim) => (
              <tr key={claim.claim_id}>
                <td className="mono">
                  <a href={`#/claims/${claim.claim_id}`}>{claim.claim_id}</a>
                  {claim.failures > 0 && (
                    <div className="muted">
                      {claim.failures} failed{" "}
                      {claim.failures === 1 ? "attempt" : "attempts"}
                    </div>
                  )}
                </td>
                <td>{claim.customer_name}</td>
                <td>{label(claim.claim_type)}</td>
                <td>{claim.summary}</td>
                <td className="mono">{claim.submitted_on}</td>
                <td className="money">{money(claim.amount_claimed)}</td>
                <td>
                  <StatusPill status={claim.status} />
                </td>
                <td>
                  {claim.outcome && (
                    <span className={`pill ${claim.outcome}`}>
                      {OUTCOME_LABELS[claim.outcome]}
                    </span>
                  )}
                </td>
                <td className="money">
                  {claim.payout !== null && money(claim.payout)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {shown.length === 0 && <p className="muted">No claims here.</p>}
      </div>
    </section>
  );
}
