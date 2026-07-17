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
      gradient: "linear-gradient(90deg,#7f1d1d,#ef4444,#facc15,#a3e635,#166534)",
      lowLabel: "basso",
      highLabel: "alto",
      note: "Scala visuale WMS; i valori quantitativi arrivano dalla Process API.",
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
      gradient: "linear-gradient(90deg,#7c2d12,#fef3c7,#bae6fd,#0284c7,#0c4a6e)",
      lowLabel: "asciutto",
      highLabel: "acqua",
      note: "Scala qualitativa del layer visuale CDSE.",
    },
  },
  {
    id: "AGRICULTURE",
    label: "Composito agricolo",
    detail: "Composito multispettrale visuale",
    provider: "cdse",
    group: "vegetation",
  },
  {
    id: "GEOLOGY",
    label: "Composito geologico",
    detail: "Composito multispettrale visuale, non carta geologica",
    provider: "cdse",
    group: "vegetation",
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

const WMS_BASE_URL =
  "https://sh.dataspace.copernicus.eu/ogc/wms/1ca53dc1-1760-4d9a-b80d-52f4d69602d7";

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

export async function loadCdseCatalog(signal?: AbortSignal): Promise<WmsLayer[]> {
  const params = new URLSearchParams({ SERVICE: "WMS", REQUEST: "GetCapabilities" });
  const response = await fetch(`${WMS_BASE_URL}?${params.toString()}`, { signal });
  if (!response.ok) throw new Error(`Capabilities CDSE non disponibili (${response.status})`);

  const document = new DOMParser().parseFromString(await response.text(), "application/xml");
  if (document.querySelector("parsererror")) throw new Error("Capabilities CDSE non valide");

  const knownRemoteLayers = new Set(
    WMS_LAYERS.filter((layer) => layer.provider === "cdse").map(
      (layer) => layer.remoteLayer ?? layer.id
    )
  );

  return Array.from(document.getElementsByTagName("Layer"))
    .map((node) => ({
      name: directChildText(node, "Name"),
      title: directChildText(node, "Title"),
    }))
    .filter(
      (entry): entry is { name: string; title: string } =>
        Boolean(entry.name && entry.title && entry.name !== "WMS" && entry.name !== "default")
    )
    .filter((entry) => !knownRemoteLayers.has(entry.name))
    .map((entry) => ({
      id: `CDSE:${entry.name}`,
      label: entry.title,
      detail: `Layer visuale ${entry.name} dalla Configuration Instance CDSE`,
      provider: "cdse" as const,
      group: "cdse-catalog" as const,
      remoteLayer: entry.name,
    }))
    .sort((left, right) => left.label.localeCompare(right.label, "it"));
}

function directChildText(node: Element, tagName: string): string {
  const child = Array.from(node.children).find((element) => element.localName === tagName);
  return child?.textContent?.trim() ?? "";
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

export function buildWmsUrl(layer: WmsLayer, area: MapArea): string {
  const bounds = areaBounds(area);
  if (layer.provider === "soilgrids" && layer.soilProperty && layer.remoteLayer) {
    const params = new URLSearchParams({
      SERVICE: "WMS",
      VERSION: "1.1.1",
      REQUEST: "GetMap",
      LAYERS: layer.remoteLayer,
      STYLES: "",
      BBOX: `${bounds.west},${bounds.south},${bounds.east},${bounds.north}`,
      SRS: "EPSG:4326",
      WIDTH: "1024",
      HEIGHT: "1024",
      FORMAT: "image/png",
      TRANSPARENT: "true",
    });
    return `https://maps.isric.org/mapserv/${layer.soilProperty}?${params.toString()}`;
  }

  const endDate = new Date();
  const startDate = new Date(endDate);
  startDate.setUTCDate(startDate.getUTCDate() - 90);
  const datePart = (date: Date) => date.toISOString().slice(0, 10);
  const params = new URLSearchParams({
    SERVICE: "WMS",
    VERSION: "1.1.1",
    REQUEST: "GetMap",
    LAYERS: layer.remoteLayer ?? layer.id,
    BBOX: `${bounds.west},${bounds.south},${bounds.east},${bounds.north}`,
    SRS: "EPSG:4326",
    WIDTH: "1024",
    HEIGHT: "1024",
    FORMAT: "image/png",
    TRANSPARENT: "true",
    TIME: `${datePart(startDate)}/${datePart(endDate)}`,
    MAXCC: "30",
  });
  return `${WMS_BASE_URL}?${params.toString()}`;
}
