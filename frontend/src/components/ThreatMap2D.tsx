"use client";

import dynamic from "next/dynamic";
import type { IOCPoint } from "@/lib/types";

const LeafletMapImpl = dynamic(() => import("./LeafletMapImpl"), { ssr: false });

export default function ThreatMap2D({ points }: { points: IOCPoint[] }) {
  return <LeafletMapImpl points={points} />;
}
