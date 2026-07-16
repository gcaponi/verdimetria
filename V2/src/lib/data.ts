import { useEffect, useState } from "react";
import type { AppData, FieldData, GeoData, Manifest, Timeseries } from "@/types";

async function loadJson<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`Errore caricamento ${url}`);
  return r.json() as Promise<T>;
}

export function useAppData() {
  const [data, setData] = useState<AppData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      loadJson<Manifest>("data/manifest.json"),
      loadJson<FieldData[]>("data/fields.json"),
      loadJson<Timeseries>("data/timeseries.json"),
      loadJson<GeoData>("data/geo.json"),
    ])
      .then(([manifest, fields, timeseries, geo]) =>
        setData({ manifest, fields, timeseries, geo })
      )
      .catch((e) => setError(String(e)));
  }, []);

  return { data, error };
}

export const CMAP_GRADIENTS: Record<string, string> = {
  RdYlGn:
    "linear-gradient(90deg,#d73027,#f46d43,#fdae61,#fee08b,#d9ef8b,#a6d96a,#66bd63,#1a9850)",
  YlOrRd:
    "linear-gradient(90deg,#ffffcc,#ffeda0,#fed976,#feb24c,#fd8d3c,#fc4e2a,#e31a1c,#bd0026)",
  viridis:
    "linear-gradient(90deg,#440154,#414487,#2a788e,#22a884,#7ad151,#fde725)",
  Spectral:
    "linear-gradient(90deg,#9e0142,#d53e4f,#f46d43,#fdae61,#fee08b,#ffffbf,#e6f598,#abdda4,#66c2a5,#3288bd,#5e4fa2)",
  YlGn: "linear-gradient(90deg,#ffffcc,#d9f0a3,#addd8e,#78c679,#31a354,#006837)",
  copper: "linear-gradient(90deg,#0d0702,#5c3317,#996633,#cc8844,#ffbb66,#ffd9a0)",
  inferno:
    "linear-gradient(90deg,#000004,#420a68,#932667,#dd513a,#fca50a,#fcffa4)",
};

export function fmt(n: number, digits = 2): string {
  return n.toLocaleString("it-IT", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function fieldCentroid(f: FieldData): [number, number] {
  const lon = f.poly.reduce((s, p) => s + p[0], 0) / f.poly.length;
  const lat = f.poly.reduce((s, p) => s + p[1], 0) / f.poly.length;
  return [lon, lat];
}
