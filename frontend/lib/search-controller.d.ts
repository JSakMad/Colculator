export type SearchCandidate = {
  id: string;
  label: string;
  kind: "state" | "county" | "city";
  regionId: string;
  stateRegionId: string;
  source: "census_catalog" | "census_tigerweb_geocoder";
  lat?: number;
  lng?: number;
};

export function rankCatalogCandidates(
  query: string,
  regions: Array<Record<string, string | null | undefined>>,
  stateNames?: Map<string, string>,
): SearchCandidate[];
export function mergeSearchCandidates(
  ...candidateGroups: SearchCandidate[][]
): SearchCandidate[];
export function searchOutcome(
  candidates: SearchCandidate[],
): "empty" | "single" | "disambiguation";
