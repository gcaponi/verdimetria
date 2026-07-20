import type { MapArea } from "@/types";

export type AnalysisStatus = "loading" | "ready" | "error";

export interface NdviPoint {
  date: string;
  from: string;
  to: string;
  mean: number;
  min: number;
  max: number;
  stDev: number;
  p10: number | null;
  p50: number | null;
  p90: number | null;
  validPixels: number;
}

export interface AnalysisInsight {
  tone: "alert" | "warn" | "ok" | "info";
  title: string;
  text: string;
  evidence: string;
}

export interface FieldAnalysis {
  status: "ready";
  analysisId: string;
  generatedAt: string;
  period: { from: string; to: string };
  area: {
    hectares: number;
    centroid: [number, number];
    utmCrs: string;
    resolutionMeters: number;
  };
  catalog: {
    sceneCount: number;
    latestAcquisition: string | null;
    meanCloudCover: number | null;
    items: Array<{ id: string; acquiredAt: string; cloudCover: number | null }>;
  };
  vegetation: {
    points: NdviPoint[];
    current: number | null;
    average: number;
    min: number;
    max: number;
    trend: number | null;
    validObservations: number;
    totalValidPixels: number;
  };
  ai: {
    provider: string;
    model: string;
    status: "generated" | "fallback";
    summary: string;
    insights: AnalysisInsight[];
  };
  provenance: Array<{
    provider: string;
    dataset: string;
    services: string[];
    quality: string;
  }>;
  disclaimer: string;
}

export async function analyzeArea(area: MapArea, signal: AbortSignal): Promise<FieldAnalysis> {
  const firstPoint = area.poly[0];
  const coordinates = [...area.poly];
  const lastPoint = coordinates.at(-1);
  if (lastPoint?.[0] !== firstPoint[0] || lastPoint[1] !== firstPoint[1]) {
    coordinates.push(firstPoint);
  }

  const response = await fetch("/api/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      geometry: { type: "Polygon", coordinates: [coordinates] },
    }),
    signal,
  });
  const payload: unknown = await response.json();
  if (!response.ok) {
    const message = isRecord(payload) && typeof payload.error === "string"
      ? payload.error
      : `Analisi non disponibile (${response.status})`;
    throw new Error(message);
  }
  return payload as FieldAnalysis;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}