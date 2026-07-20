import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { useDefaultLayout } from "react-resizable-panels";
import MapPanelNational from "@/components/MapPanelNational";
import LayerCatalog from "@/components/LayerCatalog";
import AnalysisWorkspace from "@/components/AnalysisWorkspace";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { loadCdseCatalog, WMS_LAYERS } from "@/lib/wms";
import {
  CloudSun,
  ChevronDown,
  Database,
  Download,
  Layers,
  Map,
  MapPin,
  Satellite,
  Sprout,
  Trash2,
} from "lucide-react";
import type { MapArea } from "@/types";

const TECHNICAL_DEMO_AREA: MapArea = {
  id: "DEMO-RG-01",
  name: "Demo tecnica Ragusa",
  poly: [
    [14.6, 36.92],
    [14.61, 36.92],
    [14.61, 36.93],
    [14.6, 36.93],
  ],
  area_ha: geodesicAreaHectares([
    [14.6, 36.92],
    [14.61, 36.92],
    [14.61, 36.93],
    [14.6, 36.93],
  ]),
};

const DESKTOP_LAYOUT_QUERY = "(min-width: 1024px)";
const DESKTOP_PANEL_IDS = ["data", "map"];

export default function HomeNational() {
  const [areas, setAreas] = useState<MapArea[]>([TECHNICAL_DEMO_AREA]);
  const [selectedAreaId, setSelectedAreaId] = useState<string | null>(TECHNICAL_DEMO_AREA.id);
  const [layerId, setLayerId] = useState("NDVI");
  const [layers, setLayers] = useState(WMS_LAYERS);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const isDesktopLayout = useDesktopLayout();
  const { defaultLayout, onLayoutChange } = useDefaultLayout({
    id: "verdimetria-workspace",
    panelIds: DESKTOP_PANEL_IDS,
  });

  useEffect(() => {
    const controller = new AbortController();
    loadCdseCatalog(controller.signal)
      .then((catalogLayers) => setLayers([...WMS_LAYERS, ...catalogLayers]))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setCatalogError(error instanceof Error ? error.message : "Catalogo CDSE non disponibile");
      })
      .finally(() => setCatalogLoading(false));
    return () => controller.abort();
  }, []);

  const selectedArea = useMemo(
    () => areas.find((area) => area.id === selectedAreaId) ?? null,
    [areas, selectedAreaId]
  );
  const activeLayer = layers.find((layer) => layer.id === layerId) ?? WMS_LAYERS[0];

  const handleCustomArea = (poly: [number, number][]) => {
    const number = areas.filter((area) => !area.id.startsWith("DEMO-")).length + 1;
    const area: MapArea = {
      id: `AREA-${number}`,
      name: `Campo ${number}`,
      poly,
      area_ha: geodesicAreaHectares(poly),
    };
    setAreas((current) => [...current, area]);
    setSelectedAreaId(area.id);
  };

  const exportGeoJson = () => {
    if (!selectedArea) return;
    const firstPoint = selectedArea.poly[0];
    const closedCoordinates = [...selectedArea.poly, firstPoint];
    const geoJson = {
      type: "Feature",
      properties: {
        id: selectedArea.id,
        name: selectedArea.name,
        area_ha: selectedArea.area_ha,
      },
      geometry: { type: "Polygon", coordinates: [closedCoordinates] },
    };
    download(
      `${selectedArea.id.toLowerCase()}.geojson`,
      JSON.stringify(geoJson, null, 2),
      "application/geo+json"
    );
  };

  const deleteSelectedArea = () => {
    if (!selectedAreaId) return;
    const remainingAreas = areas.filter((area) => area.id !== selectedAreaId);
    setAreas(remainingAreas);
    setSelectedAreaId(remainingAreas.at(-1)?.id ?? null);
  };

  const dataPanel = (
    <div className={isDesktopLayout ? "min-w-0 space-y-5 pr-4" : "min-w-0 space-y-5"}>
      {selectedArea ? (
        <>
          <section className="border-y border-slate-800 py-5">
            <div className="text-[11px] font-medium uppercase text-lime-400">Area selezionata</div>
            <div className="mt-2 flex flex-wrap items-end justify-between gap-4">
              <div>
                <h1 className="text-2xl font-semibold text-slate-100">{selectedArea.name}</h1>
                <p className="mt-1 text-sm text-slate-400">
                  {selectedArea.id.startsWith("DEMO-")
                    ? "AOI tecnica dimostrativa · dati satellitari reali · non e' un campo autorizzato"
                    : "Confine acquisito sulla mappa · analisi CDSE reale richiesta on demand"}
                </p>
              </div>
              <div className="text-right">
                <div className="text-3xl font-bold text-slate-100">
                  {formatArea(selectedArea.area_ha)}
                </div>
                <div className="text-[11px] uppercase text-slate-500">ettari stimati</div>
              </div>
            </div>
            <div className="mt-4 border-l-2 border-amber-400/70 pl-3 text-[12px] leading-relaxed text-slate-400">
              Catalog, serie NDVI e AI sono calcolati online sul Polygon. I layer SoilGrids
              restano contesto modellato a 250 m; diagnosi e prescrizioni richiedono ground
              truth e validazione agronomica.
            </div>
          </section>
          <AnalysisWorkspace
            area={selectedArea}
            layers={layers}
            activeLayerId={layerId}
            onLayerChange={setLayerId}
          />
        </>
      ) : (
        <section className="flex min-h-64 items-center justify-center border-y border-slate-800 py-12 text-center">
          <div className="max-w-sm">
            <MapPin className="mx-auto h-8 w-8 text-lime-400" />
            <h1 className="mt-4 text-lg font-semibold text-slate-100">Seleziona il primo campo</h1>
            <p className="mt-2 text-sm leading-relaxed text-slate-400">
              Disegna un rettangolo o un poligono in qualsiasi area d’Italia.
            </p>
          </div>
        </section>
      )}

      <LayerCatalog
        layers={layers}
        activeLayerId={layerId}
        onLayerChange={setLayerId}
        catalogLoading={catalogLoading}
        catalogError={catalogError}
      />

      <footer className="border-y border-slate-800 py-5 text-[11px] leading-relaxed text-slate-400">
        <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-slate-200">
          <Database className="h-4 w-4 text-lime-400" /> Fonti e provenienza dei dati
        </div>
        <div className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
          <Source icon={<Map className="h-4 w-4" />} label="Mappa di base" detail="Esri World Imagery · Esri, Maxar, Earthstar Geographics" href="https://www.esri.com/" />
          <Source icon={<Satellite className="h-4 w-4" />} label="Layer satellitari" detail="Sentinel-2 · WMS Copernicus Data Space Ecosystem" href="https://dataspace.copernicus.eu/" />
          <Source icon={<CloudSun className="h-4 w-4" />} label="Meteo" detail="Open-Meteo · osservazioni e previsioni sul centroide" href="https://open-meteo.com/" />
          <Source icon={<Database className="h-4 w-4" />} label="Proprietà del suolo" detail="SoilGrids WMS · ISRIC World Soil Information" href="https://soilgrids.org/" />
          <Source icon={<Layers className="h-4 w-4" />} label="Territorio Sicilia, prossima integrazione" detail="Geoportale S.I.T.R. · Regione Siciliana" href="https://www.sitr.regione.sicilia.it/geoportale/it/home/servicecatalog" />
        </div>
        <p className="mt-4 border-t border-slate-800 pt-3 text-slate-500">
          <strong className="text-slate-400">Disponibilità attuale:</strong> basemap, layer visuali Sentinel-2, SoilGrids, meteo, Catalog, serie NDVI quantitativa e AI da evidenze sono live. S.I.T.R., anomaly detection e PCA restano in integrazione. Nessun indicatore sintetico viene presentato come dato reale.
        </p>
      </footer>
    </div>
  );

  const mapPanel = (
    <div className={isDesktopLayout ? "sticky top-[72px] h-[calc(100vh-96px)] pl-4" : "h-[min(68vh,620px)] min-h-[420px]"}>
      <MapPanelNational
        areas={areas}
        activeLayer={activeLayer}
        selectedAreaId={selectedAreaId}
        onSelectArea={setSelectedAreaId}
        onCustomArea={handleCustomArea}
      />
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="sticky top-0 z-[600] border-b border-slate-800 bg-slate-950/90 backdrop-blur">
        <div className="flex w-full flex-wrap items-center gap-3 px-3 py-3 sm:px-4 xl:px-5">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-lime-400/15">
              <Sprout className="h-5 w-5 text-lime-400" />
            </div>
            <div>
              <div className="text-[15px] font-bold leading-tight">Verdimetria</div>
              <div className="flex items-center gap-1 text-[11px] leading-tight text-slate-500">
                <MapPin className="h-3 w-3" /> Italia · rollout operativo iniziale in Sicilia
              </div>
            </div>
          </div>

          <div className="ml-auto flex flex-wrap items-center gap-2">
            {selectedArea && (
              <>
                <Select
                  icon={<MapPin className="h-3.5 w-3.5" />}
                  value={selectedArea.id}
                  onChange={setSelectedAreaId}
                  options={areas.map((area) => ({ value: area.id, label: area.name }))}
                />
                <button
                  onClick={deleteSelectedArea}
                  aria-label="Elimina campo selezionato"
                  title="Elimina campo selezionato"
                  className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-700 text-slate-400 transition-colors hover:border-rose-400/60 hover:bg-rose-400/10 hover:text-rose-300"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </>
            )}
            <Select
              icon={<Layers className="h-3.5 w-3.5" />}
              value={layerId}
              onChange={setLayerId}
              options={layers.map((layer) => ({
                value: layer.id,
                label: layer.provider === "pending" ? `${layer.label} · in preparazione` : layer.label,
                disabled: layer.provider === "pending",
              }))}
            />
            <button
              onClick={exportGeoJson}
              disabled={!selectedArea}
              className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-2 text-[12px] font-medium text-slate-300 transition-colors hover:border-slate-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Download className="h-3.5 w-3.5" /> GeoJSON
            </button>
          </div>
        </div>
      </header>

      <main className="w-full px-3 py-4 sm:px-4 xl:px-5">
        {isDesktopLayout ? (
          <ResizablePanelGroup
            id="verdimetria-workspace"
            orientation="horizontal"
            defaultLayout={defaultLayout}
            onLayoutChange={onLayoutChange}
          >
            <ResizablePanel id="data" defaultSize="52%" minSize="32%" maxSize="68%">
              {dataPanel}
            </ResizablePanel>
            <ResizableHandle
              withHandle
              aria-label="Ridimensiona pannelli dati e mappa"
              className="mx-1.5 w-3 !items-start cursor-col-resize rounded-md bg-slate-900 transition-colors after:w-3 hover:bg-lime-400/15 [&>div]:pointer-events-none [&>div]:sticky [&>div]:top-[45vh] [&>div]:h-12 [&>div]:w-2 [&>div]:border-slate-600 [&>div]:bg-slate-950 [&>div]:text-lime-400"
            />
            <ResizablePanel id="map" defaultSize="48%" minSize="32%" maxSize="68%">
              {mapPanel}
            </ResizablePanel>
          </ResizablePanelGroup>
        ) : (
          <div className="flex flex-col gap-4">
            {mapPanel}
            {dataPanel}
          </div>
        )}
      </main>
    </div>
  );
}

function subscribeDesktopLayout(onChange: () => void) {
  const mediaQuery = window.matchMedia(DESKTOP_LAYOUT_QUERY);
  const resizeObserver = new ResizeObserver(onChange);
  mediaQuery.addEventListener("change", onChange);
  window.addEventListener("resize", onChange);
  resizeObserver.observe(document.documentElement);
  return () => {
    mediaQuery.removeEventListener("change", onChange);
    window.removeEventListener("resize", onChange);
    resizeObserver.disconnect();
  };
}

function getDesktopLayoutSnapshot() {
  return window.matchMedia(DESKTOP_LAYOUT_QUERY).matches;
}

function useDesktopLayout() {
  return useSyncExternalStore(subscribeDesktopLayout, getDesktopLayoutSnapshot, () => false);
}

function geodesicAreaHectares(poly: [number, number][]): number {
  const earthRadius = 6_378_137;
  let area = 0;
  for (let current = 0, previous = poly.length - 1; current < poly.length; previous = current++) {
    const [currentLongitude, currentLatitude] = poly[current];
    const [previousLongitude, previousLatitude] = poly[previous];
    area +=
      toRadians(currentLongitude - previousLongitude) *
      (2 + Math.sin(toRadians(previousLatitude)) + Math.sin(toRadians(currentLatitude)));
  }
  return Math.round((Math.abs(area * earthRadius * earthRadius) / 2 / 10_000) * 10) / 10;
}

function toRadians(value: number): number {
  return (value * Math.PI) / 180;
}

function formatArea(areaHectares: number): string {
  return areaHectares.toLocaleString("it-IT", { maximumFractionDigits: 1 });
}

function download(name: string, content: string, type: string) {
  const anchor = document.createElement("a");
  anchor.href = URL.createObjectURL(new Blob([content], { type }));
  anchor.download = name;
  anchor.click();
  URL.revokeObjectURL(anchor.href);
}

function Source({
  icon,
  label,
  detail,
  href,
}: {
  icon: React.ReactNode;
  label: string;
  detail: string;
  href: string;
}) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className="group flex gap-2.5">
      <span className="mt-0.5 text-slate-500 transition-colors group-hover:text-lime-400">{icon}</span>
      <span>
        <strong className="block text-slate-300 transition-colors group-hover:text-lime-300">{label}</strong>
        <span className="text-slate-500">{detail}</span>
      </span>
    </a>
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
  onChange: (value: string) => void;
  options: { value: string; label: string; disabled?: boolean }[];
}) {
  return (
    <div className="relative">
      <div className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500">
        {icon}
      </div>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="max-w-[240px] appearance-none truncate rounded-lg border border-slate-700 bg-slate-900 py-2 pl-8 pr-8 text-[12px] font-medium text-slate-200 outline-none transition-colors hover:border-slate-500 focus:border-lime-400/60"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value} disabled={option.disabled}>
            {option.label}
          </option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" />
    </div>
  );
}
