import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("design pass keeps provenance and Zillow attribution visible", async () => {
  const [calculator, dataPanel, sourceLedger] = await Promise.all([
    read("../components/accessible-calculator.tsx"),
    read("../components/data-panel.tsx"),
    read("../components/source-ledger.tsx"),
  ]);

  assert.match(calculator, /Official BEA/);
  assert.match(calculator, /Modeled estimate/);
  assert.match(dataPanel, /Modeled county estimate/);
  assert.match(sourceLedger, /Zillow Research/);
  assert.match(sourceLedger, /Required attribution/);
  assert.match(sourceLedger, /https:\/\/www\.zillow\.com\/research\/data\//);
});

test("design pass preserves reduced-motion and keyboard alternatives", async () => {
  const [experience, globeStage, styles] = await Promise.all([
    read("../components/colculator-experience.tsx"),
    read("../components/globe-stage.tsx"),
    read("../app/globals.css"),
  ]);

  assert.match(experience, /Skip the globe and use the calculator/);
  assert.match(globeStage, /prefers-reduced-motion: reduce/);
  assert.match(globeStage, /<FlatMap/);
  assert.match(styles, /@media \(prefers-reduced-motion: reduce\)/);
  assert.match(styles, /\.skip-link:focus/);
});

test("offer comparison exposes assumptions, sources, and the official baseline", async () => {
  const [calculator, sourceLedger] = await Promise.all([
    read("../components/accessible-calculator.tsx"),
    read("../components/source-ledger.tsx"),
  ]);

  assert.match(calculator, /Estimated take-home/);
  assert.match(calculator, /Comparable purchasing power/);
  assert.match(calculator, /Official purchasing-power baseline/);
  assert.match(calculator, /Zillow is a registered trademark/);
  assert.match(calculator, /IRS federal/);
  assert.match(calculator, /Tax Foundation state/);
  assert.match(calculator, /RPP confidence interval/);
  assert.match(calculator, /result\.origin\.rpp_source === "modeled" \|\| result\.destination\.rpp_source === "modeled"/);
  assert.match(calculator, /Offer B break-even salary:/);
  assert.match(sourceLedger, /New York Tax/);
});
