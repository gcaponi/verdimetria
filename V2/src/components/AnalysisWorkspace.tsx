import { useState } from "react";
import {
  CalendarRange,
  CheckCircle2,
  CloudSun,
  Database,
  FlaskConical,
  Leaf,
  LayoutDashboard,
  LockKeyhole,
  Mountain,
  Satellite,
  Sparkles,
  Sprout,
} from "lucide-react";
import WeatherSection from "@/sections/WeatherSection";
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
        {activeTab === "overview" && <Overview area={area} />}
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
          />
        )}
        {activeTab === "geology" && (
          <GeologyAnalysis
            layers={layers}
            activeLayerId={activeLayerId}
            onLayerChange={onLayerChange}
          />
        )}
        {activeTab === "insights" && <InsightsAnalysis />}
        {activeTab === "weather" && <WeatherSection field={area} />}
      </div>
    </section>
  );
}

function Overview({ area }: { area: MapArea }) {
  const metrics = [
    { label: "Superficie", value: `${formatArea(area.area_ha)} ha`, detail: "calcolata dal confine" },
    { label: "Vertici", value: String(area.poly.length), detail: "geometria acquisita" },
    { label: "Meteo", value: "Live", detail: "Open-Meteo sul centroide" },
    { label: "Analisi zonali", value: "In attesa", detail: "endpoint backend non esposto" },
  ];

  return (
    <div className="space-y-5">
      <SectionHeading
        eyebrow="Stato del campo"
        title={`Panoramica — ${area.name}`}
        detail="Questa vista mostra solo dati effettivamente disponibili nel prototipo nazionale."
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
          items={["Confine e superficie", "Meteo live", "Layer visuali CDSE", "Proprietà SoilGrids 250 m"]}
        />
        <StatusPanel
          icon={LockKeyhole}
          tone="pending"
          title="Richiede backend"
          items={["Statistiche NDVI zonali", "Serie storica e debolezza", "Anomaly detection e PCA", "Interpretazione AI"]}
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
}: Omit<Props, "area">) {
  const vegetationIds = new Set(["NDVI", "EVI", "SAVI", "NDWI", "AGRICULTURE"]);
  const vegetationLayers = layers.filter((layer) => vegetationIds.has(layer.id));
  return (
    <div className="space-y-5">
      <SectionHeading
        eyebrow="Sentinel-2 · Copernicus Data Space"
        title="Vegetazione e umidità"
        detail="I preset WMS sono attivi per l'ispezione visuale; le misure NDVI richiedono la Process e Statistical API lato server."
      />
      <LayerGrid
        layers={vegetationLayers}
        activeLayerId={activeLayerId}
        onLayerChange={onLayerChange}
      />
      <EmptyAnalysis
        icon={CalendarRange}
        title="Andamento NDVI"
        detail="La pipeline Statistical API è stata validata live, ma il browser non può ricevere le credenziali OAuth. Il grafico attende l'endpoint autenticato che restituisca la serie del campo."
      />
      <EmptyAnalysis
        icon={Database}
        title="Distribuzione e debolezza cronica"
        detail="Istogramma, percentili e zone persistentemente deboli saranno calcolati sui pixel reali della serie, non su una distribuzione sintetica."
      />
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

function InsightsAnalysis() {
  return (
    <div className="space-y-5">
      <SectionHeading
        eyebrow="Interpretazione assistita"
        title="AI Insights"
        detail="Gli insight vengono generati solo dopo avere statistiche reali, provenienza e indicatori di confidenza."
      />
      <EmptyAnalysis
        icon={Sparkles}
        title="Nessun insight ancora generato"
        detail="Il prototipo precedente usava testi costruiti su misure sintetiche. Questa versione attende gli output quantitativi del backend prima di formulare diagnosi o raccomandazioni."
      />
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