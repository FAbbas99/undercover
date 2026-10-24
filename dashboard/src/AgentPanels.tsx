import { useEffect, useState } from "react";
import {
  listHandlers,
  runAgent,
  signOff,
  type Claim,
  type Handler,
} from "./api";
import { label, message, money } from "./format";

const STEP_LABELS: Record<string, string> = {
  started: "Started work on the claim",
  get_claim: "Read the claim, policy and history",
  get_policy_wording: "Read the policy wording",
  record_decision: "Recorded a decision",
  pay_claim: "Asked to pay the claim",
  finished: "Finished",
};

interface Props {
  claim: Claim;
  onChange: (claim: Claim) => void;
}

export function RunPanel({ claim, onChange }: Readonly<Props>) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const start = () => {
    setBusy(true);
    runAgent(claim.claim_id).then(onChange, (failure: unknown) => {
      setError(message(failure));
      setBusy(false);
    });
  };

  return (
    <section className="panel" aria-label="Run the agent">
      <div className="actions">
        <button
          type="button"
          className="primary"
          disabled={busy}
          onClick={start}
        >
          Run agent
        </button>
        <span className="muted">
          The UnderCover Agent will read the claim and decide it.
        </span>
      </div>
      {error && <p className="error">{error}</p>}
    </section>
  );
}

export function StepsPanel({ claim }: Readonly<{ claim: Claim }>) {
  if (claim.steps.length === 0) return null;
  return (
    <section className="panel" aria-label="Agent steps">
      <h2>What the agent did</h2>
      <ol className="steps">
        {claim.steps.map((step, index) => (
          <li key={`${step.at}-${String(index)}`}>
            <span className="time">{step.at.slice(11, 19)}</span>
            <div>
              <div>{STEP_LABELS[step.name] ?? label(step.name)}</div>
              {step.name !== "started" && (
                <div className="detail">{step.detail}</div>
              )}
            </div>
          </li>
        ))}
      </ol>
      {claim.status === "in_progress" && (
        <p className="muted">The agent is working on this claim.</p>
      )}
    </section>
  );
}

export function SignOffPanel({ claim, onChange }: Readonly<Props>) {
  const [handlers, setHandlers] = useState<Handler[]>([]);
  const [handlerId, setHandlerId] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listHandlers().then(
      (all) => {
        setHandlers(all.filter((h) => h.can_approve_over_limit));
      },
      (failure: unknown) => {
        setError(message(failure));
      },
    );
  }, []);

  const submit = () => {
    signOff(claim.claim_id, handlerId).then(onChange, (failure: unknown) => {
      setError(message(failure));
    });
  };

  return (
    <section className="panel" aria-label="Sign-off">
      <h2>Sign-off needed</h2>
      <p>
        The agent approved a payout of{" "}
        <span className="mono">{money(claim.decision?.payout ?? 0)}</span>,
        which is over the approval limit. The payment waits until a handler
        signs off.
      </p>
      <div className="actions">
        <label htmlFor="handler">Handler</label>
        <select
          id="handler"
          value={handlerId}
          onChange={(event) => {
            setHandlerId(event.target.value);
          }}
        >
          <option value="">Choose a handler</option>
          {handlers.map((h) => (
            <option key={h.handler_id} value={h.handler_id}>
              {h.name}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="primary"
          disabled={!handlerId}
          onClick={submit}
        >
          Sign off and pay
        </button>
      </div>
      {error && <p className="error">{error}</p>}
    </section>
  );
}
