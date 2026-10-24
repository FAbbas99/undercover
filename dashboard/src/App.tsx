import { useEffect, useState } from "react";
import { ClaimPage } from "./ClaimPage";
import { Instructions } from "./Instructions";
import { Queue } from "./Queue";

function useHash(): string {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const onChange = () => {
      setHash(window.location.hash);
    };
    window.addEventListener("hashchange", onChange);
    return () => {
      window.removeEventListener("hashchange", onChange);
    };
  }, []);
  return hash;
}

function Page({ hash }: Readonly<{ hash: string }>) {
  const claim = /^#\/claims\/([\w-]+)$/.exec(hash);
  if (claim) return <ClaimPage claimId={claim[1]} key={claim[1]} />;
  if (hash === "#/instructions") return <Instructions />;
  return <Queue />;
}

export function App() {
  const hash = useHash();
  return (
    <div className="page">
      <header className="header">
        <p className="brand">
          <a href="#/">UnderCover Claims</a>
          <span className="tagline">The claims queue</span>
        </p>
        <nav className="nav" aria-label="Main">
          <a href="#/">Queue</a>
          <a href="#/instructions">Agent instructions</a>
        </nav>
      </header>
      <main>
        <Page hash={hash} />
      </main>
    </div>
  );
}
