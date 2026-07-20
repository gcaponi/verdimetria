import { useEffect, useEffectEvent, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "@geoman-io/leaflet-geoman-free";
import "@geoman-io/leaflet-geoman-free/dist/leaflet-geoman.css";
import { areaBounds, buildWmsUrl } from "@/lib/wms";
import type { WmsLayer } from "@/lib/wms";
import type { MapArea } from "@/types";
import { Check, ChevronDown, Hexagon, RectangleHorizontal, X } from "lucide-react";

interface Props {
  areas: MapArea[];
  activeLayer: WmsLayer;
  selectedAreaId: string | null;
  onSelectArea: (id: string) => void;
  onCustomArea: (poly: [number, number][]) => void;
}

type DrawMode = "none" | "rect" | "poly";
type LayerStatus = "idle" | "loading" | "ready" | "error";

export default function MapPanelNational({
  areas,
  activeLayer,
  selectedAreaId,
  onSelectArea,
  onCustomArea,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const overlayRef = useRef<L.ImageOverlay | null>(null);
  const areasLayerRef = useRef<L.LayerGroup | null>(null);
  const draftLayerRef = useRef<L.Polygon | null>(null);
  const fittedAreaRef = useRef<string | null>(null);
  const [drawMode, setDrawMode] = useState<DrawMode>("none");
  const [hasDraft, setHasDraft] = useState(false);
  const [overlayState, setOverlayState] = useState<{ key: string | null; status: LayerStatus }>({
    key: null,
    status: "idle",
  });

  const modeRef = useRef<DrawMode>("none");
  const selectArea = useEffectEvent(onSelectArea);

  const selectedArea = areas.find((area) => area.id === selectedAreaId);
  const overlayKey = selectedArea && activeLayer.provider !== "none" && activeLayer.provider !== "pending"
    ? `${selectedArea.id}:${activeLayer.id}`
    : null;
  const layerStatus = overlayState.key === overlayKey
    ? overlayState.status
    : overlayKey
      ? "loading"
      : "idle";

  const setMode = (mode: DrawMode) => {
    const map = mapRef.current;
    const container = containerRef.current;
    if (!map || !container || hasDraft) return;

    map.pm.disableDraw();
    const nextMode = modeRef.current === mode ? "none" : mode;
    modeRef.current = nextMode;
    setDrawMode(nextMode);
    if (nextMode === "none") {
      restoreMapNavigation(map, container);
      return;
    }

    map.dragging.disable();
    map.touchZoom.disable();
    map.doubleClickZoom.disable();
    map.scrollWheelZoom.disable();
    container.style.cursor = "crosshair";
    map.pm.enableDraw(nextMode === "rect" ? "Rectangle" : "Polygon", {
      allowSelfIntersection: false,
      finishOnEnter: true,
      hintlineStyle: tempStyle(),
      pathOptions: tempStyle(),
      snapDistance: 24,
      snappable: true,
      templineStyle: tempStyle(),
      tooltips: true,
    });
  };

  const cancelDrawing = () => {
    const map = mapRef.current;
    const container = containerRef.current;
    if (map) {
      map.pm.disableDraw();
      if (draftLayerRef.current) {
        draftLayerRef.current.pm.disable();
        map.removeLayer(draftLayerRef.current);
      }
      if (container) restoreMapNavigation(map, container);
    }
    draftLayerRef.current = null;
    modeRef.current = "none";
    setDrawMode("none");
    setHasDraft(false);
  };
  const cancelDrawingFromEffect = useEffectEvent(cancelDrawing);

  const confirmDraft = () => {
    const map = mapRef.current;
    const container = containerRef.current;
    const layer = draftLayerRef.current;
    if (!map || !container || !layer) return;
    const coordinates = draftCoordinates(layer);
    if (coordinates.length < 3) return;

    layer.pm.disable();
    map.removeLayer(layer);
    restoreMapNavigation(map, container);
    draftLayerRef.current = null;
    setHasDraft(false);
    onCustomArea(coordinates);
  };

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = L.map(containerRef.current, {
      center: [42.2, 12.5],
      zoom: 6,
      zoomControl: true,
      attributionControl: true,
      maxBounds: L.latLngBounds([34.5, 5.5], [48.5, 20.5]),
      maxBoundsViscosity: 0.6,
    });
    L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      { attribution: "Esri, Maxar, Earthstar Geographics", maxZoom: 18 }
    ).addTo(map);
    L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
      { maxZoom: 18, opacity: 0.9 }
    ).addTo(map);
    mapRef.current = map;
    areasLayerRef.current = L.layerGroup().addTo(map);

    const handleCreate: L.PM.CreateEventHandler = ({ layer }) => {
      if (!(layer instanceof L.Polygon)) {
        map.removeLayer(layer);
        return;
      }

      map.pm.disableDraw();
      restoreMapNavigation(map, containerRef.current!);
      modeRef.current = "none";
      setDrawMode("none");
      draftLayerRef.current = layer;
      layer.setStyle(tempStyle());
      layer.pm.enable({
        allowSelfIntersection: false,
        allowSelfIntersectionEdit: false,
        draggable: false,
        removeLayerBelowMinVertexCount: false,
        snapDistance: 24,
        snappable: true,
      });
      setHasDraft(true);
    };
    map.on("pm:create", handleCreate);

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        cancelDrawingFromEffect();
      }
    };
    window.addEventListener("keydown", onKey);
    let resizeFrame = 0;
    const resizeObserver = new ResizeObserver(() => {
      cancelAnimationFrame(resizeFrame);
      resizeFrame = requestAnimationFrame(() => {
        map.invalidateSize({ animate: false, pan: false });
      });
    });
    resizeObserver.observe(containerRef.current);
    setTimeout(() => map.invalidateSize(), 100);
    return () => {
      window.removeEventListener("keydown", onKey);
      resizeObserver.disconnect();
      cancelAnimationFrame(resizeFrame);
      map.off("pm:create", handleCreate);
      map.pm.disableDraw();
      map.remove();
      mapRef.current = null;
      areasLayerRef.current = null;
      draftLayerRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (overlayRef.current) {
      map.removeLayer(overlayRef.current);
      overlayRef.current = null;
    }
    if (!selectedArea || !overlayKey) return;

    const bounds = areaBounds(selectedArea);
    const imageBounds: L.LatLngBoundsExpression = [
      [bounds.south, bounds.west],
      [bounds.north, bounds.east],
    ];
    const overlay = L.imageOverlay(buildWmsUrl(activeLayer, selectedArea), imageBounds, {
      opacity: 0.82,
      interactive: false,
    });
    overlay.on("load", () => setOverlayState({ key: overlayKey, status: "ready" }));
    overlay.on("error", () => setOverlayState({ key: overlayKey, status: "error" }));
    overlay.addTo(map);
    overlayRef.current = overlay;
    const element = overlay.getElement();
    if (element) element.style.clipPath = polygonClipPath(selectedArea);
  }, [activeLayer, overlayKey, selectedArea]);

  useEffect(() => {
    const group = areasLayerRef.current;
    if (!group) return;
    group.clearLayers();
    areas.forEach((area) => {
      const selected = area.id === selectedAreaId;
      const polygon = L.polygon(
        area.poly.map(([longitude, latitude]) => [latitude, longitude]),
        {
          color: selected ? "#a3e635" : "#fbbf24",
          weight: selected ? 3 : 1.5,
          dashArray: selected ? undefined : "6 4",
          fillColor: selected ? "#a3e635" : "#fbbf24",
          fillOpacity: selected ? 0.08 : 0.04,
        }
      );
      polygon.bindTooltip(
        `<div style="font-weight:600">${area.name}</div><div style="opacity:.75">${area.area_ha.toLocaleString("it-IT")} ha</div>`,
        { sticky: true }
      );
      polygon.on("click", () => {
        if (modeRef.current === "none") selectArea(area.id);
      });
      polygon.addTo(group);
    });
  }, [areas, selectedAreaId]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !selectedArea || fittedAreaRef.current === selectedArea.id) return;
    const bounds = areaBounds(selectedArea);
    map.fitBounds(
      L.latLngBounds([bounds.south, bounds.west], [bounds.north, bounds.east]),
      { padding: [36, 36], maxZoom: 15 },
    );
    fittedAreaRef.current = selectedArea.id;
  }, [selectedArea]);

  return (
    <div className="relative isolate z-0 h-full w-full overflow-hidden rounded-xl border border-slate-800">
      <div ref={containerRef} className="h-full w-full bg-slate-950" />

      <div className="absolute left-1/2 top-4 z-[500] flex -translate-x-1/2 items-center gap-1.5">
        {hasDraft ? (
          <div className="flex max-w-[calc(100vw-1.5rem)] items-center gap-2 rounded-lg border border-lime-400/40 bg-slate-900/95 p-1.5 pl-3 shadow-lg backdrop-blur">
            <span className="min-w-0 text-[12px] font-medium text-lime-300">
              Regola i vertici, poi conferma
            </span>
            <button
              type="button"
              onClick={confirmDraft}
              className="flex h-11 shrink-0 items-center gap-1.5 rounded-md bg-lime-400 px-3 text-[12px] font-bold text-slate-950 hover:bg-lime-300"
              title="Conferma il confine"
            >
              <Check className="h-4 w-4" />
              Conferma
            </button>
            <button
              type="button"
              onClick={cancelDrawing}
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md text-slate-400 hover:bg-slate-800 hover:text-white"
              title="Annulla il disegno"
              aria-label="Annulla il disegno"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        ) : drawMode === "none" ? (
          <>
            <DrawButton onClick={() => setMode("rect")} title="Disegna un rettangolo">
              <RectangleHorizontal className="h-4 w-4" />
              <span className="hidden sm:inline">Rettangolo</span>
            </DrawButton>
            <DrawButton onClick={() => setMode("poly")} title="Disegna un poligono">
              <Hexagon className="h-4 w-4" />
              <span className="hidden sm:inline">Poligono</span>
            </DrawButton>
          </>
        ) : (
          <div className="flex items-center gap-2 rounded-lg border border-lime-400/40 bg-slate-900/95 px-3 py-2 shadow-lg backdrop-blur">
            <span className="text-[12px] text-lime-300">
              {drawMode === "rect"
                ? "Indica i due angoli"
                : "Tocca i vertici · chiudi sul primo"}
            </span>
            <button
              type="button"
              onClick={cancelDrawing}
              className="flex h-11 w-11 items-center justify-center rounded-md text-slate-400 hover:bg-slate-800 hover:text-white"
              title="Annulla il disegno"
              aria-label="Annulla il disegno"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        )}
      </div>

      {selectedArea && activeLayer && activeLayer.provider !== "none" && (
        <div className="absolute bottom-4 right-4 z-[500] max-w-[260px] rounded-lg border border-slate-700/70 bg-slate-900/95 px-3 py-2 text-[11px] shadow-lg backdrop-blur">
          <div className="font-semibold text-slate-200">{activeLayer.label}</div>
          <div className="text-slate-400">{activeLayer.detail}</div>
          <div className={layerStatusColor(layerStatus)}>
            {layerStatusLabel(layerStatus, activeLayer.provider)}
          </div>
          <LayerLegend layer={activeLayer} />
        </div>
      )}

      <AreaChip area={selectedArea} />
    </div>
  );
}

function polygonClipPath(area: MapArea): string {
  const bounds = areaBounds(area);
  const width = bounds.east - bounds.west;
  const height = bounds.north - bounds.south;
  const points = area.poly.map(([longitude, latitude]) => {
    const x = ((longitude - bounds.west) / width) * 100;
    const y = ((bounds.north - latitude) / height) * 100;
    return `${x.toFixed(4)}% ${y.toFixed(4)}%`;
  });
  return `polygon(${points.join(", ")})`;
}

function tempStyle(): L.PolylineOptions {
  return {
    color: "#a3e635",
    weight: 2,
    dashArray: "6 4",
    fillColor: "#a3e635",
    fillOpacity: 0.12,
  };
}

function draftCoordinates(layer: L.Polygon): [number, number][] {
  const latLngs = layer.getLatLngs();
  const firstRing = latLngs[0];
  if (!Array.isArray(firstRing) || firstRing.length === 0 || Array.isArray(firstRing[0])) return [];
  return (firstRing as L.LatLng[]).map((vertex) => [
    Math.round(vertex.lng * 100000) / 100000,
    Math.round(vertex.lat * 100000) / 100000,
  ]);
}

function restoreMapNavigation(map: L.Map, container: HTMLDivElement) {
  map.dragging.enable();
  map.touchZoom.enable();
  map.doubleClickZoom.enable();
  map.scrollWheelZoom.enable();
  container.style.cursor = "";
}

function DrawButton({
  children,
  onClick,
  title,
}: {
  children: React.ReactNode;
  onClick: () => void;
  title: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className="flex h-11 items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900/95 px-3 text-[12px] font-medium text-slate-200 shadow-lg backdrop-blur transition-colors hover:border-lime-400/50 hover:text-lime-300"
    >
      {children}
    </button>
  );
}

function AreaChip({ area }: { area?: MapArea }) {
  if (!area) return null;
  return (
    <div className="absolute left-4 top-4 z-[400] max-w-[220px] rounded-lg border border-slate-700/70 bg-slate-900/90 px-3 py-2 shadow-lg backdrop-blur">
      <div className="truncate text-sm font-semibold text-slate-100">{area.name}</div>
      <div className="text-[11px] text-slate-400">
        {area.area_ha.toLocaleString("it-IT", { maximumFractionDigits: 1 })} ha
      </div>
    </div>
  );
}

function layerStatusLabel(status: LayerStatus, provider: "cdse" | "soilgrids" | "pending"): string {
  const providerLabel = provider === "soilgrids" ? "SoilGrids" : "CDSE";
  if (status === "loading") return `Caricamento da ${providerLabel}…`;
  if (status === "ready") return `Dati ${providerLabel} caricati`;
  if (status === "error") return "Layer non disponibile per l'intervallo richiesto";
  return "";
}

function layerStatusColor(status: LayerStatus): string {
  if (status === "ready") return "mt-1 text-emerald-300";
  if (status === "error") return "mt-1 text-rose-300";
  return "mt-1 text-amber-300";
}

function LayerLegend({ layer }: { layer: WmsLayer }) {
  const legend = layer.legend;
  const [expanded, setExpanded] = useState(false);
  if (!legend) {
    return (
      <div className="mt-2 border-t border-slate-700/70 pt-2 text-[10px] leading-relaxed text-slate-500">
        Layer visuale WMS senza scala numerica pubblicata.
      </div>
    );
  }

  if (legend.kind === "image" && legend.imageUrl) {
    return (
      <div className="mt-2 border-t border-slate-700/70 pt-2">
        <button
          type="button"
          onClick={() => setExpanded((current) => !current)}
          className="flex w-full items-center justify-between gap-3 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-300 hover:text-white"
          aria-expanded={expanded}
        >
          Legenda ufficiale SoilGrids
          <ChevronDown className={`h-3.5 w-3.5 transition-transform ${expanded ? "rotate-180" : ""}`} />
        </button>
        {expanded && (
          <div className="mt-2 max-h-56 overflow-y-auto rounded bg-white p-1.5">
            <img
              src={legend.imageUrl}
              alt={`Scala colori ${layer.label}`}
              className="mx-auto h-auto max-w-full"
            />
          </div>
        )}
        {legend.note && <p className="mt-1.5 leading-relaxed text-slate-500">{legend.note}</p>}
      </div>
    );
  }

  return (
    <div className="mt-2 border-t border-slate-700/70 pt-2">
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
        Scala colori
      </div>
      <div className="h-2.5 w-full rounded-sm" style={{ background: legend.gradient }} />
      <div className="mt-1 flex justify-between text-[10px] text-slate-400">
        <span>{legend.lowLabel}</span>
        <span>{legend.highLabel}</span>
      </div>
      {legend.note && <p className="mt-1.5 leading-relaxed text-slate-500">{legend.note}</p>}
    </div>
  );
}
