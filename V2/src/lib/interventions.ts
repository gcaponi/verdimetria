import { getApiBaseUrl } from "@/lib/auth";
import { FieldsApiError } from "@/lib/fields";

export type InterventionKind =
  | "irrigation"
  | "fertilization"
  | "treatment"
  | "sowing"
  | "harvest"
  | "note";

export interface Intervention {
  id: string;
  kind: InterventionKind;
  date: string;
  notes: string;
  created_at: string;
}

export const INTERVENTION_KINDS: Array<{ value: InterventionKind; label: string }> = [
  { value: "irrigation", label: "Irrigazione" },
  { value: "fertilization", label: "Concimazione" },
  { value: "treatment", label: "Trattamento" },
  { value: "sowing", label: "Semina" },
  { value: "harvest", label: "Raccolta" },
  { value: "note", label: "Nota" },
];

export function interventionKindLabel(kind: InterventionKind): string {
  return INTERVENTION_KINDS.find((entry) => entry.value === kind)?.label ?? kind;
}

export async function listInterventions(
  fieldId: string,
  authorization: string,
  signal?: AbortSignal,
): Promise<Intervention[]> {
  return interventionRequest<Intervention[]>(
    `/api/v1/fields/${fieldId}/interventions/`,
    authorization,
    { signal },
  );
}

export async function createIntervention(
  fieldId: string,
  authorization: string,
  payload: { kind: InterventionKind; date: string; notes?: string },
): Promise<Intervention> {
  return interventionRequest<Intervention>(
    `/api/v1/fields/${fieldId}/interventions/`,
    authorization,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export async function deleteIntervention(
  interventionId: string,
  authorization: string,
): Promise<void> {
  const response = await fetch(`${getApiBaseUrl()}/api/v1/interventions/${interventionId}/`, {
    method: "DELETE",
    headers: { Authorization: authorization },
  });
  if (!response.ok) throw await readInterventionError(response);
}

async function interventionRequest<T>(
  path: string,
  authorization: string,
  init: RequestInit,
): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: authorization,
    },
  });
  if (!response.ok) throw await readInterventionError(response);
  return (await response.json()) as T;
}

async function readInterventionError(response: Response): Promise<FieldsApiError> {
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  const message =
    typeof payload === "object" && payload !== null && "detail" in payload
      ? String((payload as { detail: unknown }).detail)
      : `Richiesta fallita (${response.status})`;
  return new FieldsApiError(message, response.status);
}
