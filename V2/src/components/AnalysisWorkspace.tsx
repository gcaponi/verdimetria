import { useEffect, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  CloudSun,
  FlaskConical,
  Leaf,
  LayoutDashboard,
  LockKeyhole,
  Mountain,
  RefreshCw,
  Satellite,
  Sparkles,
  Sprout,
} from "lucide-react";
import WeatherSection from "@/sections/WeatherSection";
import VegetationCharts from "@/sections/VegetationCharts";
import RealInsightsSection from "@/sections/RealInsightsSection";
import { analyzeArea } from "@/lib/analysis";
import type { AnalysisStatus, FieldAnalysis } from "@/lib/analysis";
import type { WmsLayer } from "@/lib/wms";
import type { MapArea } from "@/types";
import { cn } from "@/lib/utils";

type TabId = "overview" | "soil" | "vegetation" | "geology" | "insights" | "weather";

interface Props {
  area: MapArea;
  layers: WmsLayer[];
  activeLayerId: string;
  onLayerChange: (layerId: string) => void;
}

const TABS: Array<{ id: TabId; label: string; icon: typeof Leaf }> = [
  { id: "overview", label: "Panoramica", icon: LayoutDashboard },
  { id: "soil", label: "Suolo", icon: Sprout },
  { id: "vegetation", label: "Vegetazione", icon: Leaf },
  { id: "geology", label: "Geologia", icon: Mountain },
  { id: "insights", label: "AI Insights", icon: Sparkles },
  { id: "weather", label: "Meteo", icon: CloudSun },
];

export default function AnalysisWorkspace({
  area,
  layers,
  activeLayerId,
  onLayerChange,
}: Props) {
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const [requestVersion, setRequestVersion] = useState(0);
  const requestKey = `${area.id}:${requestVersion}:${area.poly.length}`;
  const [analysisState, setAnalysisState] = useState<{
    key: string;
    analysis: FieldAnalysis | null;
    status: AnalysisStatus;
    error: string | null;
  }>({ key: requestKey, analysis: null, status: "loading", error: null });
  const currentState = analysisState.key === requestKey
    ? analysisState
    : { key: requestKey, analysis: null, status: "loading" as const, error: null };
  const analysis = currentState.analysis;
  const analysisStatus = currentState.status;
  const analysisError = currentState.error;

  useEffect(() => {
    const controller = new AbortController();
    analyzeArea(area, controller.signal)
      .then((result) => {
        setAnalysisState({ key: requestKey, analysis: result, status: "ready", error: null });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setAnalysisState({
          key: requestKey,
          analysis: null,
          status: "error",
          error: error instanceof Error ? error.message : "Analisi non disponibile",
        });
      });
    return () => controller.abort();
  }, [area, requestKey]);

  return (
    <section className="border-y border-slate-800">
      <nav
        aria-label="Analisi del campo"
        className="flex gap-1 overflow-x-auto border-b border-slate-800 py-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {TABS.map((tab) => {
          const Icon = tab.icon;
          const active = tab.id === activeTab;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              aria-pressed={active}
              className={cn(
                "flex h-10 shrink-0 items-center gap-1.5 border-b-2 px-3 text-[12px] font-medium transition-colors",
                active
                  ? "border-lime-400 text-lime-300"
                  : "border-transparent text-slate-500 hover:text-slate-200"
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              {tab.label}
            </button>
          );
        })}
      </nav>

      <div className="py-5">
        <AnalysisRunStatus
          status={analysisStatus}
          analysis={analysis}
          error={analysisError}
          onRetry={() => setRequestVersion((version) => version + 1)}
        />
        {activeTab === "overview" && <Overview area={area} analysis={analysis} status={analysisStatus} />}
        {activeTab === "soil" && (
          <SoilAnalysis
            layers={layers}
            activeLayerId={activeLayerId}
            onLayerChange={onLayerChange}
          />
        )}
        {activeTab === "vegetation" && (
          <VegetationAnalysis
            layers={layers}
            activeLayerId={activeLayerId}
            onLayerChange={onLayerChange}
            analysis={analysis}
            status={analysisStatus}
            error={analysisError}
            onRetry={() => setRequestVersion((version) => version + 1)}
          />
        )}
        {activeTab === "geology" && (
          <GeologyAnalysis
            layers={layers}
            activeLayerId={activeLayerId}
            onLayerChange={onLayerChange}
          />
        )}
        {activeTab === "insights" && (
          <InsightsAnalysis
            analysis={analysis}
            status={analysisStatus}
            error={analysisError}
            onRetry={() => setRequestVersion((version) => version + 1)}
          />
        )}
        {activeTab === "weather" && <WeatherSection field={area} />}
      </div>
    </section>
  );
}

function Overview({
  area,
  analysis,
  status,
}: {
  area: MapArea;
  analysis: FieldAnalysis | null;
  status: AnalysisStatus;
}) {
  const metrics = [
    { label: "Superficie", value: `${formatArea(area.area_ha)} ha`, detail: "calcolata dal confine" },
    {
      label: "Scene Sentinel-2",
      value: analysis ? String(analysis.catalog.sceneCount) : status === "loading" ? "..." : "n/d",
      detail: "Catalog API · cloud <= 30%",
    },
    {
      label: "NDVI corrente",
      value: analysis?.vegetation.current?.toLocaleString("it-IT", { maximumFractionDigits: 3 }) ?? (status === "loading" ? "..." : "n/d"),
      detail: "Statistical API · pixel validi",
    },
    {
      label: "Interpretazione",
      value: analysis ? (analysis.ai.status === "generated" ? "AI" : "Regole") : status === "loading" ? "..." : "n/d",
      detail: analysis?.ai.model ?? "in elaborazione",
    },
  ];

  return (
    <div className="space-y-5">
      <SectionHeading
        eyebrow="Stato del campo"
        title={`Panoramica — ${area.name}`}
        detail="Geometria, scene, statistiche e interpretazione provengono dalla pipeline online sul Polygon selezionato."
      />
      <div className="grid gap-px overflow-hidden rounded-lg border border-slate-800 bg-slate-800 sm:grid-cols-2 xl:grid-cols-4">
        {metrics.map((metric) => (
          <div key={metric.label} className="min-h-28 bg-slate-950 p-4">
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">{metric.label}</p>
            <p className="mt-2 text-xl font-semibold text-slate-100">{metric.value}</p>
            <p className="mt-1 text-[11px] text-slate-500">{metric.detail}</p>
          </div>
        ))}
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <StatusPanel
          icon={CheckCircle2}
          tone="live"
          title="Disponibile ora"
          items={["Confine e superficie", "Catalog Sentinel-2", "Serie NDVI quantitativa", "AI con evidenze e provenance"]}
        />
        <StatusPanel
          icon={LockKeyhole}
          tone="pending"
          title="Richiede validazione campo"
          items={["Ground truth e laboratorio", "Diagnosi cause agronomiche", "Prescrizioni", "Validazione professionista"]}
        />
      </div>
    </div>
  );
}

function SoilAnalysis({
  layers,
  activeLayerId,
  onLayerChange,
}: Omit<Props, "area">) {
  const soilLayers = layers.filter((layer) => layer.group === "soil");
  return (
    <div className="space-y-5">
      <SectionHeading
        eyebrow="SoilGrids · 250 m · 0-5 cm"
        title="Contesto pedologico modellato"
        detail="I layer sono stime globali visuali con legenda ufficiale, non risultati di laboratorio del campo."
      />
      <LayerGrid
        layers={soilLayers}
        activeLayerId={activeLayerId}
        onLayerChange={onLayerChange}
      />
      <div className="border-l-2 border-amber-400/70 bg-amber-400/5 px-4 py-3 text-[12px] leading-relaxed text-slate-400">
        Fosforo disponibile e potassio scambiabile non sono proprietà SoilGrids. Rimangono nel catalogo
        come analisi in attesa di dati di laboratorio o di una fonte validata; non vengono stimati artificialmente.
      </div>
      <EmptyAnalysis
        icon={FlaskConical}
        title="Valori medi e tessitura del campo"
        detail="La tabella quantitativa tornerà quando un endpoint backend estrarrà valori, unità convertite e incertezza sul poligono selezionato."
      />
    </div>
  );
}

function VegetationAnalysis({
  layers,
  activeLayerId,
  onLayerChange,
  analysis,
  status,
  error,
  onRetry,
}: Omit<Props, "area"> & AnalysisResultProps) {
  const vegetationIds = new Set(["NDVI", "EVI", "SAVI", "NDWI", "AGRICULTURE"]);
  const vegetationLayers = layers.filter((layer) => vegetationIds.has(layer.id));
  return (
    <div className="space-y-5">
      <SectionHeading
        eyebrow="Sentinel-2 · Copernicus Data Space"
        title="Vegetazione e umidità"
        detail="I preset WMS supportano l'ispezione; i grafici usano Statistical API su Sentinel-2 L2A con masking qualità."
      />
      <LayerGrid
        layers={vegetationLayers}
        activeLayerId={activeLayerId}
        onLayerChange={onLayerChange}
      />
      <AnalysisResult status={status} analysis={analysis} error={error} onRetry={onRetry}>
        {(result) => <VegetationCharts analysis={result} />}
      </AnalysisResult>
    </div>
  );
}

function GeologyAnalysis({
  layers,
  activeLayerId,
  onLayerChange,
}: Omit<Props, "area">) {
  const geologyLayers = layers.filter((layer) => ["GEOLOGY", "ANOMALY", "PCA"].includes(layer.id));
  return (
    <div className="space-y-5">
      <SectionHeading
        eyebrow="Territorio e anomalie"
        title="Lettura geologica"
        detail="Il composito multispettrale CDSE è disponibile; anomalie, PCA e cartografia geologica autorevole sono ancora in integrazione."
      />
      <LayerGrid
        layers={geologyLayers}
        activeLayerId={activeLayerId}
        onLayerChange={onLayerChange}
      />
      <div className="grid gap-3 sm:grid-cols-2">
        <StatusPanel
          icon={Satellite}
          tone="live"
          title="Visuale disponibile"
          items={["Composito GEOLOGY CDSE", "Catalogo bande e indici WMS"]}
        />
        <StatusPanel
          icon={LockKeyhole}
          tone="pending"
          title="Analisi non calcolata"
          items={["Isolation Forest", "PCA multibanda", "Top anomalie", "Layer ISPRA/S.I.T.R."]}
        />
      </div>
    </div>
  );
}

function InsightsAnalysis({ analysis, status, error, onRetry }: AnalysisResultProps) {
  return (
    <div className="space-y-5">
      <SectionHeading
        eyebrow="Interpretazione assistita"
        title="AI Insights"
        detail="Il modello riceve solo statistiche CDSE aggregate e deve citare le evidenze usate."
      />
      <AnalysisResult status={status} analysis={analysis} error={error} onRetry={onRetry}>
        {(result) => <RealInsightsSection analysis={result} />}
      </AnalysisResult>
    </div>
  );
}

interface AnalysisResultProps {
  analysis: FieldAnalysis | null;
  status: AnalysisStatus;
  error: string | null;
  onRetry: () => void;
}

function AnalysisRunStatus({ status, analysis, error, onRetry }: AnalysisResultProps) {
  return (
    <div className="mb-5 flex min-h-12 flex-wrap items-center justify-between gap-3 border border-slate-800 bg-slate-900/50 px-4 py-3 text-[11px]">
      <div className="flex items-center gap-2">
        {status === "loading" ? (
          <RefreshCw className="h-4 w-4 animate-spin text-cyan-300" />
        ) : status === "ready" ? (
          <CheckCircle2 className="h-4 w-4 text-emerald-300" />
        ) : (
          <AlertCircle className="h-4 w-4 text-rose-300" />
        )}
        <span className="text-slate-300">
          {status === "loading"
            ? "Analisi reale in corso: Catalog + Statistical + AI"
            : status === "ready" && analysis
              ? `${analysis.vegetation.validObservations} intervalli validi · ${analysis.catalog.sceneCount} scene · ${analysis.ai.status === "generated" ? "AI generata" : "fallback trasparente"}`
              : error ?? "Analisi non disponibile"}
        </span>
      </div>
      {status === "error" && (
        <button type="button" onClick={onRetry} className="flex items-center gap-1.5 border border-slate-700 px-3 py-1.5 text-slate-200 hover:border-cyan-400/50 hover:text-cyan-200">
          <RefreshCw className="h-3.5 w-3.5" /> Riprova
        </button>
      )}
    </div>
  );
}

function AnalysisResult({
  status,
  analysis,
  error,
  onRetry,
  children,
}: AnalysisResultProps & { children: (analysis: FieldAnalysis) => React.ReactNode }) {
  if (status === "ready" && analysis) return children(analysis);
  if (status === "error") {
    return (
      <div className="flex min-h-40 items-center justify-between gap-4 border border-rose-400/30 bg-rose-400/5 p-5">
        <div>
          <h3 className="text-sm font-semibold text-rose-200">Analisi non completata</h3>
          <p className="mt-1 text-[12px] text-slate-400">{error}</p>
        </div>
        <button type="button" onClick={onRetry} className="shrink-0 border border-slate-700 px-3 py-2 text-[11px] text-slate-200 hover:border-rose-300/50">
          Riprova
        </button>
      </div>
    );
  }
  return (
    <div className="flex min-h-40 items-center gap-4 border border-dashed border-cyan-400/30 bg-cyan-400/5 p-5">
      <RefreshCw className="h-5 w-5 animate-spin text-cyan-300" />
      <div>
        <h3 className="text-sm font-semibold text-slate-200">Elaborazione del Polygon</h3>
        <p className="mt-1 text-[12px] text-slate-500">Ricerca scene, statistiche NDVI e interpretazione AI in corso.</p>
      </div>
    </div>
  );
}

function LayerGrid({
  layers,
  activeLayerId,
  onLayerChange,
}: {
  layers: WmsLayer[];
  activeLayerId: string;
  onLayerChange: (layerId: string) => void;
}) {
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {layers.map((layer) => {
        const active = layer.id === activeLayerId;
        const pending = layer.provider === "pending";
        return (
          <button
            key={layer.id}
            type="button"
            onClick={() => onLayerChange(layer.id)}
            disabled={pending}
            className={cn(
              "min-h-20 border px-3 py-3 text-left transition-colors",
              active
                ? "border-lime-400/50 bg-lime-400/10"
                : "border-slate-800 bg-slate-900/40 hover:border-slate-600",
              pending && "cursor-not-allowed opacity-55 hover:border-slate-800"
            )}
          >
            <span className="flex items-center justify-between gap-3">
              <span className={cn("text-[13px] font-semibold", active ? "text-lime-200" : "text-slate-200")}>{layer.label}</span>
              <span className="text-[9px] font-semibold uppercase text-slate-500">
                {pending ? "in attesa" : active ? "attivo" : layer.provider}
              </span>
            </span>
            <span className="mt-1 block text-[11px] leading-relaxed text-slate-500">{layer.detail}</span>
          </button>
        );
      })}
    </div>
  );
}

function EmptyAnalysis({
  icon: Icon,
  title,
  detail,
}: {
  icon: typeof Leaf;
  title: string;
  detail: string;
}) {
  return (
    <div className="flex min-h-40 items-center gap-4 border border-dashed border-slate-700 bg-slate-900/30 p-5">
      <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-slate-700 bg-slate-950 text-slate-500">
        <Icon className="h-5 w-5" />
      </span>
      <div>
        <h3 className="text-sm font-semibold text-slate-200">{title}</h3>
        <p className="mt-1 max-w-2xl text-[12px] leading-relaxed text-slate-500">{detail}</p>
      </div>
    </div>
  );
}

function StatusPanel({
  icon: Icon,
  tone,
  title,
  items,
}: {
  icon: typeof Leaf;
  tone: "live" | "pending";
  title: string;
  items: string[];
}) {
  return (
    <div className="border border-slate-800 bg-slate-900/40 p-4">
      <div className={cn("flex items-center gap-2 text-[12px] font-semibold", tone === "live" ? "text-emerald-300" : "text-amber-300")}>
        <Icon className="h-4 w-4" /> {title}
      </div>
      <ul className="mt-3 space-y-1.5 text-[11px] text-slate-500">
        {items.map((item) => (
          <li key={item} className="flex items-start gap-2">
            <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-slate-600" />
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function SectionHeading({
  eyebrow,
  title,
  detail,
}: {
  eyebrow: string;
  title: string;
  detail: string;
}) {
  return (
    <header>
      <p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-lime-400">{eyebrow}</p>
      <h2 className="mt-1 text-lg font-semibold text-slate-100">{title}</h2>
      <p className="mt-1 max-w-3xl text-[12px] leading-relaxed text-slate-500">{detail}</p>
    </header>
  );
}

function formatArea(areaHectares: number): string {
  return areaHectares.toLocaleString("it-IT", { maximumFractionDigits: 1 });
}