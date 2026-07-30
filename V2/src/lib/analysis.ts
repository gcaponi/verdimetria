import { getApiBaseUrl } from "@/lib/auth";
import { FieldsApiError } from "@/lib/fields";
import type { MapArea, NdmiBlock, VariabilityBlock } from "@/types";

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
  ndmi?: NdmiBlock | null;
  variability?: VariabilityBlock | null;
  terrain: {
    elevation: { min: number; max: number; mean: number };
    slope: { mean: number; max: number };
    aspectDominant: string | null;
    resolutionMeters: number;
    source?: string;
    validPixels: number;
  };
  landCover?: {
    year: number;
    source: string;
    resolutionMeters: number;
    dominantClass: number;
    classes: Array<{ code: number; label: string; share: number; hectares: number }>;
    validPixels: number;
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

type JobStatus = "pending" | "running" | "completed" | "failed";

interface AnalysisJob {
  id: string;
  status: JobStatus;
  progress_step: string;
  result: FieldAnalysis | null;
  error: string;
}

const POLL_INTERVAL_MS = 3_000;
const POLL_TIMEOUT_MS = 5 * 60_000;

export async function analyzeArea(
  area: MapArea,
  authorization: string,
  signal: AbortSignal,
): Promise<FieldAnalysis> {
  const job = await jobRequest<AnalysisJob>(
    `/api/v1/fields/${area.id}/jobs/`,
    authorization,
    { method: "POST", body: JSON.stringify({}), signal },
  );
  return waitForJobResult(job, authorization, signal);
}

async function waitForJobResult(
  job: AnalysisJob,
  authorization: string,
  signal: AbortSignal,
): Promise<FieldAnalysis> {
  const deadline = Date.now() + POLL_TIMEOUT_MS;
  let current = job;
  for (;;) {
    if (current.status === "completed" && current.result) return current.result;
    if (current.status === "failed") {
      throw new Error(current.error || "Analisi non completata");
    }
    if (Date.now() >= deadline) {
      throw new Error("Analisi troppo lenta: riprova tra poco");
    }
    await sleep(POLL_INTERVAL_MS, signal);
    current = await jobRequest<AnalysisJob>(
      `/api/v1/jobs/${current.id}/`,
      authorization,
      { signal },
    );
  }
}

async function jobRequest<T>(
  path: string,
  authorization: string,
  init: RequestInit,
): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: authorization,
    },
  });
  if (!response.ok) throw await readJobError(response);
  return (await response.json()) as T;
}

async function readJobError(response: Response): Promise<FieldsApiError> {
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  const message =
    typeof payload === "object" && payload !== null && "detail" in payload
      ? String((payload as { detail: unknown }).detail)
      : `Analisi non disponibile (${response.status})`;
  return new FieldsApiError(message, response.status);
}

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    };
    signal.addEventListener("abort", onAbort, { once: true });
  });
}
