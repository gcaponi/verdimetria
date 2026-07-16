import type { AppData, FieldData } from "@/types";
import { Card, SectionTitle, HealthBars, RatingChip } from "@/components/ui-bits";
import { fmt } from "@/lib/data";
import { cn } from "@/lib/utils";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";

interface Props {
  data: AppData;
  field: FieldData;
  onSelectField: (id: string) => void;
}

export default function OverviewSection({ data, field, onSelectField }: Props) {
  const hist = field.hist.counts.map((c, i) => ({
    bin: fmt((field.hist.edges[i] + field.hist.edges[i + 1]) / 2, 1),
    count: c,
    mid: (field.hist.edges[i] + field.hist.edges[i + 1]) / 2,
  }));

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <Kpi label="NDVI medio" value={fmt(field.ndvi)} sub="rilievo corrente" tone={field.ndvi > 0.45 ? "good" : field.ndvi > 0.32 ? "warn" : "bad"} />
        <Kpi label="Debolezza cronica" value={fmt(field.weakness)} sub={`${fmt(field.weak_frac * 100, 0)}% sup. critica`} tone={field.weakness < 0.3 ? "good" : field.weakness < 0.55 ? "warn" : "bad"} />
        <Kpi label="Superficie" value={`${fmt(field.area_ha, 0)} ha`} sub={field.crop} tone="neutral" />
        <Kpi label="Anomalia geologica" value={fmt(field.anomaly_mean)} sub="score medio nel campo" tone={field.anomaly_mean > 0.5 ? "warn" : "neutral"} />
      </div>

      <Card>
        <SectionTitle kicker="Salute vegetazione" title="Ripartizione dell'area per vigoria" />
        <HealthBars health={field.health} />
      </Card>

      <Card>
        <SectionTitle kicker="Distribuzione" title="Istogramma NDVI nel campo" />
        <div className="h-40">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={hist} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
              <XAxis dataKey="bin" tick={{ fill: "#94a3b8", fontSize: 10 }} tickLine={false} axisLine={{ stroke: "#334155" }} />
              <YAxis tick={{ fill: "#94a3b8", fontSize: 10 }} tickLine={false} axisLine={false} />
              <Tooltip
                contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 8, fontSize: 12 }}
                labelStyle={{ color: "#e2e8f0" }}
                formatter={(v: number) => [`${v} pixel`, "Frequenza"]}
              />
              <Bar dataKey="count" radius={[3, 3, 0, 0]}>
                {hist.map((h) => (
                  <Cell key={h.bin} fill={h.mid <= 0.32 ? "#f87171" : h.mid <= 0.5 ? "#fbbf24" : "#34d399"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card>
        <SectionTitle kicker="Tutti i campi" title="Confronto parcelle — clicca per selezionare" />
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[13px]">
            <thead>
              <tr className="border-b border-slate-800 text-[11px] uppercase tracking-wide text-slate-500">
                <th className="py-2 pr-3 font-medium">Campo</th>
                <th className="py-2 pr-3 font-medium">Coltura</th>
                <th className="py-2 pr-3 font-medium text-right">NDVI</th>
                <th className="py-2 pr-3 font-medium text-right">Debolezza</th>
                <th className="py-2 font-medium text-right">SOM</th>
              </tr>
            </thead>
            <tbody>
              {data.fields.map((f) => (
                <tr
                  key={f.id}
                  onClick={() => onSelectField(f.id)}
                  className={cn(
                    "cursor-pointer border-b border-slate-800/60 transition-colors hover:bg-slate-800/40",
                    f.id === field.id && "bg-lime-500/5"
                  )}
                >
                  <td className="py-2 pr-3 font-medium text-slate-200">
                    {f.id === field.id && <span className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full bg-lime-400 align-middle" />}
                    {f.name}
                  </td>
                  <td className="py-2 pr-3 text-slate-400">{f.crop}</td>
                  <td className={cn("py-2 pr-3 text-right font-medium", f.ndvi > 0.45 ? "text-emerald-300" : f.ndvi > 0.32 ? "text-amber-300" : "text-rose-300")}>
                    {fmt(f.ndvi)}
                  </td>
                  <td className={cn("py-2 pr-3 text-right", f.weakness > 0.55 ? "text-rose-300" : f.weakness > 0.3 ? "text-amber-300" : "text-slate-300")}>
                    {fmt(f.weakness)}
                  </td>
                  <td className="py-2 text-right">
                    <RatingChip value={f.ratings.som} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function Kpi({ label, value, sub, tone }: { label: string; value: string; sub: string; tone: "good" | "warn" | "bad" | "neutral" }) {
  const tones = {
    good: "text-emerald-300",
    warn: "text-amber-300",
    bad: "text-rose-300",
    neutral: "text-slate-100",
  };
  return (
    <Card className="p-4">
      <div className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className={cn("mt-1 text-2xl font-bold", tones[tone])}>{value}</div>
      <div className="mt-0.5 text-[11px] text-slate-500">{sub}</div>
    </Card>
  );
}
