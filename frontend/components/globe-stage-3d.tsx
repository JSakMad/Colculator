"use client";

import { useEffect, useMemo, useRef } from "react";
import Globe, { type GlobeMethods } from "react-globe.gl";
import { feature } from "topojson-client";
import worldTopology from "world-atlas/countries-110m.json";

import { metricValue } from "@/lib/data";
import type { Focus, Metric, RegionFeature, RegionProperties } from "@/lib/types";

type WorldProperties = RegionProperties & { type: "country" };
type DisplayFeature = RegionFeature & { properties: RegionProperties | WorldProperties };

const worldFeatures = (
  feature(worldTopology as never, (worldTopology as never as { objects: { countries: never } }).objects.countries) as unknown as {
    features: Array<{ id?: string | number; properties?: { name?: string }; geometry: RegionFeature["geometry"] }>;
  }
).features
  .filter((country) => String(country.id) !== "840")
  .map(
    (country) =>
      ({
        ...country,
        properties: {
          id: `COUNTRY-${country.id}`,
          name: country.properties?.name ?? "International region",
          type: "country",
          countryCode: String(country.id),
          interactive: false,
          focus: { lat: 0, lng: 0 },
          rpp: null,
          rppHousing: null,
          medianWage: null,
          source: "unavailable",
        },
      }) as DisplayFeature,
  );

function interpolateColor(value: number | null, min: number, max: number) {
  if (value === null) return "rgba(96, 112, 124, .52)";
  const t = Math.max(0, Math.min(1, (value - min) / (max - min || 1)));
  const low = [62, 136, 148];
  const high = [239, 110, 66];
  const rgb = low.map((channel, index) =>
    Math.round(channel + (high[index] - channel) * t),
  );
  return `rgb(${rgb.join(",")})`;
}

export function GlobeStage3D({
  width,
  height,
  regions,
  metric,
  selectedId,
  camera,
  cameraRevision,
  onActivate,
  onReady,
}: {
  width: number;
  height: number;
  regions: RegionFeature[];
  metric: Metric;
  selectedId: string | null;
  camera: Focus;
  cameraRevision: number;
  onActivate: (feature: DisplayFeature) => void;
  onReady: () => void;
}) {
  const globe = useRef<GlobeMethods | undefined>(undefined);
  const display = useMemo(() => [...worldFeatures, ...regions], [regions]);
  const values = useMemo(
    () => regions.map((item) => metricValue(item, metric)).filter((value): value is number => value !== null),
    [metric, regions],
  );
  const min = values.length ? Math.min(...values) : 0;
  const max = values.length ? Math.max(...values) : 1;

  useEffect(() => {
    if (!globe.current) return;
    globe.current.pointOfView(camera, 1150);
  }, [camera, cameraRevision]);

  useEffect(() => () => {
    document.body.style.cursor = "default";
  }, []);

  const selected = regions.find((item) => item.properties.id === selectedId);
  const rings = selected ? [{ ...selected.properties.focus, maxR: 3.8 }] : [];

  return (
    <Globe
      ref={globe}
      width={width}
      height={height}
      backgroundColor="rgba(0,0,0,0)"
      animateIn
      showGlobe
      showGraticules
      showAtmosphere
      atmosphereColor="#78d8e0"
      atmosphereAltitude={0.14}
      polygonsData={display}
      polygonGeoJsonGeometry="geometry"
      polygonCapColor={(datum) => {
        const item = datum as DisplayFeature;
        if (!item.properties.interactive) return "rgba(27, 42, 50, .78)";
        if (item.properties.id === selectedId) return "#ffe8c5";
        if (item.properties.source === "modeled") return "rgba(239, 110, 66, .72)";
        return interpolateColor(metricValue(item as RegionFeature, metric), min, max);
      }}
      polygonSideColor={(datum) => {
        const item = datum as DisplayFeature;
        if (!item.properties.interactive) return "rgba(7, 16, 22, .85)";
        return item.properties.source === "modeled"
          ? "rgba(239, 110, 66, .28)"
          : "rgba(67, 169, 179, .32)";
      }}
      polygonStrokeColor={(datum) =>
        (datum as DisplayFeature).properties.source === "modeled"
          ? "#ef6e42"
          : (datum as DisplayFeature).properties.interactive
            ? "rgba(238, 244, 237, .66)"
            : "rgba(96, 123, 132, .22)"
      }
      polygonAltitude={(datum) => {
        const item = datum as DisplayFeature;
        if (!item.properties.interactive) return 0.003;
        const value = metricValue(item as RegionFeature, metric);
        const normalized = value === null ? 0 : (value - min) / (max - min || 1);
        return item.properties.id === selectedId ? 0.075 : 0.012 + normalized * 0.052;
      }}
      polygonLabel={(datum) => {
        const item = datum as DisplayFeature;
        if (!item.properties.interactive) return "";
        const value = metricValue(item as RegionFeature, metric);
        const formatted = value === null
          ? "Data unavailable"
          : metric === "cost"
            ? `${value.toFixed(1)} RPP`
            : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);
        const provenance = item.properties.source === "modeled" ? " · modeled" : "";
        return `<div class="globe-label"><strong>${item.properties.name}</strong><span>${formatted}${provenance}</span></div>`;
      }}
      polygonsTransitionDuration={900}
      onPolygonClick={(datum) => {
        const item = datum as DisplayFeature;
        if (item.properties.interactive && globe.current) {
          globe.current.controls().autoRotate = false;
        }
        onActivate(item);
      }}
      onPolygonHover={(datum) => {
        document.body.style.cursor =
          datum && (datum as DisplayFeature).properties.interactive ? "pointer" : "default";
      }}
      ringsData={rings}
      ringLat="lat"
      ringLng="lng"
      ringColor={() => (time: number) => `rgba(255, 216, 155, ${1 - time})`}
      ringMaxRadius="maxR"
      ringPropagationSpeed={1.9}
      ringRepeatPeriod={980}
      onGlobeReady={() => {
        if (!globe.current) return;
        const controls = globe.current.controls();
        controls.autoRotate = true;
        controls.autoRotateSpeed = 0.32;
        controls.enableDamping = true;
        controls.dampingFactor = 0.06;
        controls.minDistance = 112;
        controls.maxDistance = 460;
        globe.current.pointOfView(camera, 0);
        onReady();
      }}
    />
  );
}
