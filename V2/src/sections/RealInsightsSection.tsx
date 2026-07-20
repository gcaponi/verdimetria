import { AlertTriangle, Bot, CheckCircle2, CircleAlert, Info, Sparkles } from "lucide-react";
import type { AnalysisInsight, FieldAnalysis } from "@/lib/analysis";
import { cn } from "@/lib/utils";

interface Props {
  analysis: FieldAnalysis;
}

const TONES = {
  alert: { icon: CircleAlert, border: "border-rose-400/40", iconColor: "text-rose-300", background: "bg-rose-400/5" },
  warn: { icon: AlertTriangle, border: "border-amber-400/40", iconColor: "text-amber-300", background: "bg-amber-400/5" },
  ok: { icon: CheckCircle2, border: "border-emerald-400/40", iconColor: "text-emerald-300", background: "bg-emerald-400/5" },
  info: { icon: Info, border: "border-cyan-400/40", iconColor: "text-cyan-300", background: "bg-cyan-400/5" },
} as const;

export default function RealInsightsSection({ analysis }: Props) {
  const generated = analysis.ai.status === "generated";
  return (
    <div className="space-y-4">
      <div className="border border-slate-800 bg-slate-900/40 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center border border-cyan-400/30 bg-cyan-400/10 text-cyan-300">
              {generated ? <Sparkles className="h-5 w-5" /> : <Bot className="h-5 w-5" />}
            </span>
            <div>
              <p className="text-[10px] font-semibold uppercase text-cyan-300">Interpretazione da evidenze reali</p>
              <h3 className="mt-1 text-sm font-semibold text-slate-100">{analysis.ai.summary}</h3>
            </div>
          </div>
          <div className="text-right text-[10px] text-slate-500">
            <div className={generated ? "text-emerald-300" : "text-amber-300"}>
              {generated ? "AI generata" : "Fallback deterministico"}
            </div>
            <div>{analysis.ai.provider}</div>
            <div>{analysis.ai.model}</div>
          </div>
        </div>
      </div>

      <div className="grid gap-3">
        {analysis.ai.insights.map((insight, index) => (
          <InsightCard key={`${insight.title}-${index}`} insight={insight} />
        ))}
      </div>

      <div className="border-l-2 border-amber-400/70 bg-amber-400/5 px-4 py-3 text-[11px] leading-relaxed text-slate-400">
        {analysis.disclaimer} L'AI riceve solo metriche aggregate CDSE e non identifica automaticamente
        carenze, malattie o cause agronomiche.
      </div>
    </div>
  );
}

function InsightCard({ insight }: { insight: AnalysisInsight }) {
  const tone = TONES[insight.tone];
  const Icon = tone.icon;
  return (
    <article className={cn("border p-4", tone.border, tone.background)}>
      <div className="flex gap-3">
        <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", tone.iconColor)} />
        <div>
          <h4 className="text-sm font-semibold text-slate-100">{insight.title}</h4>
          <p className="mt-1 text-[12px] leading-relaxed text-slate-300">{insight.text}</p>
          <p className="mt-2 border-t border-slate-700/60 pt-2 text-[10px] leading-relaxed text-slate-500">
            <strong className="text-slate-400">Evidenza:</strong> {insight.evidence}
          </p>
        </div>
      </div>
    </article>
  );
}