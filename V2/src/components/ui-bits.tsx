import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { CMAP_GRADIENTS } from "@/lib/data";
import type { LayerSpec } from "@/types";
import { AlertTriangle, CheckCircle2, Info, AlertOctagon } from "lucide-react";

export function Card({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-xl border border-slate-800 bg-slate-900/70 p-5",
        className
      )}
    >
      {children}
    </div>
  );
}

export function SectionTitle({
  kicker,
  title,
}: {
  kicker?: string;
  title: string;
}) {
  return (
    <div className="mb-4">
      {kicker && (
        <div className="text-[11px] font-semibold uppercase tracking-widest text-lime-400/80">
          {kicker}
        </div>
      )}
      <h3 className="text-lg font-semibold text-slate-100">{title}</h3>
    </div>
  );
}

const RATING_STYLE: Record<string, string> = {
  BUONO: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  SUFFICIENTE: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  BASSO: "bg-rose-500/15 text-rose-300 border-rose-500/30",
  ALTO: "bg-rose-500/15 text-rose-300 border-rose-500/30",
  ACIDO: "bg-rose-500/15 text-rose-300 border-rose-500/30",
};

export function RatingChip({ value }: { value: string }) {
  return (
    <span
      className={cn(
        "inline-block rounded-md border px-2 py-0.5 text-[11px] font-semibold",
        RATING_STYLE[value] ?? "bg-slate-700 text-slate-300"
      )}
    >
      {value}
    </span>
  );
}

export function GradientLegend({ layer }: { layer: LayerSpec }) {
  if (!layer.cmap) return null;
  return (
    <div className="rounded-lg border border-slate-700/70 bg-slate-900/90 px-3 py-2 shadow-lg backdrop-blur">
      <div className="mb-1 text-[11px] font-medium text-slate-200">
        {layer.label}
        {layer.unit ? ` (${layer.unit})` : ""}
      </div>
      <div
        className="h-2.5 w-44 rounded"
        style={{ background: CMAP_GRADIENTS[layer.cmap] }}
      />
      <div className="mt-0.5 flex justify-between text-[10px] text-slate-400">
        <span>{layer.vmin}</span>
        <span>{layer.vmax}</span>
      </div>
    </div>
  );
}

const INSIGHT_ICON = {
  alert: { Icon: AlertOctagon, cls: "text-rose-400 border-rose-500/30 bg-rose-500/10" },
  warn: { Icon: AlertTriangle, cls: "text-amber-400 border-amber-500/30 bg-amber-500/10" },
  ok: { Icon: CheckCircle2, cls: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10" },
  info: { Icon: Info, cls: "text-sky-400 border-sky-500/30 bg-sky-500/10" },
};

export function InsightCard({
  t,
  title,
  text,
}: {
  t: "alert" | "warn" | "ok" | "info";
  title: string;
  text: string;
}) {
  const { Icon, cls } = INSIGHT_ICON[t];
  return (
    <div className={cn("flex gap-3 rounded-xl border p-4", cls)}>
      <Icon className="mt-0.5 h-5 w-5 shrink-0" />
      <div>
        <div className="text-sm font-semibold text-slate-100">{title}</div>
        <p className="mt-1 text-[13px] leading-relaxed text-slate-300">{text}</p>
      </div>
    </div>
  );
}

export function HealthBars({
  health,
}: {
  health: { healthy: number; marginal: number; stressed: number };
}) {
  const rows = [
    { label: "In salute", v: health.healthy, cls: "bg-emerald-400" },
    { label: "Marginale", v: health.marginal, cls: "bg-amber-400" },
    { label: "Stressato", v: health.stressed, cls: "bg-rose-400" },
  ];
  return (
    <div className="space-y-2">
      {rows.map((r) => (
        <div key={r.label} className="flex items-center gap-3">
          <span className="w-20 text-xs text-slate-400">{r.label}</span>
          <div className="h-2 flex-1 overflow-hidden rounded bg-slate-800">
            <div className={cn("h-full rounded", r.cls)} style={{ width: `${r.v}%` }} />
          </div>
          <span className="w-12 text-right text-xs font-medium text-slate-200">
            {r.v}%
          </span>
        </div>
      ))}
    </div>
  );
}
