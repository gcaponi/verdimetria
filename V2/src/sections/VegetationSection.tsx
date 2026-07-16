import { useMemo, useState } from "react";
import type { AppData, FieldData } from "@/types";
import { Card, SectionTitle, HealthBars } from "@/components/ui-bits";
import { fmt } from "@/lib/data";
import { cn } from "@/lib/utils";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceDot, ReferenceArea,
} from "recharts";
import { LayerToggle } from "@/sections/SoilSection";

interface Props {
  data: AppData;
  field: FieldData;
  activeLayerId: string;
  onLayerChange: (id: string) => void;
}

const RANGES = [
  { id: "3M", label: "3M", days: 90 },
  { id: "1Y", label: "1A", days: 365 },
  { id: "ALL", label: "3 anni", days: 9999 },
];

export default function VegetationSection({ data, field, activeLayerId, onLayerChange }: Props) {
  const [range, setRange] = useState("1Y");
  const [cursor, setCursor] = useState<number | null>(null);

  const { dates, series } = data.timeseries;
  const values = series[field.id];

  const points = useMemo(() => {
    const days = RANGES.find((r) => r.id === range)!.days;
    const cutoff = days >= 9999 ? 0 : Math.max(0, dates.length - Math.ceil(days / 10));
    return dates.slice(cutoff).map((d, i) => ({
      date: d,
      v: values[cutoff + i],
      idx: cutoff + i,
    }));
  }, [range, dates, values]);

  const selIdx = cursor ?? points.length - 1;
  const sel = points[Math.min(selIdx, points.length - 1)];

  const stats = useMemo(() => {
    const vs = points.map((p) => p.v);
    return {
      min: Math.min(...vs),
      max: Math.max(...vs),
      avg: vs.reduce((s, v) => s + v, 0) / vs.length,
    };
  }, [points]);

  return (
    <div className="space-y-4">
      <Card>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <SectionTitle kicker="Monitoraggio vegetazione" title="Andamento NDVI — Sentinel-2" />
          <div className="flex gap-1 rounded-lg border border-slate-800 bg-slate-950 p-0.5">
            {RANGES.map((r) => (
              <button
                key={r.id}
                onClick={() => { setRange(r.id); setCursor(null); }}
                className={cn(
                  "rounded-md px-3 py-1 text-[12px] font-medium transition-colors",
                  range === r.id ? "bg-lime-400/15 text-lime-300" : "text-slate-400 hover:text-slate-200"
                )}
              >
                {r.label}
              </button>
            ))}
          </div>
        </div>

        <div className="mb-3 flex flex-wrap items-baseline gap-x-6 gap-y-1">
          <div>
            <span className="text-3xl font-bold text-lime-300">{fmt(sel.v)}</span>
            <span className="ml-2 text-[12px] text-slate-400">NDVI del {sel.date.split("-").reverse().join("/")}</span>
          </div>
          <div className="flex gap-3 text-[11px] text-slate-500">
            <span>Min {fmt(stats.min)}</span>
            <span>Med {fmt(stats.avg)}</span>
            <span>Max {fmt(stats.max)}</span>
          </div>
        </div>

        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={points} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}
              onMouseMove={(s) => {
                if (s && s.activeTooltipIndex != null) setCursor(Number(s.activeTooltipIndex));
              }}
              onMouseLeave={() => setCursor(null)}
            >
              <defs>
                <linearGradient id="ndviFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#a3e635" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#a3e635" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <ReferenceArea y1={0.5} y2={1} fill="#34d399" fillOpacity={0.05} />
              <ReferenceArea y1={-0.1} y2={0.32} fill="#f87171" fillOpacity={0.05} />
              <XAxis dataKey="date" tick={{ fill: "#94a3b8", fontSize: 10 }} tickLine={false}
                axisLine={{ stroke: "#334155" }}
                tickFormatter={(d: string) => d.slice(2, 7).split("-").reverse().join("/")}
                minTickGap={48} />
              <YAxis domain={[-0.1, 1]} tick={{ fill: "#94a3b8", fontSize: 10 }} tickLine={false} axisLine={false} />
              <Tooltip
                contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 8, fontSize: 12 }}
                formatter={(v: number) => [fmt(v, 3), "NDVI"]}
                labelFormatter={(d: string) => d.split("-").reverse().join("/")}
              />
              <Area type="monotone" dataKey="v" stroke="#a3e635" strokeWidth={2} fill="url(#ndviFill)" dot={false} />
              <ReferenceDot x={sel.date} y={sel.v} r={5} fill="#a3e635" stroke="#0f172a" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <input
          type="range"
          min={0}
          max={points.length - 1}
          value={Math.min(selIdx, points.length - 1)}
          onChange={(e) => setCursor(Number(e.target.value))}
          className="mt-2 w-full accent-lime-400"
        />
        <div className="flex justify-between text-[10px] text-slate-500">
          <span>{points[0].date.split("-").reverse().join("/")}</span>
          <span>{points[points.length - 1].date.split("-").reverse().join("/")}</span>
        </div>
      </Card>

      <Card>
        <SectionTitle kicker="Stato attuale" title="Ripartizione per vigoria" />
        <HealthBars health={field.health} />
        <div className="mt-4 flex flex-wrap gap-2">
          <LayerToggle id="ndvi" label="NDVI sulla mappa" active={activeLayerId} onChange={onLayerChange} />
          <LayerToggle id="weakness" label="Debolezza cronica" active={activeLayerId} onChange={onLayerChange} />
        </div>
      </Card>

      <Card>
        <p className="text-[12px] leading-relaxed text-slate-500">
          <strong className="text-slate-300">Come leggerlo:</strong> valori sopra 0,5 indicano
          vegetazione vigorosa; sotto 0,32 stress o suolo nudo. La stagionalità riflette il ciclo
          colturale mediterraneo (picco primaverile, minimo estivo). Nel prototipo la serie è
          sintetica; in produzione arriva dalla Process API CDSE (evalscript NDVI FLOAT32, L2A),
          come previsto dalla Fase 2 del PRD.
        </p>
      </Card>
    </div>
  );
}
