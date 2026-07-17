export interface LayerSpec {
  id: string;
  label: string;
  cmap: string | null;
  vmin: number | null;
  vmax: number | null;
  unit: string;
}

export interface Manifest {
  bounds: { west: number; south: number; east: number; north: number };
  layers: LayerSpec[];
}

export type RatingKey = "n" | "p" | "k" | "som" | "ph";

export interface Insight {
  t: "alert" | "warn" | "ok" | "info";
  title: string;
  text: string;
}

export interface MapArea {
  id: string;
  name: string;
  poly: [number, number][];
  area_ha: number;
}

export interface FieldData extends MapArea {
  crop: string;
  n: number;
  p: number;
  k: number;
  ph: number;
  som: number;
  clay: number;
  sand: number;
  silt: number;
  ndvi: number;
  weakness: number;
  weak_frac: number;
  ratings: Record<RatingKey, string>;
  health: { healthy: number; marginal: number; stressed: number };
  hist: { counts: number[]; edges: number[] };
  anomaly_mean: number;
  insights: Insight[];
}

export interface Timeseries {
  dates: string[];
  series: Record<string, number[]>;
}

export interface GeoData {
  geo: Insight[];
  top_locations: { lon: number; lat: number; score: number }[];
  aoi_avg: Record<string, number>;
}

export interface AppData {
  manifest: Manifest;
  fields: FieldData[];
  timeseries: Timeseries;
  geo: GeoData;
}
