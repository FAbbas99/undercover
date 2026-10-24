import { useEffect, useState } from "react";
import { getInstructions } from "./api";
import { message } from "./format";

export function Instructions() {
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getInstructions().then(
      (loaded) => {
        setText(loaded.text);
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
        Read only. The agent reads these at the start of every claim.
      </p>
      {text === null ? (
        <p className="muted">Loading the instructions</p>
      ) : (
        <pre className="instructions">{text}</pre>
      )}
    </section>
  );
}
