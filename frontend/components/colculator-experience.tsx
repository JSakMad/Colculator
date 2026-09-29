"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  activateGlobeRegion,
  createInitialGlobeState,
  INITIAL_CAMERA,
  returnToNationalView,
} from "@/lib/globe-controller.mjs";
import { loadCountiesForState, loadRegionCatalog, loadStateData } from "@/lib/data";
import type {
  Focus,
  GlobeSelectionState,
  Metric,
  RegionCatalogEntry,
  RegionFeature,
  SearchCandidate,
} from "@/lib/types";
import { AccessibleCalculator } from "./accessible-calculator";
import { DataPanel } from "./data-panel";
import { GlobeStage } from "./globe-stage";
import { LocationSearch } from "./location-search";
import { SourceLedger } from "./source-ledger";

export function ColculatorExperience() {
  const [states, setStates] = useState<RegionFeature[]>([]);
  const [counties, setCounties] = useState<RegionFeature[]>([]);
  const [catalog, setCatalog] = useState<RegionCatalogEntry[]>([]);
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
    Promise.all([loadStateData(), loadRegionCatalog()])
      .then(([data, nextCatalog]) => {
        if (!active) return;
        setStates(data.states);
        setCatalog(nextCatalog);
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

  async function focusSearchCandidate(candidate: SearchCandidate) {
    const catalogRegion = catalog.find((region) => region.id === candidate.regionId);
    if (!catalogRegion) {
      setError(`No Colculator region is available for ${candidate.label}.`);
      return;
    }

    if (catalogRegion.type === "state") {
      const stateFeature = states.find((state) => state.properties.id === catalogRegion.id);
      if (!stateFeature) return;
      const result = activateGlobeRegion(selection, {
        id: stateFeature.properties.id,
        name: stateFeature.properties.name,
        type: "state",
        interactive: true,
        focus: stateFeature.properties.focus,
      });
      setSelection({
        ...(result.state as GlobeSelectionState),
        destinationRegionId: catalogRegion.id,
      });
      if (result.camera) {
        setCamera(result.camera);
        setCameraRevision((revision) => revision + 1);
      }
      if (rpp && wages) {
        const request = ++countyRequest.current;
        setLoadingCounties(true);
        try {
          const nextCounties = await loadCountiesForState(catalogRegion.id, rpp, wages);
          if (request === countyRequest.current) setCounties(nextCounties);
        } catch (caught) {
          setError(caught instanceof Error ? caught.message : "That location could not be focused.");
        } finally {
          if (request === countyRequest.current) setLoadingCounties(false);
        }
      }
      return;
    }

    if (catalogRegion.type === "county" && catalogRegion.parent_region_id && rpp && wages) {
      const request = ++countyRequest.current;
      setLoadingCounties(true);
      try {
        const nextCounties = await loadCountiesForState(
          catalogRegion.parent_region_id,
          rpp,
          wages,
        );
        if (request !== countyRequest.current) return;
        setCounties(nextCounties);
        const county = nextCounties.find((item) => item.properties.id === catalogRegion.id);
        if (!county) throw new Error("County geometry is unavailable.");
        const result = activateGlobeRegion(selection, {
          id: county.properties.id,
          name: county.properties.name,
          type: "county",
          parentRegionId: county.properties.parentRegionId,
          interactive: true,
          focus:
            candidate.lat !== undefined && candidate.lng !== undefined
              ? { lat: candidate.lat, lng: candidate.lng, altitude: 0.13 }
              : county.properties.focus,
        });
        setSelection(result.state as GlobeSelectionState);
        if (result.camera) {
          setCamera(result.camera);
          setCameraRevision((revision) => revision + 1);
        }
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "That location could not be focused.");
      } finally {
        if (request === countyRequest.current) setLoadingCounties(false);
      }
    }
  }

  function focusAccessibleDestination(regionId: string) {
    const region = catalog.find((item) => item.id === regionId);
    if (!region) return;
    void focusSearchCandidate({
      id: region.id,
      label: region.name,
      kind: region.type === "county" ? "county" : "state",
      regionId: region.id,
      stateRegionId: region.type === "county" ? region.parent_region_id ?? "" : region.id,
      source: "census_catalog",
    });
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
      <a className="skip-link" href="#calculator">Skip the globe and use the calculator</a>
      <header className="site-header">
        <a className="wordmark" href="#top" aria-label="Colculator home">
          <span className="wordmark-orbit" aria-hidden="true" />
          Colculator
        </a>
        <div className="edition"><span aria-hidden="true" /> U.S. terrain / 2026 edition</div>
        <nav className="site-nav" aria-label="Primary navigation">
          <a href="#top">Field</a>
          <a href="#calculator">Compare</a>
          <a href="#sources">Sources</a>
        </nav>
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
          <div className="field-note" aria-label="Coverage summary">
            <span>Coverage</span>
            <strong>50 states + D.C.</strong>
            <small>3,144 county geometries</small>
          </div>
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
          <div className="globe-reticle" aria-hidden="true">
            <span className="reticle-horizontal" />
            <span className="reticle-vertical" />
            <span className="reticle-scan" />
            <i className="reticle-north">N</i>
            <i className="reticle-east">E</i>
          </div>
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
          <LocationSearch onSelect={focusSearchCandidate} />
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
          <div className="globe-footnote" aria-hidden="true">
            <span>RPP datum / U.S. = 100</span>
            <span>Drag · scroll · select</span>
          </div>
        </div>

        <DataPanel selection={selectedFeature} rppYear={rppYear} wageYear={wageYear} />
      </section>

      {error ? <div className="error-banner" role="alert">{error}</div> : null}

      <AccessibleCalculator
        regions={catalog}
        destinationRegionId={selection.destinationRegionId}
        onDestinationChange={focusAccessibleDestination}
      />

      <SourceLedger />

      <footer id="method" className="site-footer">
        <a className="wordmark footer-wordmark" href="#top" aria-label="Back to top">
          <span className="wordmark-orbit" aria-hidden="true" />
          Colculator
        </a>
        <p>A personal geographic instrument for software salary decisions.</p>
        <p>World boundaries: <a href="https://www.naturalearthdata.com/" target="_blank" rel="noreferrer">Natural Earth</a></p>
      </footer>
    </main>
  );
}
