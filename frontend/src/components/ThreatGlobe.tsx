"use client";

import dynamic from "next/dynamic";
import type { IOCPoint } from "@/lib/types";

// react-globe.gl touches the DOM/WebGL at import time, so it must never be
// server-rendered.
const Globe = dynamic(() => import("react-globe.gl"), { ssr: false });

export default function ThreatGlobe({ points }: { points: IOCPoint[] }) {
  return (
    <Globe
      backgroundColor="rgba(0,0,0,0)"
      globeImageUrl="//unpkg.com/three-globe/example/img/earth-dark.jpg"
      pointsData={points}
      pointLat="lat"
      pointLng="lng"
      pointLabel="label"
      pointColor={() => "#ff4d4f"}
      pointAltitude={0.01}
      pointRadius={0.35}
    />
  );
}
