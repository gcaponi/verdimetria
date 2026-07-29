import { useEffect, useState } from "react";
import { CalendarDays, LoaderCircle, Plus, Trash2 } from "lucide-react";
import {
  createIntervention,
  deleteIntervention,
  INTERVENTION_KINDS,
  interventionKindLabel,
  listInterventions,
  type Intervention,
  type InterventionKind,
} from "@/lib/interventions";
import { FieldsApiError } from "@/lib/fields";
import { useAuth } from "@/hooks/useAuth";

export default function InterventionsSection({ fieldId }: { fieldId: string }) {
  const { getAuthHeader, logout } = useAuth();
  const [interventions, setInterventions] = useState<Intervention[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [kind, setKind] = useState<InterventionKind>("irrigation");
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [notes, setNotes] = useState("");

  const load = (signal?: AbortSignal) => {
    getAuthHeader()
      .then((authorization) => listInterventions(fieldId, authorization, signal))
      .then(setInterventions)
      .catch((loadError: unknown) => {
        if (loadError instanceof FieldsApiError && loadError.status === 401) logout();
        setError("Diario non disponibile");
      });
  };

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fieldId]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      const authorization = await getAuthHeader();
      await createIntervention(fieldId, authorization, {
        kind,
        date,
        notes: notes.trim() || undefined,
      });
      setNotes("");
      load();
    } catch (saveError) {
      if (saveError instanceof FieldsApiError && saveError.status === 401) logout();
      setError("Salvataggio non riuscito");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (interventionId: string) => {
    try {
      const authorization = await getAuthHeader();
      await deleteIntervention(interventionId, authorization);
      load();
    } catch (deleteError) {
      if (deleteError instanceof FieldsApiError && deleteError.status === 401) logout();
      setError("Eliminazione non riuscita");
    }
  };

  return (
    <div className="space-y-5">
      <header>
        <p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-lime-400">Quaderno del campo</p>
        <h2 className="mt-1 text-lg font-semibold text-slate-100">Diario degli interventi</h2>
        <p className="mt-1 max-w-3xl text-[12px] leading-relaxed text-slate-500">
          Registra irrigazioni, concimazioni, trattamenti e note: il confronto prima/dopo con le
          serie satellitari arriva con il monitoraggio stagionale.
        </p>
      </header>

      <form onSubmit={submit} className="flex flex-wrap items-end gap-2 border border-slate-800 bg-slate-900/40 p-4">
        <label className="flex flex-col gap-1 text-[11px] text-slate-400">
          Tipo
          <select
            value={kind}
            onChange={(event) => setKind(event.target.value as InterventionKind)}
            className="rounded-md border border-slate-700 bg-slate-900 px-2.5 py-2 text-[12px] text-slate-200"
          >
            {INTERVENTION_KINDS.map((entry) => (
              <option key={entry.value} value={entry.value}>{entry.label}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-[11px] text-slate-400">
          Data
          <input
            type="date"
            value={date}
            onChange={(event) => setDate(event.target.value)}
            required
            className="rounded-md border border-slate-700 bg-slate-900 px-2.5 py-2 text-[12px] text-slate-200"
          />
        </label>
        <label className="flex min-w-[220px] flex-1 flex-col gap-1 text-[11px] text-slate-400">
          Nota (opzionale)
          <input
            type="text"
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            maxLength={500}
            placeholder="Es. 2 ore goccia a goccia, dose 40 kg/ha…"
            className="rounded-md border border-slate-700 bg-slate-900 px-2.5 py-2 text-[12px] text-slate-200"
          />
        </label>
        <button
          type="submit"
          disabled={saving}
          className="flex items-center gap-1.5 rounded-md bg-lime-400 px-4 py-2 text-[12px] font-semibold text-slate-950 hover:bg-lime-300 disabled:opacity-50"
        >
          {saving ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
          Aggiungi
        </button>
      </form>

      {error && <p className="text-[12px] text-rose-300">{error}</p>}

      {interventions === null && !error && (
        <p className="text-[12px] text-slate-500">Caricamento del diario…</p>
      )}
      {interventions !== null && interventions.length === 0 && (
        <div className="flex min-h-32 items-center gap-4 border border-dashed border-slate-700 bg-slate-900/30 p-5">
          <CalendarDays className="h-5 w-5 shrink-0 text-slate-500" />
          <p className="text-[12px] leading-relaxed text-slate-500">
            Nessun intervento registrato. Il primo passo del quaderno e' segnare cosa fai oggi:
            tra qualche settimana confronterai gli effetti sulle serie NDVI.
          </p>
        </div>
      )}
      {interventions !== null && interventions.length > 0 && (
        <ul className="divide-y divide-slate-800 border border-slate-800">
          {interventions.map((intervention) => (
            <li key={intervention.id} className="flex items-center gap-3 px-4 py-3">
              <span className="w-24 shrink-0 text-[12px] text-slate-400">
                {new Date(`${intervention.date}T00:00:00`).toLocaleDateString("it-IT", {
                  day: "numeric",
                  month: "short",
                  year: "numeric",
                })}
              </span>
              <span className="shrink-0 rounded-full border border-lime-400/40 bg-lime-400/10 px-2.5 py-0.5 text-[11px] font-medium text-lime-300">
                {interventionKindLabel(intervention.kind)}
              </span>
              <span className="min-w-0 flex-1 truncate text-[12px] text-slate-300">
                {intervention.notes || "—"}
              </span>
              <button
                type="button"
                onClick={() => remove(intervention.id)}
                aria-label="Elimina intervento"
                className="shrink-0 rounded-md p-1.5 text-slate-500 hover:bg-rose-400/10 hover:text-rose-300"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
