import { useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceArea,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Activity, CalendarRange, ScanSearch } from "lucide-react";
import type { FieldAnalysis, NdviPoint } from "@/lib/analysis";

interface Props {
  analysis: FieldAnalysis;
}

type RangeId = "3M" | "1Y";

export default function VegetationCharts({ analysis }: Props) {
  const [range, setRange] = useState<RangeId>("1Y");
  const [cursor, setCursor] = useState<number | null>(null);
  const analysisEnd = Date.parse(`${analysis.period.to}T00:00:00Z`);
  const cutoff = range === "3M" ? analysisEnd - 90 * 86_400_000 : 0;
  const points = analysis.vegetation.points.filter(
    (point) => range === "1Y" || Date.parse(`${point.date}T00:00:00Z`) >= cutoff,
  );
  const visiblePoints = points.length > 0 ? points : analysis.vegetation.points;
  const means = visiblePoints.map((point) => point.mean);
  const selectedIndex = Math.min(cursor ?? visiblePoints.length - 1, visiblePoints.length - 1);
  const selectedPoint = visiblePoints[selectedIndex];
  const percentileData = percentileBars(selectedPoint);

  return (
    <div className="space-y-4">
      <div className="border border-slate-800 bg-slate-900/40 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase text-lime-400">
              <Activity className="h-3.5 w-3.5" /> Serie quantitativa reale
            </p>
            <h3 className="mt-1 text-sm font-semibold text-slate-100">Andamento NDVI Sentinel-2 L2A</h3>
          </div>
          <div className="flex border border-slate-700 bg-slate-950 p-0.5">
            {(["3M", "1Y"] as const).map((rangeId) => (
              <button
                key={rangeId}
                type="button"
                onClick={() => {
                  setRange(rangeId);
                  setCursor(null);
                }}
                className={`h-8 px-3 text-[11px] font-semibold transition-colors ${
                  range === rangeId ? "bg-lime-400 text-slate-950" : "text-slate-400 hover:text-white"
                }`}
              >
                {rangeId === "3M" ? "3 mesi" : "1 anno"}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-end gap-x-6 gap-y-2">
          <div>
            <span className="text-3xl font-bold text-lime-300">{formatNdvi(selectedPoint.mean)}</span>
            <span className="ml-2 text-[11px] text-slate-500">NDVI medio · {formatDate(selectedPoint.date)}</span>
          </div>
          <div className="flex gap-3 text-[11px] text-slate-500">
            <span>Min {formatNdvi(Math.min(...means))}</span>
            <span>Media {formatNdvi(average(means))}</span>
            <span>Max {formatNdvi(Math.max(...means))}</span>
          </div>
        </div>

        <div className="mt-4 h-64 min-w-0">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={visiblePoints}
              margin={{ top: 8, right: 8, left: -18, bottom: 0 }}
              onMouseMove={(state) => {
                if (state?.activeTooltipIndex !== undefined) setCursor(Number(state.activeTooltipIndex));
              }}
            >
              <defs>
                <linearGradient id="realNdviFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#a3e635" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#a3e635" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" vertical={false} />
              <ReferenceArea y1={0.5} y2={1} fill="#34d399" fillOpacity={0.04} />
              <ReferenceArea y1={-0.1} y2={0.3} fill="#fb7185" fillOpacity={0.04} />
              <XAxis
                dataKey="date"
                tick={{ fill: "#64748b", fontSize: 10 }}
                tickLine={false}
                axisLine={{ stroke: "#334155" }}
                tickFormatter={shortDate}
                minTickGap={42}
              />
              <YAxis
                domain={[-0.1, 1]}
                tick={{ fill: "#64748b", fontSize: 10 }}
                tickLine={false}
                axisLine={false}
              />
              <Tooltip
                contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 4, fontSize: 12 }}
                formatter={(value: number) => [formatNdvi(value), "NDVI medio"]}
                labelFormatter={(value: string) => formatDate(value)}
              />
              <Area
                type="monotone"
                dataKey="mean"
                stroke="#a3e635"
                strokeWidth={2}
                fill="url(#realNdviFill)"
                dot={false}
                activeDot={{ r: 4, fill: "#a3e635" }}
              />
              <ReferenceDot
                x={selectedPoint.date}
                y={selectedPoint.mean}
                r={5}
                fill="#a3e635"
                stroke="#0f172a"
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <input
          type="range"
          min={0}
          max={visiblePoints.length - 1}
          value={selectedIndex}
          onChange={(event) => setCursor(Number(event.target.value))}
          className="mt-2 h-8 w-full accent-lime-400"
          aria-label="Seleziona la data NDVI"
        />
        <div className="flex justify-between text-[10px] text-slate-500">
          <span>{formatDate(visiblePoints[0].date)}</span>
          <span>{formatDate(visiblePoints.at(-1)!.date)}</span>
        </div>
        <p className="mt-2 text-[10px] text-slate-500">
          Intervalli di 10 giorni · nuvole, ombre e no-data esclusi con SCL + dataMask.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_240px]">
        <div className="border border-slate-800 bg-slate-900/40 p-4">
          <div className="flex items-center gap-2">
            <ScanSearch className="h-4 w-4 text-cyan-300" />
            <div>
              <h3 className="text-sm font-semibold text-slate-100">Distribuzione dell'osservazione selezionata</h3>
              <p className="text-[10px] text-slate-500">
                Percentili dei pixel validi · {formatDate(selectedPoint.date)}
              </p>
            </div>
          </div>
          <div className="mt-3 h-40 min-w-0">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={percentileData} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
                <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" tick={{ fill: "#64748b", fontSize: 10 }} tickLine={false} axisLine={false} />
                <YAxis domain={[-0.1, 1]} tick={{ fill: "#64748b", fontSize: 10 }} tickLine={false} axisLine={false} />
                <Tooltip
                  cursor={{ fill: "#1e293b", opacity: 0.35 }}
                  contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 4, fontSize: 12 }}
                  formatter={(value: number) => [formatNdvi(value), "NDVI"]}
                />
                <Bar dataKey="value" radius={[3, 3, 0, 0]}>
                  {percentileData.map((item) => <Cell key={item.label} fill={item.color} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="border border-slate-800 bg-slate-900/40 p-4">
          <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase text-cyan-300">
            <CalendarRange className="h-3.5 w-3.5" /> Qualità analisi
          </p>
          <dl className="mt-4 space-y-3 text-[11px]">
            <Metric label="Scene Catalog" value={String(analysis.catalog.sceneCount)} />
            <Metric label="Intervalli validi" value={String(analysis.vegetation.validObservations)} />
            <Metric label="Pixel validi" value={analysis.vegetation.totalValidPixels.toLocaleString("it-IT")} />
            <Metric label="Risoluzione" value={`${analysis.area.resolutionMeters} m`} />
            <Metric
              label="Nuvolosità media"
              value={analysis.catalog.meanCloudCover === null ? "n/d" : `${analysis.catalog.meanCloudCover}%`}
            />
          </dl>
        </div>
      </div>
    </div>
  );
}

function percentileBars(point: NdviPoint) {
  return [
    { label: "P10", value: point.p10 ?? point.min, color: "#fb7185" },
    { label: "P50", value: point.p50 ?? point.mean, color: "#22d3ee" },
    { label: "Media", value: point.mean, color: "#a3e635" },
    { label: "P90", value: point.p90 ?? point.max, color: "#34d399" },
  ];
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-slate-800 pb-2 last:border-0 last:pb-0">
      <dt className="text-slate-500">{label}</dt>
      <dd className="font-semibold text-slate-200">{value}</dd>
    </div>
  );
}

function formatNdvi(value: number): string {
  return value.toLocaleString("it-IT", { minimumFractionDigits: 3, maximumFractionDigits: 3 });
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("it-IT", { day: "2-digit", month: "short", year: "numeric" }).format(
    new Date(`${value}T00:00:00Z`),
  );
}

function shortDate(value: string): string {
  return new Intl.DateTimeFormat("it-IT", { month: "short", year: "2-digit" }).format(
    new Date(`${value}T00:00:00Z`),
  );
}

function average(values: number[]): number {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}