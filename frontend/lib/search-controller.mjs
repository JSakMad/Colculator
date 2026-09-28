function normalize(value) {
  return value
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
}

export function rankCatalogCandidates(query, regions, stateNames = new Map()) {
  const needle = normalize(query).replace(/\s+county$/, "");
  if (needle.length < 2) return [];

  return regions
    .filter((region) => region.type === "state" || region.type === "county")
    .map((region) => {
      const name = normalize(region.name);
      const abbreviation = normalize(region.abbreviation ?? "");
      const exact = name === needle || abbreviation === needle;
      const starts = name.startsWith(needle);
      if (!exact && !starts) return null;
      const stateName = region.parent_region_id
        ? stateNames.get(region.parent_region_id)
        : null;
      return {
        id: region.id,
        label:
          region.type === "county" && stateName
            ? `${region.name} County, ${stateName}`
            : region.name,
        kind: region.type,
        regionId: region.id,
        stateRegionId:
          region.type === "state" ? region.id : region.parent_region_id,
        source: "census_catalog",
        score: (exact ? 100 : 50) + (region.type === "state" ? 5 : 0),
      };
    })
    .filter(Boolean)
    .sort((a, b) => b.score - a.score || a.label.localeCompare(b.label))
    .slice(0, 10)
    .map(({ score: _score, ...candidate }) => candidate);
}

export function mergeSearchCandidates(...candidateGroups) {
  const seen = new Set();
  const merged = [];
  for (const candidate of candidateGroups.flat()) {
    const key = `${candidate.kind}:${candidate.id}`;
    if (seen.has(key)) continue;
    seen.add(key);
    merged.push(candidate);
  }
  return merged.slice(0, 12);
}

export function searchOutcome(candidates) {
  if (candidates.length === 0) return "empty";
  if (candidates.length === 1) return "single";
  return "disambiguation";
}
