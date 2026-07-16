import type { AppData, FieldData } from "@/types";
import { Card, SectionTitle, InsightCard } from "@/components/ui-bits";
import { fmt } from "@/lib/data";
import { cn } from "@/lib/utils";
import { Mountain, MapPin } from "lucide-react";
import { LayerToggle } from "@/sections/SoilSection";

interface Props {
  data: AppData;
  field: FieldData;
  activeLayerId: string;
  onLayerChange: (id: string) => void;
}

export default function GeologySection({ data, field, activeLayerId, onLayerChange }: Props) {
  const { top_locations, geo } = data.geo;
  return (
    <div className="space-y-4">
      <Card>
        <SectionTitle kicker="Modulo geologico · unsupervised" title="Anomaly detection multivariata" />
        <p className="mb-4 text-[13px] leading-relaxed text-slate-400">
          <strong className="text-slate-200">IsolationForest + PCA</strong> su stack
          litologia-morfologia-indici spettrali. Il punteggio [0–1] ordina i pixel per
          &laquo;stranezza&raquo; multivariata rispetto al pattern dominante del Plateau Ibleo.
          Senza depositi noti su cui addestrarsi, l'approccio non supervisionato è l'unico
          realistico: produce <strong className="text-slate-200">ipotesi di lettura</strong> da
          validare con un geologo, non scoperte.
        </p>
        <div className="mb-4 grid grid-cols-2 gap-3">
          <div className="rounded-lg border border-slate-800 bg-slate-950 p-3">
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-wide text-slate-500">
              <Mountain className="h-3.5 w-3.5" /> Score medio nel campo
            </div>
            <div className={cn("mt-1 text-2xl font-bold", field.anomaly_mean > 0.5 ? "text-orange-300" : "text-slate-100")}>
              {fmt(field.anomaly_mean)}
            </div>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-950 p-3">
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-wide text-slate-500">
              <MapPin className="h-3.5 w-3.5" /> Anomalie prioritarie
            </div>
            <div className="mt-1 text-2xl font-bold text-orange-300">
              {top_locations.filter((l) => l.score > 0.85).length}
              <span className="ml-1 text-sm font-normal text-slate-500">su {top_locations.length} picchi</span>
            </div>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <LayerToggle id="anomaly" label="Mappa anomalie" active={activeLayerId} onChange={onLayerChange} />
          <LayerToggle id="pca" label="Proiezione PCA (RGB)" active={activeLayerId} onChange={onLayerChange} />
        </div>
      </Card>

      <Card>
        <SectionTitle kicker="Per il sopralluogo" title="Top anomalie — coordinate da verificare" />
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[13px]">
            <thead>
              <tr className="border-b border-slate-800 text-[11px] uppercase tracking-wide text-slate-500">
                <th className="py-2 pr-3 font-medium">#</th>
                <th className="py-2 pr-3 font-medium text-right">Score</th>
                <th className="py-2 pr-3 font-medium text-right">Lat</th>
                <th className="py-2 font-medium text-right">Lon</th>
              </tr>
            </thead>
            <tbody>
              {top_locations.map((l, i) => (
                <tr key={i} className="border-b border-slate-800/60">
                  <td className="py-2 pr-3">
                    <span className={cn(
                      "inline-flex h-5 w-5 items-center justify-center rounded text-[10px] font-bold",
                      i < 5 ? "bg-orange-400 text-slate-950" : "bg-slate-700 text-slate-300"
                    )}>
                      {i + 1}
                    </span>
                  </td>
                  <td className="py-2 pr-3 text-right font-semibold text-orange-200">{fmt(l.score, 3)}</td>
                  <td className="py-2 pr-3 text-right text-slate-300">{l.lat}</td>
                  <td className="py-2 text-right text-slate-300">{l.lon}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-[11px] text-slate-500">
          Attiva la mappa anomalie per vedere i marcatori sul territorio. Le 5 anomalie
          principali (arancio pieno) sono i candidati per un primo controllo a campo.
        </p>
      </Card>

      <div className="space-y-3">
        {geo.map((g, i) => (
          <InsightCard key={i} t={g.t} title={g.title} text={g.text} />
        ))}
      </div>
    </div>
  );
}
