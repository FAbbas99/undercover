import { useEffect, useState } from "react";
import { getCurrentRun, startRun, type Run } from "./api";
import { RUN_STATE_LABELS, message } from "./format";

const REFRESH_MS = 2000;
const DEFAULT_CAP = 5;

export function RunPanel() {
  const [run, setRun] = useState<Run | null>(null);
  const [cap, setCap] = useState(DEFAULT_CAP);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = () => {
      getCurrentRun().then(setRun, (failure: unknown) => {
        setError(message(failure));
      });
    };
    load();
    const timer = setInterval(load, REFRESH_MS);
    return () => {
      clearInterval(timer);
    };
  }, []);

  const start = () => {
    setBusy(true);
    startRun(cap).then(setRun, (failure: unknown) => {
      setError(message(failure));
      setBusy(false);
    });
  };

  const running = run !== null && run.finished_at === null;
  const worked = run?.items.filter((item) => item.state === "done").length ?? 0;

  return (
    <section className="panel" aria-label="Queue run">
      <h2>The run</h2>
      <div className="actions">
        <label htmlFor="cap">Claims to work</label>
        <input
          id="cap"
          type="number"
          min="1"
          max="25"
          value={cap}
          onChange={(event) => {
            setCap(Number(event.target.value));
          }}
        />
        <button
          type="button"
          className="primary"
          disabled={busy || running || cap < 1}
          onClick={start}
        >
          Start run
        </button>
        <span className="muted">
          The agent works that many waiting claims and leaves the rest.
        </span>
      </div>
      {error && <p className="error">{error}</p>}
      {run === null ? (
        <p className="muted">No run has been started yet.</p>
      ) : (
        <>
          <p className="muted">
            Started {run.started_at.slice(11, 19)}, cap {run.cap}. {worked} of{" "}
            {run.items.length} done.
          </p>
          <ol className="todo">
            {run.items.map((item) => (
              <li key={item.claim_id}>
                <a className="mono" href={`#/claims/${item.claim_id}`}>
                  {item.claim_id}
                </a>
                <span className={`pill ${item.state}`}>
                  {RUN_STATE_LABELS[item.state]}
                </span>
                <span className="detail">{item.note}</span>
              </li>
            ))}
          </ol>
          {run.summary && <p className="summary">{run.summary}</p>}
        </>
      )}
    </section>
  );
}
