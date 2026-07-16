import type { AppData, FieldData } from "@/types";
import { InsightCard, SectionTitle } from "@/components/ui-bits";

interface Props {
  data: AppData;
  field: FieldData;
}

export default function InsightsSection({ data, field }: Props) {
  return (
    <div className="space-y-5">
      <div>
        <SectionTitle kicker={`${field.name} · ${field.crop}`} title="Interpretazione automatica del campo" />
        <div className="space-y-3">
          {field.insights.map((ins, i) => (
            <InsightCard key={i} t={ins.t} title={ins.title} text={ins.text} />
          ))}
        </div>
      </div>
      <div>
        <SectionTitle kicker="Modulo geologico" title="Lettura del territorio" />
        <div className="space-y-3">
          {data.geo.geo.map((ins, i) => (
            <InsightCard key={i} t={ins.t} title={ins.title} text={ins.text} />
          ))}
        </div>
      </div>
    </div>
  );
}
