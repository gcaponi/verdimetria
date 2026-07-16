import type { AppData, FieldData } from "@/types";
import { Card, SectionTitle, RatingChip } from "@/components/ui-bits";
import { fmt } from "@/lib/data";
import { cn } from "@/lib/utils";

interface Props {
  data: AppData;
  field: FieldData;
  activeLayerId: string;
  onLayerChange: (id: string) => void;
}

const ROWS = [
  { key: "n", label: "Azoto totale (N)", unit: "mg/kg", layer: "n", digits: 0 },
  { key: "p", label: "Fosforo accessibile (P)", unit: "mg/kg", layer: "p", digits: 1 },
  { key: "k", label: "Potassio scambiabile (K)", unit: "mg/kg", layer: "k", digits: 0 },
  { key: "ph", label: "pH", unit: "", layer: "ph", digits: 2 },
  { key: "som", label: "Sostanza organica (SOM)", unit: "%", layer: "som", digits: 2 },
] as const;

export default function SoilSection({ data, field, activeLayerId, onLayerChange }: Props) {
  const avg = data.geo.aoi_avg;
  return (
    <div className="space-y-4">
      <Card>
        <SectionTitle
          kicker="Analisi del suolo · griglia ~30 m"
          title={`Medie zonali — ${field.name}`}
        />
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[13px]">
            <thead>
              <tr className="border-b border-slate-800 text-[11px] uppercase tracking-wide text-slate-500">
                <th className="py-2 pr-3 font-medium">Parametro</th>
                <th className="py-2 pr-3 font-medium text-right">Valore</th>
                <th className="py-2 pr-3 font-medium text-right">Media AOI</th>
                <th className="py-2 pr-3 font-medium text-center">Valutazione</th>
                <th className="py-2 font-medium text-right">Mappa</th>
              </tr>
            </thead>
            <tbody>
              {ROWS.map((r) => {
                const v = field[r.key as "n"];
                const a = avg[r.key];
                const diff = ((v - a) / a) * 100;
                return (
                  <tr key={r.key} className="border-b border-slate-800/60">
                    <td className="py-2.5 pr-3 font-medium text-slate-200">{r.label}</td>
                    <td className="py-2.5 pr-3 text-right text-slate-100">
                      <span className="font-semibold">{fmt(v, r.digits)}</span>
                      {r.unit && <span className="ml-1 text-[11px] text-slate-500">{r.unit}</span>}
                    </td>
                    <td className="py-2.5 pr-3 text-right text-slate-400">
                      {fmt(a, r.digits)}
                      <span className={cn("ml-1.5 text-[10px]", diff >= 0 ? "text-emerald-400" : "text-rose-400")}>
                        {diff >= 0 ? "+" : ""}{fmt(diff, 0)}%
                      </span>
                    </td>
                    <td className="py-2.5 pr-3 text-center">
                      <RatingChip value={field.ratings[r.key as "n"]} />
                    </td>
                    <td className="py-2.5 text-right">
                      <button
                        onClick={() => onLayerChange(activeLayerId === r.layer ? "none" : r.layer)}
                        className={cn(
                          "rounded-md border px-2 py-1 text-[11px] font-medium transition-colors",
                          activeLayerId === r.layer
                            ? "border-lime-400/50 bg-lime-400/10 text-lime-300"
                            : "border-slate-700 text-slate-400 hover:border-slate-500 hover:text-slate-200"
                        )}
                      >
                        {activeLayerId === r.layer ? "Attivo" : "Mostra"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      <Card>
        <SectionTitle kicker="Tessitura" title="Composizione granulometrica stimata" />
        <div className="mb-2 flex h-4 w-full overflow-hidden rounded-full">
          <div className="bg-amber-700" style={{ width: `${field.sand}%` }} title={`Sabbia ${field.sand}%`} />
          <div className="bg-orange-300" style={{ width: `${field.silt}%` }} title={`Limo ${field.silt}%`} />
          <div className="bg-rose-400" style={{ width: `${field.clay}%` }} title={`Argilla ${field.clay}%`} />
        </div>
        <div className="flex flex-wrap gap-4 text-[12px] text-slate-300">
          <LegendDot cls="bg-amber-700" label={`Sabbia ${fmt(field.sand, 1)}%`} />
          <LegendDot cls="bg-orange-300" label={`Limo ${fmt(field.silt, 1)}%`} />
          <LegendDot cls="bg-rose-400" label={`Argilla ${fmt(field.clay, 1)}%`} />
        </div>
        <p className="mt-3 text-[12px] leading-relaxed text-slate-500">
          {field.clay > 38
            ? "Tessitura argillosa: buona riserva idrica ma rischio di ristagno e lavorazioni difficili. Tipica delle valli interne iblee."
            : field.sand > 40
            ? "Tessitura sciolta: drenaggio elevato, attenzione alla scarsa ritenzione idrica e ai nutrienti lisciviabili."
            : "Tessitura franca bilanciata: condizione ottimale per la maggior parte delle colture mediterranee."}
        </p>
      </Card>

      <Card>
        <SectionTitle kicker="Debolezza cronica" title="Layer diagnostico del modulo agro" />
        <p className="mb-3 text-[13px] leading-relaxed text-slate-400">
          Il punteggio di debolezza è la <strong className="text-slate-200">media degli z-score NDVI</strong> su
          tutta la serie storica: segnala le zone cronicamente sotto la media, non gli stress
          passeggeri. È il cuore del modulo agricolo del progetto.
        </p>
        <div className="flex flex-wrap gap-2">
          <LayerToggle id="weakness" label="Debolezza cronica" active={activeLayerId} onChange={onLayerChange} />
          <LayerToggle id="ndvi" label="NDVI corrente" active={activeLayerId} onChange={onLayerChange} />
        </div>
      </Card>
    </div>
  );
}

function LegendDot({ cls, label }: { cls: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className={cn("h-2.5 w-2.5 rounded-sm", cls)} />
      {label}
    </span>
  );
}

export function LayerToggle({
  id,
  label,
  active,
  onChange,
}: {
  id: string;
  label: string;
  active: string;
  onChange: (id: string) => void;
}) {
  const is = active === id;
  return (
    <button
      onClick={() => onChange(is ? "none" : id)}
      className={cn(
        "rounded-lg border px-3 py-1.5 text-[12px] font-medium transition-colors",
        is
          ? "border-lime-400/60 bg-lime-400/10 text-lime-300"
          : "border-slate-700 text-slate-400 hover:border-slate-500 hover:text-slate-200"
      )}
    >
      {label}
    </button>
  );
}
