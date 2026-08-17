import type { MapArea } from "@/types";

export type WmsLayerGroup = "base" | "vegetation" | "soil" | "analysis" | "cdse-catalog";

export interface WmsLegend {
  kind: "gradient" | "image";
  gradient?: string;
  lowLabel?: string;
  highLabel?: string;
  imageUrl?: string;
  note?: string;
}

export interface WmsLayer {
  id: string;
  label: string;
  detail: string;
  provider: "none" | "cdse" | "soilgrids" | "pending";
  group: WmsLayerGroup;
  remoteLayer?: string;
  soilProperty?: string;
  legend?: WmsLegend;
}

export const WMS_LAYERS: WmsLayer[] = [
  {
    id: "NONE",
    label: "Solo satellite",
    detail: "Mappa di base senza overlay",
    provider: "none",
    group: "base",
  },
  {
    id: "NDVI",
    label: "NDVI",
    detail: "Indice di vegetazione, visualizzazione Sentinel-2",
    provider: "cdse",
    group: "vegetation",
    legend: {
      kind: "gradient",
      gradient: "linear-gradient(90deg,#d01010,#701010,#787810,#e0e030,#30e0e0)",
      lowLabel: "basso (rosso)",
      highLabel: "alto (turchese)",
      note: "Rampa reale del layer CDSE: rosso = suolo nudo/acqua, giallo = vegetazione moderata, turchese = vegetazione vigorosa. Valori quantitativi dalla Process API.",
    },
  },
  {
    id: "EVI",
    label: "EVI",
    detail: "Indice di vegetazione migliorato, visualizzazione Sentinel-2",
    provider: "cdse",
    group: "vegetation",
    legend: {
      kind: "gradient",
      gradient: "linear-gradient(90deg,#78350f,#f59e0b,#fde68a,#65a30d,#14532d)",
      lowLabel: "basso",
      highLabel: "alto",
      note: "Scala qualitativa del layer visuale CDSE.",
    },
  },
  {
    id: "SAVI",
    label: "SAVI",
    detail: "Indice di vegetazione corretto per il suolo",
    provider: "cdse",
    group: "vegetation",
    legend: {
      kind: "gradient",
      gradient: "linear-gradient(90deg,#92400e,#fbbf24,#d9f99d,#4d7c0f,#14532d)",
      lowLabel: "suolo esposto",
      highLabel: "vegetazione",
      note: "Scala qualitativa del layer visuale CDSE.",
    },
  },
  {
    id: "NDWI",
    label: "NDWI",
    detail: "Indice visuale della presenza d'acqua",
    provider: "cdse",
    group: "vegetation",
    legend: {
      kind: "gradient",
      gradient: "linear-gradient(90deg,#0a0a0a,#737373,#e5e5e5)",
      lowLabel: "asciutto (scuro)",
      highLabel: "acqua (chiaro)",
      note: "Il layer CDSE rende in scala di grigi: scuro = secco, chiaro = umido/acqua.",
    },
  },
  {
    id: "AGRICULTURE",
    label: "Composito agricolo",
    detail: "Composito multispettrale visuale",
    provider: "cdse",
    group: "vegetation",
    legend: {
      kind: "gradient",
      note: "Falso colore (SWIR/NIR/verde), nessuna scala numerica: verde brillante = vegetazione vigorosa, marrone/tenue = suolo nudo o vegetazione stressata, acqua scura.",
    },
  },
  {
    id: "GEOLOGY",
    label: "Composito geologico",
    detail: "Composito multispettrale visuale, non carta geologica",
    provider: "cdse",
    group: "vegetation",
    legend: {
      kind: "gradient",
      note: "Falso colore SWIR/NIR/visibile, nessuna scala numerica: suoli nudi e rocce in toni marrone-rossastri, vegetazione in toni ciano-verdi, acqua scura. Lettura visuale di supporto: non e' una carta geologica (quella arriva da ISPRA).",
    },
  },
  soilLayer("NITROGEN", "Azoto totale (N)", "nitrogen", "nitrogen_0-5cm_mean"),
  soilLayer("PH", "pH in acqua", "phh2o", "phh2o_0-5cm_mean"),
  soilLayer("SOC", "Carbonio organico (SOC)", "soc", "soc_0-5cm_mean"),
  soilLayer("CLAY", "Argilla", "clay", "clay_0-5cm_mean"),
  soilLayer("SAND", "Sabbia", "sand", "sand_0-5cm_mean"),
  soilLayer("SILT", "Limo", "silt", "silt_0-5cm_mean"),
  soilLayer("CEC", "Capacità di scambio cationico", "cec", "cec_0-5cm_mean"),
  soilLayer("BDOD", "Densità apparente", "bdod", "bdod_0-5cm_mean"),
  soilLayer("CFVO", "Frammenti grossolani", "cfvo", "cfvo_0-5cm_mean"),
  {
    id: "WEAKNESS",
    label: "Debolezza cronica suolo",
    detail: "Richiede una serie storica NDVI quantitativa",
    provider: "pending",
    group: "analysis",
  },
  {
    id: "PHOSPHORUS",
    label: "Fosforo accessibile (P)",
    detail: "Non disponibile in SoilGrids; richiede laboratorio o fonte validata",
    provider: "pending",
    group: "analysis",
  },
  {
    id: "POTASSIUM",
    label: "Potassio scambiabile (K)",
    detail: "Non disponibile in SoilGrids; richiede laboratorio o fonte validata",
    provider: "pending",
    group: "analysis",
  },
  {
    id: "ANOMALY",
    label: "Anomalia geologica",
    detail: "Richiede pipeline anomaly detection backend",
    provider: "pending",
    group: "analysis",
  },
  {
    id: "PCA",
    label: "PCA geologica (RGB)",
    detail: "Richiede pipeline PCA backend",
    provider: "pending",
    group: "analysis",
  },
];

// Visual CDSE overlays are served by the Worker Process API proxy.
// The old Sentinel Hub Configuration Instance id is invalid after the
// 2026-08-14 credential rotation (`Invalid instance id`).
const LAYER_PREVIEW_PATH = "/api/layer";

function soilLayer(
  id: string,
  label: string,
  soilProperty: string,
  remoteLayer: string
): WmsLayer {
  return {
    id,
    label,
    detail: "SoilGrids 250 m, profondità 0-5 cm, media modellata",
    provider: "soilgrids",
    group: "soil",
    soilProperty,
    remoteLayer,
    legend: {
      kind: "image",
      imageUrl: buildSoilGridsLegendUrl(soilProperty, remoteLayer),
      note: "Legenda ufficiale SoilGrids; valori modellati, non analisi di laboratorio.",
    },
  };
}

function buildSoilGridsLegendUrl(soilProperty: string, remoteLayer: string): string {
  const params = new URLSearchParams({
    map: `/map/${soilProperty}.map`,
    version: "1.1.1",
    service: "WMS",
    request: "GetLegendGraphic",
    layer: remoteLayer,
    format: "image/png",
    STYLE: "default",
  });
  return `https://maps.isric.org/mapserv?${params.toString()}`;
}

export async function loadCdseCatalog(_signal?: AbortSignal): Promise<WmsLayer[]> {
  // Extra catalog layers came from the deleted Configuration Instance.
  // First-party visual layers are listed in WMS_LAYERS and rendered via /api/layer.
  return [];
}

export const SCENE_WINDOW_DAYS = 90;
export const SCENE_MAX_CLOUD_COVER = 30;
export const SCENE_MAX_ATTEMPTS = 3;
export const SCENE_MIN_COVERAGE = 0.85;

/** Inclusive date range (YYYY-MM-DD) for the WMS TIME parameter. */
export interface SceneTimeWindow {
  from: string;
  to: string;
}

/** Rolling window [today - SCENE_WINDOW_DAYS, today] used by default for CDSE GetMap requests. */
export function currentSceneWindow(now: Date = new Date()): SceneTimeWindow {
  const to = now.toISOString().slice(0, 10);
  return { from: shiftISODate(to, -SCENE_WINDOW_DAYS), to };
}

/**
 * Window that forces the WMS to pick the acquisition BEFORE `sceneDate`:
 * same start, end = day before the current scene. Returns null when the range
 * would be empty (no older acquisition to try inside the rolling window).
 */
export function previousSceneWindow(
  timeRange: SceneTimeWindow,
  sceneDate: string
): SceneTimeWindow | null {
  // Clamp to the range end so it always shrinks, even in the rare case the
  // catalogue and the WMS disagree about the most recent scene.
  const anchor = sceneDate <= timeRange.to ? sceneDate : timeRange.to;
  const to = shiftISODate(anchor, -1);
  if (to < timeRange.from) return null;
  return { from: timeRange.from, to };
}

/** One evaluated WMS image: which scene it shows (if known) and how much of the polygon it covers. */
export interface SceneAttempt {
  sceneDate: string | null;
  coverage: number; // 0..1, fraction of non-transparent pixels inside the field polygon
}

/** Attempt with the highest polygon coverage (first max wins); null when nothing was measured. */
export function pickBestAttempt<T extends SceneAttempt>(attempts: readonly T[]): T | null {
  let best: T | null = null;
  for (const attempt of attempts) {
    if (!best || attempt.coverage > best.coverage) best = attempt;
  }
  return best;
}

function shiftISODate(isoDate: string, days: number): string {
  const date = new Date(`${isoDate}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

const CDSE_CATALOG_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products";

export interface CdseScene {
  /** Acquisition day (YYYY-MM-DD) of the most recent scene matching the query. */
  date: string;
}

/**
 * Most recent Sentinel-2 L2A scene in the CDSE catalogue intersecting the bbox,
 * filtered by the same rolling window and cloud cover (MAXCC) used by the WMS
 * GetMap. The WMS picks per tile while this queries per bbox, so the date is an
 * indication: it may rarely differ from the scene actually rendered.
 */
export async function fetchLatestCdseScene(
  bounds: { west: number; south: number; east: number; north: number },
  timeRange: SceneTimeWindow,
  signal?: AbortSignal
): Promise<CdseScene | null> {
  const footprint =
    "POLYGON((" +
    `${bounds.west} ${bounds.south},${bounds.east} ${bounds.south},` +
    `${bounds.east} ${bounds.north},${bounds.west} ${bounds.north},` +
    `${bounds.west} ${bounds.south}))`;
  const filter = [
    "Collection/Name eq 'SENTINEL-2'",
    "contains(Name,'MSIL2A')",
    `ContentDate/Start ge ${timeRange.from}T00:00:00.000Z`,
    `ContentDate/Start le ${timeRange.to}T23:59:59.999Z`,
    `OData.CSC.Intersects(area=geography'SRID=4326;${footprint}')`,
    `Attributes/OData.CSC.DoubleAttribute/any(att:att/Name eq 'cloudCover' and att/OData.CSC.DoubleAttribute/Value le ${SCENE_MAX_CLOUD_COVER})`,
  ].join(" and ");
  const params = new URLSearchParams({
    $filter: filter,
    $orderby: "ContentDate/Start desc",
    $top: "1",
    $select: "Name,ContentDate",
  });
  const response = await fetch(`${CDSE_CATALOG_URL}?${params.toString()}`, { signal });
  if (!response.ok) throw new Error(`Catalogo CDSE non disponibile (${response.status})`);
  const data = (await response.json()) as {
    value?: Array<{ ContentDate?: { Start?: string } }>;
  };
  const start = data.value?.[0]?.ContentDate?.Start;
  return start ? { date: start.slice(0, 10) } : null;
}

export function areaBounds(area: MapArea): {
  west: number;
  south: number;
  east: number;
  north: number;
} {
  const longitudes = area.poly.map(([longitude]) => longitude);
  const latitudes = area.poly.map(([, latitude]) => latitude);
  return {
    west: Math.min(...longitudes),
    south: Math.min(...latitudes),
    east: Math.max(...longitudes),
    north: Math.max(...latitudes),
  };
}

export function buildWmsUrl(layer: WmsLayer, area: MapArea, timeWindow?: SceneTimeWindow): string {
  const bounds = areaBounds(area);
  if (layer.provider === "soilgrids" && layer.soilProperty && layer.remoteLayer) {
    const params = new URLSearchParams({
      map: `/map/${layer.soilProperty}.map`,
      SERVICE: "WMS",
      VERSION: "1.1.1",
      REQUEST: "GetMap",
      LAYERS: layer.remoteLayer,
      STYLES: "default",
      BBOX: `${bounds.west},${bounds.south},${bounds.east},${bounds.north}`,
      SRS: "EPSG:4326",
      WIDTH: "512",
      HEIGHT: "512",
      FORMAT: "image/png",
      TRANSPARENT: "true",
    });
    return `https://maps.isric.org/mapserv?${params.toString()}`;
  }

  const timeRange = timeWindow ?? currentSceneWindow();
  const params = new URLSearchParams({
    layer: layer.remoteLayer ?? layer.id,
    west: String(bounds.west),
    south: String(bounds.south),
    east: String(bounds.east),
    north: String(bounds.north),
    from: timeRange.from,
    to: timeRange.to,
    width: "1024",
    height: "1024",
  });
  return `${LAYER_PREVIEW_PATH}?${params.toString()}`;
}
