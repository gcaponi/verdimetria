import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { AppData, FieldData } from "@/types";
import { GradientLegend } from "@/components/ui-bits";
import { RectangleHorizontal, Hexagon, X, Loader2 } from "lucide-react";

interface Props {
  data: AppData;
  activeLayerId: string;
  selectedFieldId: string;
  onSelectField: (id: string) => void;
  drawEnabled: boolean;
  onCustomArea: (poly: [number, number][]) => void;
}

type DrawMode = "none" | "rect" | "poly";

export default function MapPanel({
  data,
  activeLayerId,
  selectedFieldId,
  onSelectField,
  drawEnabled,
  onCustomArea,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const overlayRef = useRef<L.ImageOverlay | null>(null);
  const fieldsLayerRef = useRef<L.LayerGroup | null>(null);
  const anomalyLayerRef = useRef<L.LayerGroup | null>(null);
  const tempRef = useRef<L.Layer | null>(null);
  const [drawMode, setDrawMode] = useState<DrawMode>("none");
  const [vertCount, setVertCount] = useState(0);

  const modeRef = useRef<DrawMode>("none");
  const rectStartRef = useRef<L.LatLng | null>(null);
  const polyVertsRef = useRef<L.LatLng[]>([]);
  const onSelectRef = useRef(onSelectField);
  const onCustomRef = useRef(onCustomArea);
  onSelectRef.current = onSelectField;
  onCustomRef.current = onCustomArea;

  const { manifest, fields, geo } = data;
  const b = manifest.bounds;
  const bounds: L.LatLngBoundsExpression = [
    [b.south, b.west],
    [b.north, b.east],
  ];

  const setMode = (m: DrawMode) => {
    modeRef.current = m;
    setDrawMode(m);
    const map = mapRef.current;
    if (!map) return;
    if (m !== "none") {
      map.doubleClickZoom.disable();
      if (containerRef.current) containerRef.current.style.cursor = "crosshair";
    } else {
      map.doubleClickZoom.enable();
      map.dragging.enable();
      if (containerRef.current) containerRef.current.style.cursor = "";
    }
  };

  const clearTemp = () => {
    const map = mapRef.current;
    if (map && tempRef.current) {
      map.removeLayer(tempRef.current);
      tempRef.current = null;
    }
    rectStartRef.current = null;
    polyVertsRef.current = [];
    setVertCount(0);
  };

  const finishPolygon = (verts: L.LatLng[]) => {
    if (verts.length < 3) return;
    const coords: [number, number][] = verts.map((v) => [
      Math.round(v.lng * 100000) / 100000,
      Math.round(v.lat * 100000) / 100000,
    ]);
    clearTemp();
    setMode("none");
    onCustomRef.current(coords);
  };

  // init mappa + handler disegno
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = L.map(containerRef.current, {
      center: [36.88, 14.62],
      zoom: 10,
      zoomControl: true,
      attributionControl: true,
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
    fieldsLayerRef.current = L.layerGroup().addTo(map);
    anomalyLayerRef.current = L.layerGroup().addTo(map);

    // ---- rettangolo: trascina ----
    map.on("mousedown", (e: L.LeafletMouseEvent) => {
      if (modeRef.current !== "rect") return;
      map.dragging.disable();
      rectStartRef.current = e.latlng;
      if (tempRef.current) map.removeLayer(tempRef.current);
      tempRef.current = L.rectangle(L.latLngBounds(e.latlng, e.latlng), tempStyle()).addTo(map);
    });
    map.on("mousemove", (e: L.LeafletMouseEvent) => {
      if (modeRef.current === "rect" && rectStartRef.current && tempRef.current) {
        (tempRef.current as L.Rectangle).setBounds(
          L.latLngBounds(rectStartRef.current, e.latlng)
        );
      }
    });
    map.on("mouseup", (e: L.LeafletMouseEvent) => {
      if (modeRef.current !== "rect" || !rectStartRef.current) return;
      const s = rectStartRef.current;
      map.dragging.enable();
      const verts = [
        L.latLng(s.lat, s.lng),
        L.latLng(s.lat, e.latlng.lng),
        L.latLng(e.latlng.lat, e.latlng.lng),
        L.latLng(e.latlng.lat, s.lng),
      ];
      finishPolygon(verts);
    });

    // ---- poligono: click vertici, dblclick chiudi ----
    map.on("click", (e: L.LeafletMouseEvent) => {
      if (modeRef.current !== "poly") return;
      polyVertsRef.current.push(e.latlng);
      setVertCount(polyVertsRef.current.length);
      if (tempRef.current) map.removeLayer(tempRef.current);
      tempRef.current = L.polygon(polyVertsRef.current, tempStyle()).addTo(map);
    });
    map.on("dblclick", () => {
      if (modeRef.current !== "poly") return;
      finishPolygon(polyVertsRef.current);
    });

    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === "Escape") {
        clearTemp();
        setMode("none");
      }
      if (ev.key === "Enter" && modeRef.current === "poly") {
        finishPolygon(polyVertsRef.current);
      }
    };
    window.addEventListener("keydown", onKey);
    setTimeout(() => map.invalidateSize(), 100);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // overlay raster
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (overlayRef.current) {
      map.removeLayer(overlayRef.current);
      overlayRef.current = null;
    }
    if (activeLayerId !== "none") {
      overlayRef.current = L.imageOverlay(
        `data/layers/${activeLayerId}.png`,
        bounds,
        { opacity: 0.85, interactive: false }
      ).addTo(map);
    }
  }, [activeLayerId]);

  // poligoni campi (+ area personalizzata, presente in fields)
  useEffect(() => {
    const grp = fieldsLayerRef.current;
    if (!grp) return;
    grp.clearLayers();
    fields.forEach((f) => {
      const sel = f.id === selectedFieldId;
      const isCustom = f.id.startsWith("CUSTOM");
      const poly = L.polygon(f.poly.map((p) => [p[1], p[0]]) as L.LatLngExpression[], {
        color: sel ? "#a3e635" : isCustom ? "#fbbf24" : "#e2e8f0",
        weight: sel ? 3 : 1.4,
        dashArray: isCustom ? "6 4" : undefined,
        fillColor: sel ? "#a3e635" : isCustom ? "#fbbf24" : "#94a3b8",
        fillOpacity: sel ? 0.18 : 0.05,
      });
      poly.bindTooltip(
        `<div style="font-weight:600">${f.name}</div><div style="opacity:.75">${f.crop} · ${f.area_ha} ha</div>`,
        { sticky: true }
      );
      poly.on("click", () => {
        if (modeRef.current === "none") onSelectRef.current(f.id);
      });
      poly.addTo(grp);
    });
  }, [fields, selectedFieldId]);

  // marker anomalie geologiche
  useEffect(() => {
    const grp = anomalyLayerRef.current;
    if (!grp) return;
    grp.clearLayers();
    if (activeLayerId === "anomaly" || activeLayerId === "pca") {
      geo.top_locations.forEach((loc, i) => {
        const m = L.circleMarker([loc.lat, loc.lon], {
          radius: i < 5 ? 9 : 6,
          color: "#0f172a",
          weight: 2,
          fillColor: i < 5 ? "#fb923c" : "#fdba74",
          fillOpacity: 0.95,
        });
        m.bindTooltip(
          `<div style="font-weight:600">Anomalia #${i + 1}</div><div>score ${loc.score} · ${loc.lat}, ${loc.lon}</div>`,
          { sticky: true }
        );
        m.addTo(grp);
      });
    }
  }, [activeLayerId, geo]);

  const layer = manifest.layers.find((l) => l.id === activeLayerId);

  return (
    <div className="relative h-full w-full overflow-hidden rounded-xl border border-slate-800">
      <div ref={containerRef} className="h-full w-full bg-slate-950" />

      {/* toolbar disegno */}
      <div className="absolute left-1/2 top-4 z-[500] flex -translate-x-1/2 items-center gap-1.5">
        {drawMode === "none" ? (
          <>
            <DrawButton
              disabled={!drawEnabled}
              onClick={() => setMode("rect")}
              title={drawEnabled ? "Disegna un rettangolo da analizzare" : "Caricamento griglie…"}
            >
              {drawEnabled ? <RectangleHorizontal className="h-4 w-4" /> : <Loader2 className="h-4 w-4 animate-spin" />}
              <span className="hidden sm:inline">Rettangolo</span>
            </DrawButton>
            <DrawButton
              disabled={!drawEnabled}
              onClick={() => setMode("poly")}
              title={drawEnabled ? "Disegna un poligono da analizzare" : "Caricamento griglie…"}
            >
              <Hexagon className="h-4 w-4" />
              <span className="hidden sm:inline">Poligono</span>
            </DrawButton>
          </>
        ) : (
          <div className="flex items-center gap-2 rounded-lg border border-lime-400/40 bg-slate-900/95 px-3 py-2 shadow-lg backdrop-blur">
            <span className="text-[12px] text-lime-300">
              {drawMode === "rect"
                ? "Trascina sulla mappa per disegnare il rettangolo"
                : vertCount < 3
                ? `Clicca per i vertici (${vertCount}/3 min)`
                : `${vertCount} vertici — chiudi con il doppio clic o ✓`}
            </span>
            {drawMode === "poly" && vertCount >= 3 && (
              <button
                onClick={() => finishPolygon(polyVertsRef.current)}
                className="rounded-md bg-lime-400 px-2 py-1 text-[12px] font-bold text-slate-950 hover:bg-lime-300"
                title="Chiudi il poligono e analizza (Invio)"
              >
                ✓ Analizza
              </button>
            )}
            <button
              onClick={() => { clearTemp(); setMode("none"); }}
              className="rounded-md p-1 text-slate-400 hover:bg-slate-800 hover:text-white"
              title="Annulla (Esc)"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        )}
      </div>

      {layer && layer.cmap && (
        <div className="absolute bottom-4 right-4 z-[500]">
          <GradientLegend layer={layer} />
        </div>
      )}
      {activeLayerId === "pca" && (
        <div className="absolute bottom-4 right-4 z-[500] max-w-[220px] rounded-lg border border-slate-700/70 bg-slate-900/90 px-3 py-2 text-[11px] text-slate-300 shadow-lg backdrop-blur">
          Proiezione PCA (3 componenti → RGB): i colori marcati indicano dove il
          territorio si discosta dai pattern dominanti
        </div>
      )}
      <FieldChip field={fields.find((f) => f.id === selectedFieldId)} />
    </div>
  );
}

function tempStyle(): L.PolylineOptions {
  return { color: "#a3e635", weight: 2, dashArray: "6 4", fillColor: "#a3e635", fillOpacity: 0.12 };
}

function DrawButton({
  children,
  onClick,
  disabled,
  title,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  title?: string;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900/95 px-3 py-2 text-[12px] font-medium text-slate-200 shadow-lg backdrop-blur transition-colors hover:border-lime-400/50 hover:text-lime-300 disabled:cursor-wait disabled:opacity-60"
    >
      {children}
    </button>
  );
}

function FieldChip({ field }: { field?: FieldData }) {
  if (!field) return null;
  return (
    <div className="absolute left-4 top-4 z-[400] max-w-[220px] rounded-lg border border-slate-700/70 bg-slate-900/90 px-3 py-2 shadow-lg backdrop-blur">
      <div className="truncate text-sm font-semibold text-slate-100">{field.name}</div>
      <div className="text-[11px] text-slate-400">
        {field.crop} · {field.area_ha} ha
      </div>
    </div>
  );
}
