"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  activateGlobeRegion,
  createInitialGlobeState,
  INITIAL_CAMERA,
  returnToNationalView,
} from "@/lib/globe-controller.mjs";
import { loadCountiesForState, loadStateData } from "@/lib/data";
import type { Focus, GlobeSelectionState, Metric, RegionFeature } from "@/lib/types";
import { DataPanel } from "./data-panel";
import { GlobeStage } from "./globe-stage";

export function ColculatorExperience() {
  const [states, setStates] = useState<RegionFeature[]>([]);
  const [counties, setCounties] = useState<RegionFeature[]>([]);
  const [rpp, setRpp] = useState<Awaited<ReturnType<typeof loadStateData>>["rpp"]>();
  const [wages, setWages] = useState<Awaited<ReturnType<typeof loadStateData>>["wages"]>();
  const [rppYear, setRppYear] = useState<number | null>(null);
  const [wageYear, setWageYear] = useState<number | null>(null);
  const [metric, setMetric] = useState<Metric>("cost");
  const [selection, setSelection] = useState<GlobeSelectionState>(
    () => createInitialGlobeState() as GlobeSelectionState,
  );
  const [camera, setCamera] = useState<Focus>(INITIAL_CAMERA);
  const [cameraRevision, setCameraRevision] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);
  const [loadingCounties, setLoadingCounties] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const countyRequest = useRef(0);

  useEffect(() => {
    let active = true;
    loadStateData()
      .then((data) => {
        if (!active) return;
        setStates(data.states);
        setRpp(data.rpp);
        setWages(data.wages);
        setRppYear(data.rppYear);
        setWageYear(data.wageYear);
      })
      .catch(() => active && setError("The map data could not be loaded."));
    return () => { active = false; };
  }, []);

  const visibleRegions = selection.level === "counties" && counties.length ? counties : states;
  const selectedFeature = useMemo(
    () =>
      [...states, ...counties].find(
        (region) =>
          region.properties.id === (selection.selectedCountyId ?? selection.selectedStateId),
      ) ?? null,
    [counties, selection.selectedCountyId, selection.selectedStateId, states],
  );

  async function activate(feature: RegionFeature) {
    const region = feature.properties;
    const result = activateGlobeRegion(selection, {
      id: region.id,
      name: region.name,
      type: region.type,
      interactive: region.interactive,
      parentRegionId: region.parentRegionId,
      focus: region.focus,
    });
    setNotice(result.notice);
    if (result.camera) {
      setCamera(result.camera);
      setCameraRevision((revision) => revision + 1);
    }
    setSelection(result.state as GlobeSelectionState);

    if (region.type === "state" && rpp && wages) {
      const request = ++countyRequest.current;
      setLoadingCounties(true);
      setCounties([]);
      try {
        const nextCounties = await loadCountiesForState(region.id, rpp, wages);
        if (request === countyRequest.current) setCounties(nextCounties);
      } catch {
        if (request === countyRequest.current) {
          setError(`County boundaries for ${region.name} could not be loaded.`);
        }
      } finally {
        if (request === countyRequest.current) setLoadingCounties(false);
      }
    }
  }

  function resetView() {
    countyRequest.current += 1;
    const result = returnToNationalView(selection);
    setSelection(result.state as GlobeSelectionState);
    setCamera(result.camera);
    setCameraRevision((revision) => revision + 1);
    setCounties([]);
    setNotice(null);
  }

  return (
    <main className="experience-shell">
      <header className="site-header">
        <a className="wordmark" href="#top" aria-label="Colculator home">
          <span className="wordmark-orbit" aria-hidden="true" />
          Colculator
        </a>
        <div className="edition">U.S. terrain / 2026 edition</div>
        <a className="method-link" href="#method">Methodology <span>↗</span></a>
      </header>

      <section id="top" className="instrument-grid" aria-labelledby="page-title">
        <div className="story-rail">
          <div className="rail-index">01</div>
          <p className="eyebrow">Salary, corrected for place</p>
          <h1 id="page-title">
            What is your work
            <span>worth, elsewhere?</span>
          </h1>
          <p className="lede">
            A geographic instrument for software salaries. Rotate the world, then
            enter the United States to compare official and modeled local costs.
          </p>
          <div className="metric-control" role="group" aria-label="Map metric">
            <span>Surface encodes</span>
            <div>
              <button
                type="button"
                aria-pressed={metric === "cost"}
                onClick={() => setMetric("cost")}
              >
                Cost index
              </button>
              <button
                type="button"
                aria-pressed={metric === "wage"}
                onClick={() => setMetric("wage")}
              >
                SWE wage
              </button>
            </div>
          </div>
          <div className="legend" aria-label="Data provenance legend">
            <span><i className="legend-official" /> Official BEA</span>
            <span><i className="legend-modeled" /> Modeled</span>
          </div>
        </div>

        <div className="globe-column">
          <div className="globe-toolbar">
            <AnimatePresence mode="wait">
              <motion.div
                key={selection.level}
                initial={{ opacity: 0, x: -12 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 12 }}
              >
                <span className="live-dot" />
                {selection.level === "states" ? "National field" : selectedFeature?.properties.name ?? "County field"}
              </motion.div>
            </AnimatePresence>
            {selection.level === "counties" ? (
              <button type="button" onClick={resetView}>← All states</button>
            ) : (
              <span>Drag anywhere to rotate</span>
            )}
          </div>
          <GlobeStage
            regions={visibleRegions}
            metric={metric}
            selectedId={selection.selectedCountyId ?? selection.selectedStateId}
            camera={camera}
            cameraRevision={cameraRevision}
            onActivate={activate}
          />
          {loadingCounties ? <div className="county-loader">Resolving county field…</div> : null}
          <AnimatePresence>
            {notice ? (
              <motion.button
                type="button"
                className="coverage-notice"
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 16 }}
                onClick={() => setNotice(null)}
              >
                {notice}<span aria-hidden="true">×</span>
              </motion.button>
            ) : null}
          </AnimatePresence>
        </div>

        <DataPanel selection={selectedFeature} rppYear={rppYear} wageYear={wageYear} />
      </section>

      {error ? <div className="error-banner" role="alert">{error}</div> : null}

      <footer id="method" className="site-footer">
        <p>
          Price parity: U.S. Bureau of Economic Analysis · Wages: U.S. Bureau of Labor Statistics · World boundaries: Natural Earth
        </p>
        <p>
          County model inputs include Zillow Research data. <a href="https://www.zillow.com/research/data/" target="_blank" rel="noreferrer">Zillow attribution</a>
        </p>
      </footer>
    </main>
  );
}
