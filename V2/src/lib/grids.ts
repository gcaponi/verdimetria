// Caricamento e interrogazione delle griglie grezze (uint8 quantizzate).
// Convenzione: riga 0 = bordo nord (come l'export Python), valori = vmin + q/255*(vmax-vmin).

export interface GridsMeta {
  rows: number;
  cols: number;
  bounds: { west: number; south: number; east: number; north: number };
  px_ha: number;
  layers: { id: string; vmin: number; vmax: number }[];
}

export interface Grids {
  meta: GridsMeta;
  data: Record<string, Float32Array>; // rows*cols, row-major, riga 0 = nord
}

let cache: Promise<Grids> | null = null;

export function loadGrids(): Promise<Grids> {
  if (cache) return cache;
  cache = (async () => {
    const meta = (await (await fetch("data/grids.json")).json()) as GridsMeta;
    const buf = await (await fetch("data/grids.bin")).arrayBuffer();
    const u8 = new Uint8Array(buf);
    const n = meta.rows * meta.cols;
    const data: Record<string, Float32Array> = {};
    meta.layers.forEach((l, i) => {
      const out = new Float32Array(n);
      const off = i * n;
      const scale = (l.vmax - l.vmin) / 255;
      for (let j = 0; j < n; j++) out[j] = l.vmin + u8[off + j] * scale;
      data[l.id] = out;
    });
    return { meta, data };
  })();
  return cache;
}

/** Ray-casting point-in-polygon su coordinate lon/lat. */
export function pointInPolygon(lon: number, lat: number, poly: [number, number][]): boolean {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i];
    const [xj, yj] = poly[j];
    if (yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) {
      inside = !inside;
    }
  }
  return inside;
}

export interface ZonalResult {
  count: number;
  means: Record<string, number>;
  ndviValues: number[];
  weakOver: number; // celle con weakness > 0.55
}

/** Statistiche zonali su tutte le griglie per un poligono (lon/lat). */
export function computeZonal(grids: Grids, poly: [number, number][]): ZonalResult {
  const { rows, cols, bounds } = grids.meta;
  const dlon = (bounds.east - bounds.west) / cols;
  const dlat = (bounds.north - bounds.south) / rows;

  // bounding box del poligono in indici di griglia
  const lons = poly.map((p) => p[0]);
  const lats = poly.map((p) => p[1]);
  const c0 = Math.max(0, Math.floor((Math.min(...lons) - bounds.west) / dlon));
  const c1 = Math.min(cols - 1, Math.ceil((Math.max(...lons) - bounds.west) / dlon));
  const r0 = Math.max(0, Math.floor((bounds.north - Math.max(...lats)) / dlat));
  const r1 = Math.min(rows - 1, Math.ceil((bounds.north - Math.min(...lats)) / dlat));

  const sums: Record<string, number> = {};
  Object.keys(grids.data).forEach((k) => (sums[k] = 0));
  const ndviValues: number[] = [];
  let count = 0;
  let weakOver = 0;

  for (let r = r0; r <= r1; r++) {
    const lat = bounds.north - (r + 0.5) * dlat;
    for (let c = c0; c <= c1; c++) {
      const lon = bounds.west + (c + 0.5) * dlon;
      if (!pointInPolygon(lon, lat, poly)) continue;
      const idx = r * cols + c;
      for (const k of Object.keys(grids.data)) sums[k] += grids.data[k][idx];
      ndviValues.push(grids.data.ndvi[idx]);
      if (grids.data.weakness[idx] > 0.55) weakOver++;
      count++;
    }
  }

  // fallback: se il poligono è più piccolo di un pixel, usa la cella del centroide
  if (count === 0) {
    const cl = (Math.min(...lons) + Math.max(...lons)) / 2;
    const ct = (Math.min(...lats) + Math.max(...lats)) / 2;
    const c = Math.min(cols - 1, Math.max(0, Math.floor((cl - bounds.west) / dlon)));
    const r = Math.min(rows - 1, Math.max(0, Math.floor((bounds.north - ct) / dlat)));
    const idx = r * cols + c;
    for (const k of Object.keys(grids.data)) sums[k] += grids.data[k][idx];
    ndviValues.push(grids.data.ndvi[idx]);
    if (grids.data.weakness[idx] > 0.55) weakOver = 1;
    count = 1;
  }

  const means: Record<string, number> = {};
  for (const k of Object.keys(sums)) means[k] = sums[k] / count;
  return { count, means, ndviValues, weakOver };
}
