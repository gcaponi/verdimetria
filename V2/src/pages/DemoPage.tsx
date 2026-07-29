import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { FlaskConical, Sprout } from "lucide-react";
import AnalysisWorkspace from "@/components/AnalysisWorkspace";
import { WMS_LAYERS } from "@/lib/wms";
import type { FieldAnalysis } from "@/lib/analysis";
import { getApiBaseUrl } from "@/lib/auth";
import type { MapArea } from "@/types";

interface DemoPayload {
  field: {
    id: string;
    name: string;
    boundary: {
      geometry:
        | { type: "Polygon"; coordinates: [number, number][][] }
        | { type: "MultiPolygon"; coordinates: [number, number][][][] };
      area_hectares: number;
    } | null;
  };
  analysis: FieldAnalysis;
  generatedAt: string;
}

function boundaryToMapArea(payload: DemoPayload): MapArea | null {
  const boundary = payload.field.boundary;
  if (!boundary) return null;
  const geometry = boundary.geometry;
  const ring =
    geometry.type === "Polygon"
      ? geometry.coordinates[0]
      : geometry.coordinates[0]?.[0];
  if (!ring || ring.length < 4) return null;
  const openRing = ring.slice(0, -1) as [number, number][];
  return {
    id: `demo-${payload.field.id}`,
    name: payload.field.name,
    poly: openRing,
    area_ha: boundary.area_hectares,
  };
}

export default function DemoPage() {
  const [state, setState] = useState<{
    status: "loading" | "ready" | "error";
    area: MapArea | null;
    analysis: FieldAnalysis | null;
    error: string | null;
  }>({ status: "loading", area: null, analysis: null, error: null });
  const [layerId, setLayerId] = useState("NDVI");

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${getApiBaseUrl()}/api/v1/demo/`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Campo dimostrativo non disponibile (${response.status})`);
        const payload = (await response.json()) as DemoPayload;
        const area = boundaryToMapArea(payload);
        if (!area) throw new Error("Confine del campo dimostrativo non valido");
        setState({ status: "ready", area, analysis: payload.analysis, error: null });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setState({
          status: "error",
          area: null,
          analysis: null,
          error: error instanceof Error ? error.message : "Demo non disponibile",
        });
      });
    return () => controller.abort();
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="sticky top-0 z-[600] border-b border-slate-800 bg-slate-950/90 backdrop-blur">
        <div className="flex w-full items-center gap-3 px-3 py-3 sm:px-4 xl:px-5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-lime-400/15">
            <Sprout className="h-5 w-5 text-lime-400" />
          </div>
          <div>
            <div className="text-[15px] font-bold leading-tight">Verdimetria</div>
            <div className="text-[11px] leading-tight text-slate-500">Il quaderno visivo del campo</div>
          </div>
          <div className="ml-auto">
            <Link
              to="/"
              className="rounded-lg bg-lime-400 px-4 py-2 text-[12px] font-semibold text-slate-950 transition-colors hover:bg-lime-300"
            >
              Analizza il tuo campo →
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1600px] px-3 py-4 sm:px-4 xl:px-5">
        <div className="mb-4 flex items-start gap-3 border border-amber-400/40 bg-amber-400/10 px-4 py-3 text-[12px] leading-relaxed text-amber-100">
          <FlaskConical className="mt-0.5 h-4 w-4 shrink-0" />
          <p>
            <strong>Campo dimostrativo.</strong> Questo e' un campo reale con dati satellitari
            reali (Sentinel-2, CLC+ Backbone, TINITALY) pre-calcolati: serve a mostrare cosa
            ottieni con Verdimetria. Non e' il tuo campo —{" "}
            <Link to="/" className="font-semibold underline hover:text-amber-50">
              registrati e analizza il tuo
            </Link>
            .
          </p>
        </div>

        {state.status === "loading" && (
          <div className="flex min-h-64 items-center justify-center border-y border-slate-800 text-sm text-slate-400">
            Caricamento del campo dimostrativo…
          </div>
        )}
        {state.status === "error" && (
          <div className="flex min-h-64 items-center justify-center border-y border-rose-400/30 text-sm text-rose-200">
            {state.error}
          </div>
        )}
        {state.status === "ready" && state.area && state.analysis && (
          <div className="grid gap-5 lg:grid-cols-2">
            <div className="min-w-0">
              <section className="border-y border-slate-800 py-5">
                <div className="text-[11px] font-medium uppercase text-lime-400">Campo dimostrativo</div>
                <div className="mt-2 flex flex-wrap items-end justify-between gap-4">
                  <h1 className="text-2xl font-semibold text-slate-100">{state.area.name}</h1>
                  <div className="text-right">
                    <div className="text-3xl font-bold text-slate-100">
                      {state.area.area_ha.toLocaleString("it-IT", { maximumFractionDigits: 1 })}
                    </div>
                    <div className="text-[11px] uppercase text-slate-500">ettari</div>
                  </div>
                </div>
              </section>
              <AnalysisWorkspace
                area={state.area}
                layers={WMS_LAYERS}
                activeLayerId={layerId}
                onLayerChange={setLayerId}
                precomputedAnalysis={state.analysis}
              />
            </div>
            <div className="sticky top-[72px] hidden h-[calc(100vh-96px)] lg:block">
              <DemoMap area={state.area} />
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

function DemoMap({ area }: { area: MapArea }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const map = L.map(containerRef.current, { zoomControl: true, attributionControl: true });
    L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      { maxZoom: 19 }
    ).addTo(map);
    L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
      { maxZoom: 19 }
    ).addTo(map);
    const latLngs = area.poly.map(([longitude, latitude]) => [latitude, longitude] as [number, number]);
    const polygon = L.polygon(latLngs, {
      color: "#a3e635",
      weight: 3,
      fillColor: "#a3e635",
      fillOpacity: 0.15,
    }).addTo(map);
    map.fitBounds(polygon.getBounds(), { padding: [24, 24] });
    return () => {
      map.remove();
    };
  }, [area]);

  return (
    <div className="relative h-full min-h-[420px] overflow-hidden rounded-lg border border-slate-800">
      <div ref={containerRef} className="h-full w-full" />
      <div className="absolute bottom-3 left-3 z-[500] rounded-md bg-slate-950/85 px-3 py-1.5 text-[11px] text-slate-200">
        {area.name} · {area.area_ha.toLocaleString("it-IT", { maximumFractionDigits: 1 })} ha
      </div>
    </div>
  );
}
