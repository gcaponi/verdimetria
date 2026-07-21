import { getApiBaseUrl } from "@/lib/auth";
import type { MapArea } from "@/types";

type Position = [number, number];

interface PolygonGeometry {
  type: "Polygon";
  coordinates: Position[][];
}

interface MultiPolygonGeometry {
  type: "MultiPolygon";
  coordinates: Position[][][];
}

type BoundaryGeometry = PolygonGeometry | MultiPolygonGeometry;

interface StoredBoundary {
  id: string;
  version: number;
  geometry: BoundaryGeometry;
  area_hectares: number;
  metric_crs: string;
  source: "draw" | "upload";
  created_at: string;
}

export interface StoredField {
  id: string;
  name: string;
  latest_boundary: StoredBoundary | null;
  created_at: string;
  updated_at: string;
}

export class FieldsApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "FieldsApiError";
    this.status = status;
  }
}

export async function listFields(
  authorization: string,
  signal?: AbortSignal,
): Promise<StoredField[]> {
  return fieldRequest<StoredField[]>("/api/v1/fields/", authorization, { signal });
}

export async function createField(
  authorization: string,
  name: string,
  boundary: Position[],
): Promise<StoredField> {
  const firstPosition = boundary[0];
  const lastPosition = boundary.at(-1);
  const coordinates =
    firstPosition && lastPosition && samePosition(firstPosition, lastPosition)
      ? boundary
      : [...boundary, firstPosition];

  return fieldRequest<StoredField>("/api/v1/fields/", authorization, {
    method: "POST",
    body: JSON.stringify({
      name,
      boundary: { type: "Polygon", coordinates: [coordinates] },
      boundary_source: "draw",
    }),
  });
}

export async function deleteField(
  authorization: string,
  fieldId: string,
): Promise<void> {
  const response = await fetch(`${getApiBaseUrl()}/api/v1/fields/${fieldId}/`, {
    method: "DELETE",
    headers: {
      "Content-Type": "application/json",
      Authorization: authorization,
    },
  });
  if (!response.ok) throw await readFieldsError(response);
}

export function storedFieldToMapArea(field: StoredField): MapArea | null {
  const boundary = field.latest_boundary;
  if (!boundary) return null;
  const ring = exteriorRing(boundary.geometry);
  if (ring.length < 4) return null;
  const lastIndex = ring.length - 1;
  const openRing = samePosition(ring[0], ring[lastIndex]) ? ring.slice(0, lastIndex) : ring;
  return {
    id: field.id,
    name: field.name,
    poly: openRing,
    area_ha: boundary.area_hectares,
  };
}

async function fieldRequest<T>(
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
  if (!response.ok) throw await readFieldsError(response);
  return (await response.json()) as T;
}

async function readFieldsError(response: Response): Promise<FieldsApiError> {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (typeof payload === "object" && payload !== null) {
    const record = payload as Record<string, unknown>;
    if (typeof record.detail === "string") {
      return new FieldsApiError(record.detail, response.status);
    }
    const fieldMessage = Object.values(record)
      .flatMap((value) => (Array.isArray(value) ? value : [value]))
      .find((value): value is string => typeof value === "string");
    if (fieldMessage) return new FieldsApiError(fieldMessage, response.status);
  }
  return new FieldsApiError(`Richiesta fallita (${response.status})`, response.status);
}

function exteriorRing(geometry: BoundaryGeometry): Position[] {
  return geometry.type === "Polygon"
    ? geometry.coordinates[0] ?? []
    : geometry.coordinates[0]?.[0] ?? [];
}

function samePosition(first: Position | undefined, second: Position | undefined): boolean {
  return Boolean(first && second && first[0] === second[0] && first[1] === second[1]);
}