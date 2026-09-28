"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";

import type { Focus, Metric, RegionFeature } from "@/lib/types";
import { FlatMap } from "./flat-map";

const GlobeStage3D = dynamic(
  () => import("./globe-stage-3d").then((module) => module.GlobeStage3D),
  { ssr: false },
);

function useReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  return reduced;
}

export function GlobeStage({
  regions,
  metric,
  selectedId,
  camera,
  cameraRevision,
  onActivate,
}: {
  regions: RegionFeature[];
  metric: Metric;
  selectedId: string | null;
  camera: Focus;
  cameraRevision: number;
  onActivate: (feature: RegionFeature) => void;
}) {
  const frame = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 900, height: 760 });
  const [ready, setReady] = useState(false);
  const reducedMotion = useReducedMotion();

  useEffect(() => {
    if (!frame.current) return;
    const observer = new ResizeObserver(([entry]) => {
      setSize({ width: entry.contentRect.width, height: entry.contentRect.height });
    });
    observer.observe(frame.current);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={frame} className="globe-frame" data-ready={ready}>
      <div className="orbital-rule" aria-hidden="true" />
      {!ready && !reducedMotion ? (
        <div className="globe-loading" role="status">
          <span />
          Plotting 3,144 counties
        </div>
      ) : null}
      {reducedMotion ? (
        <FlatMap
          regions={regions}
          metric={metric}
          selectedId={selectedId}
          onActivate={onActivate}
        />
      ) : (
        <GlobeStage3D
          width={size.width}
          height={size.height}
          regions={regions}
          metric={metric}
          selectedId={selectedId}
          camera={camera}
          cameraRevision={cameraRevision}
          onActivate={onActivate}
          onReady={() => setReady(true)}
        />
      )}
    </div>
  );
}
