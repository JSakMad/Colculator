"use client";

import { AnimatePresence, motion } from "motion/react";

import type { RegionFeature } from "@/lib/types";

const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

export function DataPanel({
  selection,
  rppYear,
  wageYear,
}: {
  selection: RegionFeature | null;
  rppYear: number | null;
  wageYear: number | null;
}) {
  return (
    <aside className="data-panel" aria-live="polite" aria-label="Selected region data">
      <div className="panel-index" aria-hidden="true">02</div>
      <AnimatePresence mode="wait">
        {selection ? (
          <motion.div
            key={selection.properties.id}
            className="selection-readout"
            initial={{ opacity: 0, y: 22 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            transition={{ duration: 0.42, ease: [0.22, 1, 0.36, 1] }}
          >
            <p className="eyebrow">
              {selection.properties.type === "county" ? "County signal" : "State signal"}
            </p>
            <h2>{selection.properties.name}</h2>
            {selection.properties.abbreviation ? (
              <p className="region-code">US / {selection.properties.abbreviation}</p>
            ) : null}

            <div className="primary-reading">
              <span>Regional price parity</span>
              <strong>
                {selection.properties.rpp === null
                  ? "Unavailable"
                  : selection.properties.rpp.toFixed(1)}
              </strong>
              <small>U.S. average = 100 · {rppYear ?? "latest"}</small>
            </div>

            <dl className="signal-list">
              <div>
                <dt>Housing RPP</dt>
                <dd>
                  {selection.properties.rppHousing === null
                    ? "Unavailable"
                    : selection.properties.rppHousing.toFixed(1)}
                </dd>
              </div>
              <div>
                <dt>Software developer median</dt>
                <dd>
                  {selection.properties.medianWage === null
                    ? "Unavailable"
                    : currency.format(selection.properties.medianWage)}
                </dd>
              </div>
            </dl>

            <div className={`source-block source-${selection.properties.source}`}>
              <span className="source-mark" aria-hidden="true" />
              <div>
                <strong>
                  {selection.properties.source === "official_bea"
                    ? "Official BEA measure"
                    : selection.properties.source === "modeled"
                      ? "Modeled county estimate"
                      : "Price data unavailable"}
                </strong>
                <p>
                  {selection.properties.source === "modeled"
                    ? "Estimated only where no official metro RPP exists."
                    : selection.properties.source === "official_bea"
                      ? `Price data ${rppYear ?? "latest"}; wage data ${wageYear ?? "latest"}.`
                      : "No value is substituted or guessed."}
                </p>
              </div>
            </div>

            {selection.properties.confidenceInterval ? (
              <div className="confidence-band">
                <span>95% confidence interval</span>
                <strong>
                  {selection.properties.confidenceInterval.lower.toFixed(1)}–
                  {selection.properties.confidenceInterval.upper.toFixed(1)}
                </strong>
              </div>
            ) : null}

            <div className="destination-field">
              <span>Calculator destination</span>
              <output>{selection.properties.name}</output>
              <small>
                {selection.properties.type === "county"
                  ? "Ready for salary comparison"
                  : "Choose a county to set a precise destination"}
              </small>
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="empty"
            className="panel-empty"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <p className="eyebrow">Reading the terrain</p>
            <h2>Select a state.</h2>
            <p>
              The surface rises with the selected economic signal. Enter a state,
              then choose a county for the most precise available measure.
            </p>
            <ol>
              <li><span>01</span> Drag to rotate</li>
              <li><span>02</span> Scroll to approach</li>
              <li><span>03</span> Select the U.S.</li>
            </ol>
          </motion.div>
        )}
      </AnimatePresence>
    </aside>
  );
}
