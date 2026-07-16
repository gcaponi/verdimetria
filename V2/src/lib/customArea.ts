// Costruisce un FieldData completo per un'area disegnata dall'utente,
// replicando la logica del generatore Python (ratings, insight, serie NDVI).
import type { FieldData, Insight } from "@/types";
import type { Grids } from "@/lib/grids";
import { computeZonal } from "@/lib/grids";

function mulberry32(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// generatore gaussiano (Box-Muller) da PRNG seedato
function gauss(rnd: () => number) {
  return () => {
    const u = Math.max(rnd(), 1e-9);
    const v = Math.max(rnd(), 1e-9);
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  };
}

function rating(v: number, good: number, ok: number): string {
  return v >= good ? "BUONO" : v >= ok ? "SUFFICIENTE" : "BASSO";
}

const LABELS: Record<string, string> = {
  n: "azoto totale",
  p: "fosforo accessibile",
  k: "potassio scambiabile",
  som: "sostanza organica",
  ph: "pH",
};

function genInsights(f: FieldData, lowRes: boolean): Insight[] {
  const ins: Insight[] = [];
  const order: Record<string, number> = { BASSO: 0, ACIDO: 0, ALTO: 0, SUFFICIENTE: 1, BUONO: 2 };
  const keys = ["n", "p", "k", "som", "ph"] as const;
  const worst = keys.reduce((a, b) => (order[f.ratings[a]] <= order[f.ratings[b]] ? a : b));
  const best = keys.reduce((a, b) => (order[f.ratings[a]] >= order[f.ratings[b]] ? a : b));

  if (f.weak_frac > 0.5) {
    ins.push({
      t: "alert",
      title: "Debolezza cronica del suolo",
      text: `Il ${Math.round(f.weak_frac * 100)}% della superficie mostra NDVI cronicamente sotto la media dell'area in tutti i rilievi degli ultimi 3 anni: non è un evento isolato ma un pattern strutturale.`,
    });
  } else if (f.weak_frac > 0.1) {
    ins.push({
      t: "warn",
      title: "Zone di stress localizzate",
      text: `Circa il ${Math.round(f.weak_frac * 100)}% della superficie mostra vigoria cronicamente ridotta, concentrato in macchie ben definite visibili nel layer Debolezza.`,
    });
  } else {
    ins.push({
      t: "ok",
      title: "Vigoria uniforme",
      text: "Nessuna zona di debolezza cronica rilevata: l'NDVI è coerente con la media dell'area in tutta la serie storica.",
    });
  }

  if (order[f.ratings[worst]] === 0) {
    const sug: Record<string, string> = {
      n: "Valutare concimazione azotata frazionata o rotazione con leguminosa (favino) per ripristinare la dotazione.",
      p: "Suoli calcarei tendono a fissare il fosforo: preferire concimi fosfatici localizzati in banda piuttosto che spaglio.",
      k: "Integrare potassio con concimazione di fondo; monitorare dopo la raccolta.",
      som: "Sostanza organica bassa: sovescio, interramento di residui colturali o compost sono la via più efficace negli Iblei.",
      ph: "pH fuori range ottimale: verificare con analisi di laboratorio prima di correggere.",
    };
    ins.push({
      t: "warn",
      title: `Fattore limitante probabile: ${LABELS[worst]}`,
      text: `Tra le proprietà misurate, ${LABELS[worst]} è quella con lo scarto più marcato rispetto ai valori di riferimento. ${sug[worst]}`,
    });
  }
  if (order[f.ratings[best]] === 2) {
    ins.push({
      t: "ok",
      title: `Punto di forza: ${LABELS[best]}`,
      text: `I valori di ${LABELS[best]} sono nel range ottimale su tutta la superficie selezionata.`,
    });
  }
  if (f.ph > 7.8) {
    ins.push({
      t: "info",
      title: "Suolo calcareo tipico ibleo",
      text: "pH > 7.8: attenzione alla disponibilità di fosforo e microelementi (Fe, Zn) anche dove i totali sono buoni. Confermare con estrazione di laboratorio.",
    });
  }
  if (lowRes) {
    ins.push({
      t: "info",
      title: "Area piccola rispetto alla griglia",
      text: "La selezione copre pochi pixel della griglia (~30 m): le medie sono indicative. Allarga l'area per statistiche più robuste.",
    });
  }
  ins.push({
    t: "info",
    title: "Nota metodologica",
    text: "Stime da modello su dati telerilevati e SoilGrids: sono ipotesi di lettura da validare con analisi di laboratorio prima di decisioni agronomiche.",
  });
  return ins;
}

/** Serie NDVI procedurale (stessa logica del generatore Python). */
export function genNdviSeries(weakness: number, dates: string[], seed: number): number[] {
  const rnd = mulberry32(seed);
  const g = gauss(rnd);
  const base = weakness < 0.3 ? 0.62 : weakness < 0.55 ? 0.5 : 0.42;
  const amp = 1.0 - 0.5 * weakness;
  const n = dates.length;
  let walk = 0;
  const walkArr: number[] = [];
  for (let i = 0; i < n; i++) {
    walk += g() * 0.015;
    walkArr.push(walk);
  }
  const wMean = walkArr.reduce((s, v) => s + v, 0) / n;
  const vals = dates.map((d, i) => {
    const doy = dayOfYear(d);
    const season = 0.5 + 0.28 * Math.sin((2 * Math.PI * (doy - 19)) / 365);
    return base * season * amp + 0.1 + (walkArr[i] - wMean) + g() * 0.022;
  });
  // eventi (raccolta/lavorazioni): 2-3 cali netti
  const events = 2 + Math.floor(rnd() * 2);
  for (let e = 0; e < events; e++) {
    const i = 5 + Math.floor(rnd() * (n - 10));
    const dur = 1 + Math.floor(rnd() * 2);
    const drop = 0.08 + rnd() * 0.1;
    for (let j = i; j < Math.min(n, i + dur); j++) vals[j] -= drop;
  }
  return vals.map((v) => Math.round(Math.min(0.92, Math.max(0.05, v)) * 1000) / 1000);
}

function dayOfYear(iso: string): number {
  const d = new Date(iso + "T00:00:00Z");
  return Math.floor((d.getTime() - Date.UTC(d.getUTCFullYear(), 0, 0)) / 86400000);
}

export interface CustomAreaResult {
  field: FieldData;
}

export function buildCustomField(
  poly: [number, number][],
  grids: Grids,
  id: string,
  name: string
): CustomAreaResult {
  const z = computeZonal(grids, poly);
  const m = z.means;
  const r3 = (v: number) => Math.round(v * 1000) / 1000;
  const r2 = (v: number) => Math.round(v * 100) / 100;
  const r1 = (v: number) => Math.round(v * 10) / 10;

  const healthy = (z.ndviValues.filter((v) => v > 0.5).length / z.count) * 100;
  const marginal = (z.ndviValues.filter((v) => v > 0.32 && v <= 0.5).length / z.count) * 100;
  const stressed = 100 - healthy - marginal;

  const edges = Array.from({ length: 13 }, (_, i) => -0.1 + (i * 1.0) / 12);
  const counts = new Array(12).fill(0);
  z.ndviValues.forEach((v) => {
    const b = Math.min(11, Math.max(0, Math.floor(((v + 0.1) / 1.0) * 12)));
    counts[b]++;
  });

  const field: FieldData = {
    id,
    name,
    crop: "Selezione libera",
    poly,
    area_ha: r1(z.count * grids.meta.px_ha),
    n: r1(m.n),
    p: r1(m.p),
    k: r1(m.k),
    ph: r2(m.ph),
    som: r2(m.som),
    clay: r1(m.clay),
    sand: r1(m.sand),
    silt: r1(100 - m.clay - m.sand),
    ndvi: r3(m.ndvi),
    weakness: r3(m.weakness),
    weak_frac: r3(z.weakOver / z.count),
    ratings: {
      n: rating(m.n, 2000, 1200),
      p: rating(m.p, 18, 10),
      k: rating(m.k, 180, 130),
      som: rating(m.som, 1.8, 1.2),
      ph: m.ph >= 6.5 && m.ph <= 7.8 ? "BUONO" : m.ph > 7.8 ? "ALTO" : "ACIDO",
    },
    health: { healthy: r1(healthy), marginal: r1(marginal), stressed: r1(stressed) },
    hist: { counts, edges: edges.map((e) => r2(e)) },
    anomaly_mean: r3(m.anomaly),
    insights: [],
  };
  field.insights = genInsights(field, z.count < 10);
  return { field };
}
