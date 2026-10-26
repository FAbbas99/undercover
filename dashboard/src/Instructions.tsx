import { useEffect, useState } from "react";
import { getClaimInstructions, getQueueInstructions } from "./api";
import { message } from "./format";

interface Documents {
  queue: string;
  claim: string;
}

export function Instructions() {
  const [documents, setDocuments] = useState<Documents | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([getQueueInstructions(), getClaimInstructions()]).then(
      ([queue, claim]) => {
        setDocuments({ queue: queue.text, claim: claim.text });
      },
      (failure: unknown) => {
        setError(message(failure));
      },
    );
  }, []);

  if (error) {
    return <p className="error">Could not load the instructions: {error}</p>;
  }
  return (
    <section className="panel" aria-label="Agent instructions">
      <h2>The UnderCover Agent's instructions</h2>
      <p className="muted">
        Read only. The agent reads these at the start of every run.
      </p>
      {documents === null ? (
        <p className="muted">Loading the instructions</p>
      ) : (
        <>
          <h3>Running the queue</h3>
          <pre className="instructions">{documents.queue}</pre>
          <h3>Working a claim</h3>
          <pre className="instructions">{documents.claim}</pre>
        </>
      )}
    </section>
  );
}
