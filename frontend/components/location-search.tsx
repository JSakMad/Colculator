"use client";

import { AnimatePresence, motion } from "motion/react";
import { useId, useState } from "react";

import type { SearchCandidate } from "@/lib/types";

export function LocationSearch({
  onSelect,
}: {
  onSelect: (candidate: SearchCandidate) => Promise<void> | void;
}) {
  const resultsId = useId();
  const [query, setQuery] = useState("");
  const [candidates, setCandidates] = useState<SearchCandidate[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function search(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setMessage("Enter at least two characters.");
      return;
    }
    setPending(true);
    setMessage(null);
    try {
      const response = await fetch(`/api/search?q=${encodeURIComponent(trimmed)}`);
      const payload = (await response.json()) as {
        outcome: "empty" | "single" | "disambiguation";
        candidates: SearchCandidate[];
      };
      if (!response.ok) throw new Error("Search is temporarily unavailable.");
      if (payload.outcome === "single") {
        setCandidates([]);
        setMessage(`Centering ${payload.candidates[0].label}`);
        await onSelect(payload.candidates[0]);
      } else if (payload.outcome === "disambiguation") {
        setCandidates(payload.candidates);
        setMessage(`Choose one of ${payload.candidates.length} matches.`);
      } else {
        setCandidates([]);
        setMessage("No supported U.S. location matched that search.");
      }
    } catch (error) {
      setCandidates([]);
      setMessage(error instanceof Error ? error.message : "Search is temporarily unavailable.");
    } finally {
      setPending(false);
    }
  }

  async function choose(candidate: SearchCandidate) {
    setQuery(candidate.label);
    setCandidates([]);
    setMessage(`Centering ${candidate.label}`);
    setPending(true);
    try {
      await onSelect(candidate);
    } catch {
      setMessage("That location could not be focused. Please try again.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="location-search">
      <form onSubmit={search} role="search">
        <label htmlFor="location-query">Find a U.S. location</label>
        <div className="search-line">
          <span aria-hidden="true">⌖</span>
          <input
            id="location-query"
            name="location"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="City, county, or state"
            autoComplete="off"
            aria-controls={candidates.length ? resultsId : undefined}
            aria-expanded={candidates.length > 0}
          />
          <button type="submit" disabled={pending}>
            {pending ? "Locating…" : "Locate"}
          </button>
        </div>
      </form>
      <div className="search-message" role="status">{message}</div>
      <AnimatePresence>
        {candidates.length ? (
          <motion.div
            id={resultsId}
            className="search-results"
            role="list"
            aria-label="Location matches"
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
          >
            {candidates.map((candidate) => (
              <button
                key={`${candidate.kind}-${candidate.id}`}
                type="button"
                onClick={() => choose(candidate)}
              >
                <span>{candidate.label}</span>
                <small>{candidate.kind}</small>
              </button>
            ))}
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
