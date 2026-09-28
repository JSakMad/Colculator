"use client";

import { geoAlbersUsa, geoPath } from "d3-geo";
import { useMemo } from "react";

import { metricValue } from "@/lib/data";
import type { Metric, RegionFeature } from "@/lib/types";

export function FlatMap({
  regions,
  metric,
  selectedId,
  onActivate,
}: {
  regions: RegionFeature[];
  metric: Metric;
  selectedId: string | null;
  onActivate: (feature: RegionFeature) => void;
}) {
  const paths = useMemo(() => {
    const projection = geoAlbersUsa().fitExtent(
      [[24, 24], [936, 576]],
      { type: "FeatureCollection", features: regions },
    );
    const path = geoPath(projection);
    return regions.map((region) => ({ region, d: path(region) ?? "" }));
  }, [regions]);
  const values = regions
    .map((region) => metricValue(region, metric))
    .filter((value): value is number => value !== null);
  const min = values.length ? Math.min(...values) : 0;
  const max = values.length ? Math.max(...values) : 1;

  return (
    <div className="flat-map" role="group" aria-label="Reduced-motion U.S. region map">
      <svg viewBox="0 0 960 600" role="img" aria-labelledby="flat-map-title">
        <title id="flat-map-title">Interactive cost of living map of the United States</title>
        {paths.map(({ region, d }) => {
          const value = metricValue(region, metric);
          const level = value === null ? 0 : (value - min) / (max - min || 1);
          return (
            <path
              key={region.properties.id}
              d={d}
              className={region.properties.id === selectedId ? "is-selected" : ""}
              style={{
                "--map-fill": `hsl(${188 - level * 170} 48% ${34 + level * 22}%)`,
              } as React.CSSProperties}
              tabIndex={0}
              role="button"
              aria-label={`Select ${region.properties.name}`}
              onClick={() => onActivate(region)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") onActivate(region);
              }}
            />
          );
        })}
      </svg>
      <p>Motion is reduced on this device. The same regions remain selectable.</p>
    </div>
  );
}
