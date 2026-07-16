import { useEffect, useMemo, useState } from "react";
import { useAppData, fmt } from "@/lib/data";
import { loadGrids, type Grids } from "@/lib/grids";
import { buildCustomField, genNdviSeries } from "@/lib/customArea";
import { cn } from "@/lib/utils";
import MapPanel from "@/components/MapPanel";
import OverviewSection from "@/sections/OverviewSection";
import SoilSection from "@/sections/SoilSection";
import VegetationSection from "@/sections/VegetationSection";
import GeologySection from "@/sections/GeologySection";
import InsightsSection from "@/sections/InsightsSection";
import WeatherSection from "@/sections/WeatherSection";
import { Sprout, Download, FileText, Layers, ChevronDown, MapPin } from "lucide-react";
import type { FieldData } from "@/types";

const TABS = [
  { id: "overview", label: "Panoramica" },
  { id: "soil", label: "Suolo" },
  { id: "veg", label: "Vegetazione" },
  { id: "geo", label: "Geologia" },
  { id: "insights", label: "AI Insights" },
  { id: "weather", label: "Meteo" },
];

export default function Home() {
  const { data, error } = useAppData();
  const [tab, setTab] = useState("overview");
  const [fieldId, setFieldId] = useState<string | null>(null);
  const [layerId, setLayerId] = useState("ndvi");

  const [grids, setGrids] = useState<Grids | null>(null);
  const [customFields, setCustomFields] = useState<FieldData[]>([]);
  const [customSeries, setCustomSeries] = useState<Record<string, number[]>>({});

  useEffect(() => {
    loadGrids()
      .then(setGrids)
      .catch(() => setGrids(null));
  }, []);

  const viewData = useMemo(() => {
    if (!data) return null;
    return {
      ...data,
      fields: [...data.fields, ...customFields],
      timeseries: {
        dates: data.timeseries.dates,
        series: { ...data.timeseries.series, ...customSeries },
      },
    };
  }, [data, customFields, customSeries]);

  const field = useMemo<FieldData | null>(() => {
    if (!viewData) return null;
    return viewData.fields.find((f) => f.id === fieldId) ?? viewData.fields[0];
  }, [viewData, fieldId]);

  const handleCustomArea = (poly: [number, number][]) => {
    if (!grids || !data) return;
    const n = customFields.length + 1;
    const id = `CUSTOM-${n}`;
    const { field: f } = buildCustomField(poly, grids, id, `Area disegnata ${n}`);
    const seed = poly.reduce((s, p) => s + Math.round(p[0] * 1e4) * 31 + Math.round(p[1] * 1e4), 7);
    const series = genNdviSeries(f.weakness, data.timeseries.dates, seed);
    setCustomFields((prev) => [...prev, f]);
    setCustomSeries((prev) => ({ ...prev, [id]: series }));
    setFieldId(id);
    setTab("overview");
  };

  if (error)
    return <div className="flex h-screen items-center justify-center bg-slate-950 text-rose-300">{error}</div>;
  if (!data || !viewData || !field)
    return (
      <div className="flex h-screen items-center justify-center bg-slate-950">
        <div className="flex items-center gap-3 text-slate-400">
          <Sprout className="h-5 w-5 animate-pulse text-lime-400" />
          Caricamento dati territoriali…
        </div>
      </div>
    );

  const download = (name: string, content: string, type: string) => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([content], { type }));
    a.download = name;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const exportCsv = () => {
    const head = "id;campo;coltura;area_ha;ndvi;debolezza;N_mgkg;P_mgkg;K_mgkg;pH;SOM_pct;argilla_pct";
    const rows = viewData.fields.map((f) =>
      [f.id, f.name, f.crop, f.area_ha, f.ndvi, f.weakness, f.n, f.p, f.k, f.ph, f.som, f.clay].join(";")
    );
    download("ragusa_geo_intel_campi.csv", [head, ...rows].join("\n"), "text/csv");
  };

  const exportReport = () => {
    const r = field.ratings;
    const md = `# Rapporto di analisi — ${field.name}
**Ragusa Geo-Intelligence** · generato il ${new Date().toLocaleDateString("it-IT")}

- **Coltura:** ${field.crop}
- **Superficie:** ${field.area_ha} ha
- **NDVI medio:** ${fmt(field.ndvi, 3)} · **Debolezza cronica:** ${fmt(field.weakness, 3)} (${fmt(field.weak_frac * 100, 0)}% superficie critica)
- **Score anomalia geologica medio:** ${fmt(field.anomaly_mean, 3)}

## Analisi del suolo (medie zonali)

| Parametro | Valore | Valutazione |
|---|---|---|
| Azoto totale | ${fmt(field.n, 0)} mg/kg | ${r.n} |
| Fosforo accessibile | ${fmt(field.p, 1)} mg/kg | ${r.p} |
| Potassio scambiabile | ${fmt(field.k, 0)} mg/kg | ${r.k} |
| pH | ${fmt(field.ph, 2)} | ${r.ph} |
| Sostanza organica | ${fmt(field.som, 2)} % | ${r.som} |
| Tessitura | Sa ${fmt(field.sand, 0)} / Cl ${fmt(field.clay, 0)} / Si ${fmt(field.silt, 0)} | — |

## Insight automatici

${field.insights.map((i) => `- **${i.title}.** ${i.text}`).join("\n")}

---
*Prototipo su dati sintetici georeferenziati. Le stime sono ipotesi di lettura da validare con analisi di laboratorio e sopralluoghi.*
`;
    download(`rapporto_${field.id}.md`, md, "text/markdown");
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      {/* HEADER */}
      <header className="sticky top-0 z-[600] border-b border-slate-800 bg-slate-950/90 backdrop-blur">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-3 px-4 py-3">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-lime-400/15">
              <Sprout className="h-5 w-5 text-lime-400" />
            </div>
            <div>
              <div className="text-[15px] font-bold leading-tight">Ragusa Geo-Intelligence</div>
              <div className="flex items-center gap-1 text-[11px] leading-tight text-slate-500">
                <MapPin className="h-3 w-3" /> Libero consorzio di Ragusa · Sentinel-2 + SoilGrids + S.IT.R.
              </div>
            </div>
          </div>

          <div className="ml-auto flex flex-wrap items-center gap-2">
            <Select
              icon={<MapPin className="h-3.5 w-3.5" />}
              value={field.id}
              onChange={setFieldId}
              options={viewData.fields.map((f) => ({
                value: f.id,
                label: f.id.startsWith("CUSTOM") ? `✏️ ${f.name}` : `${f.name} — ${f.crop}`,
              }))}
            />
            <Select
              icon={<Layers className="h-3.5 w-3.5" />}
              value={layerId}
              onChange={setLayerId}
              options={[
                { value: "none", label: "Solo satellite" },
                ...data.manifest.layers.map((l) => ({ value: l.id, label: l.label })),
              ]}
            />
            <button
              onClick={exportCsv}
              className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-2 text-[12px] font-medium text-slate-300 transition-colors hover:border-slate-500 hover:text-white"
            >
              <Download className="h-3.5 w-3.5" /> CSV
            </button>
            <button
              onClick={exportReport}
              className="flex items-center gap-1.5 rounded-lg bg-lime-400 px-3 py-2 text-[12px] font-semibold text-slate-950 transition-colors hover:bg-lime-300"
            >
              <FileText className="h-3.5 w-3.5" /> Scarica rapporto
            </button>
          </div>
        </div>
      </header>

      {/* BODY */}
      <main className="mx-auto max-w-[1600px] gap-4 px-4 py-4 lg:grid lg:grid-cols-[minmax(0,1fr)_44%]">
        <div>
          {/* TABS */}
          <nav className="mb-4 flex gap-1 overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/60 p-1">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={cn(
                  "whitespace-nowrap rounded-lg px-4 py-2 text-[13px] font-medium transition-colors",
                  tab === t.id
                    ? "bg-lime-400/15 text-lime-300"
                    : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
                )}
              >
                {t.label}
              </button>
            ))}
          </nav>

          {tab === "overview" && <OverviewSection data={viewData} field={field} onSelectField={setFieldId} />}
          {tab === "soil" && <SoilSection data={viewData} field={field} activeLayerId={layerId} onLayerChange={setLayerId} />}
          {tab === "veg" && <VegetationSection data={viewData} field={field} activeLayerId={layerId} onLayerChange={setLayerId} />}
          {tab === "geo" && <GeologySection data={viewData} field={field} activeLayerId={layerId} onLayerChange={setLayerId} />}
          {tab === "insights" && <InsightsSection data={viewData} field={field} />}
          {tab === "weather" && <WeatherSection field={field} />}

          <footer className="mt-6 rounded-xl border border-slate-800/60 bg-slate-900/40 p-4 text-[11px] leading-relaxed text-slate-500">
            <strong className="text-slate-400">Prototipo dimostrativo.</strong> I layer
            territoriali sono griglie sintetiche georeferenziate sul bounding box di Ragusa
            (stessa filosofia del demo del PRD, hotspot iniettati inclusi, IsolationForest e PCA
            reali di scikit-learn). Meteo Open-Meteo in tempo reale. In produzione i raster
            arriveranno da Sentinel-2 Process API (CDSE), SoilGrids (ISRIC) e Geoportale S.IT.R. —
            la pipeline Python esistente si collega sostituendo solo il layer dati.
          </footer>
        </div>

        {/* MAPPA */}
        <div className="mt-4 lg:mt-0">
          <div className="sticky top-[72px] h-[520px] lg:h-[calc(100vh-96px)]">
            <MapPanel
              data={viewData}
              activeLayerId={layerId}
              selectedFieldId={field.id}
              onSelectField={setFieldId}
              drawEnabled={!!grids}
              onCustomArea={handleCustomArea}
            />
          </div>
        </div>
      </main>
    </div>
  );
}

function Select({
  icon,
  value,
  onChange,
  options,
}: {
  icon: React.ReactNode;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <div className="relative">
      <div className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500">
        {icon}
      </div>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="max-w-[240px] appearance-none truncate rounded-lg border border-slate-700 bg-slate-900 py-2 pl-8 pr-8 text-[12px] font-medium text-slate-200 outline-none transition-colors hover:border-slate-500 focus:border-lime-400/60"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" />
    </div>
  );
}
