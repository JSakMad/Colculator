import assert from "node:assert/strict";
import test from "node:test";

import { submitAccessibleCalculation } from "../lib/accessible-calculator.mjs";
import {
  rankCatalogCandidates,
  searchOutcome,
} from "../lib/search-controller.mjs";

test("ambiguous Washington search requires explicit disambiguation", () => {
  const regions = [
    { id: "US-STATE-53", type: "state", name: "Washington", abbreviation: "WA" },
    {
      id: "US-COUNTY-01129",
      type: "county",
      name: "Washington",
      parent_region_id: "US-STATE-01",
    },
    {
      id: "US-COUNTY-42125",
      type: "county",
      name: "Washington",
      parent_region_id: "US-STATE-42",
    },
  ];
  const stateNames = new Map([
    ["US-STATE-01", "Alabama"],
    ["US-STATE-42", "Pennsylvania"],
  ]);
  const candidates = rankCatalogCandidates("Washington", regions, stateNames);

  assert.equal(searchOutcome(candidates), "disambiguation");
  assert.deepEqual(
    candidates.map((candidate) => candidate.label),
    ["Washington", "Washington County, Alabama", "Washington County, Pennsylvania"],
  );
});

test("complete calculator flow runs independently of the globe component", async () => {
  let capturedRequest;
  const response = await submitAccessibleCalculation(
    {
      nominalSalary: "100000",
      originRegionId: "US-STATE-06",
      destinationRegionId: "US-COUNTY-53033",
      socCode: "15-1252",
      includeStateIncomeTax: false,
    },
    async (url, init) => {
      capturedRequest = { url, body: JSON.parse(init.body) };
      return {
        ok: true,
        json: async () => ({ adjusted_salary: 97321.45 }),
      };
    },
  );

  assert.equal(capturedRequest.url, "/api/calculate");
  assert.equal(capturedRequest.body.origin_region_id, "US-STATE-06");
  assert.equal(capturedRequest.body.destination_region_id, "US-COUNTY-53033");
  assert.equal(capturedRequest.body.nominal_salary, 100000);
  assert.equal(response.adjusted_salary, 97321.45);
});
