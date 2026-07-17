import type { MapArea } from "@/types";

export interface WmsLayer {
  id: string;
  label: string;
  detail: string;
  provider: "none" | "cdse" | "soilgrids" | "pending";
  remoteLayer?: string;
  soilProperty?: string;
}

export const WMS_LAYERS: WmsLayer[] = [
  { id: "NONE", label: "Solo satellite", detail: "Mappa di base senza overlay", provider: "none" },
  { id: "NDVI", label: "NDVI", detail: "Indice di vegetazione, visualizzazione Sentinel-2", provider: "cdse" },
  { id: "WEAKNESS", label: "Debolezza cronica suolo", detail: "Richiede una serie storica NDVI quantitativa", provider: "pending" },
  { id: "NITROGEN", label: "Azoto totale (N)", detail: "SoilGrids, profondità 0-5 cm, media modellata", provider: "soilgrids", soilProperty: "nitrogen", remoteLayer: "nitrogen_0-5cm_mean" },
  { id: "PHOSPHORUS", label: "Fosforo accessibile (P)", detail: "Non disponibile in SoilGrids", provider: "pending" },
  { id: "POTASSIUM", label: "Potassio scambiabile (K)", detail: "Non disponibile in SoilGrids", provider: "pending" },
  { id: "PH", label: "pH in acqua", detail: "SoilGrids, profondità 0-5 cm, media modellata", provider: "soilgrids", soilProperty: "phh2o", remoteLayer: "phh2o_0-5cm_mean" },
  { id: "SOC", label: "Carbonio organico (SOC)", detail: "SoilGrids, profondità 0-5 cm, media modellata", provider: "soilgrids", soilProperty: "soc", remoteLayer: "soc_0-5cm_mean" },
  { id: "CLAY", label: "Argilla", detail: "SoilGrids, profondità 0-5 cm, media modellata", provider: "soilgrids", soilProperty: "clay", remoteLayer: "clay_0-5cm_mean" },
  { id: "ANOMALY", label: "Anomalia geologica", detail: "Richiede pipeline anomaly detection backend", provider: "pending" },
  { id: "PCA", label: "PCA geologica (RGB)", detail: "Richiede pipeline PCA backend", provider: "pending" },
  { id: "EVI", label: "EVI", detail: "Indice di vegetazione migliorato", provider: "cdse" },
  { id: "SAVI", label: "SAVI", detail: "Indice di vegetazione corretto per il suolo", provider: "cdse" },
  { id: "NDWI", label: "NDWI", detail: "Indice visuale della presenza d'acqua", provider: "cdse" },
  { id: "AGRICULTURE", label: "Composito agricolo", detail: "Composito multispettrale visuale", provider: "cdse" },
  { id: "GEOLOGY", label: "Composito geologico", detail: "Composito multispettrale visuale", provider: "cdse" },
];

const WMS_BASE_URL =
  "https://sh.dataspace.copernicus.eu/ogc/wms/1ca53dc1-1760-4d9a-b80d-52f4d69602d7";

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
