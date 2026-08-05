import { getApiBaseUrl } from "@/lib/auth";

export interface Plan {
  tier: string;
  label: string;
  amount_eur_month: number;
  max_hectares: number | null;
  price_id: string;
}

export interface Entitlement {
  subscribed: boolean;
  status: string;
  current_period_end: string | null;
  max_fields: number;
  tier: string | null;
  max_hectares: number | null;
  plans: Plan[];
}

export class BillingApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "BillingApiError";
    this.status = status;
  }
}

export async function getEntitlement(
  authorization: string,
  signal?: AbortSignal,
): Promise<Entitlement> {
  return billingRequest<Entitlement>("/api/v1/billing/entitlement/", authorization, {
    signal,
  });
}

export async function startCheckout(
  authorization: string,
  priceId?: string,
): Promise<{ url: string }> {
  return billingRequest<{ url: string }>("/api/v1/billing/checkout/", authorization, {
    method: "POST",
    body: JSON.stringify(priceId ? { price_id: priceId } : {}),
  });
}

export async function openPortal(authorization: string): Promise<{ url: string }> {
  return billingRequest<{ url: string }>("/api/v1/billing/portal/", authorization, {
    method: "POST",
    body: "{}",
  });
}

async function billingRequest<T>(
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
  if (!response.ok) throw await readBillingError(response);
  return (await response.json()) as T;
}

async function readBillingError(response: Response): Promise<BillingApiError> {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (typeof payload === "object" && payload !== null) {
    const record = payload as Record<string, unknown>;
    if (typeof record.detail === "string") {
      return new BillingApiError(record.detail, response.status);
    }
  }
  return new BillingApiError(`Richiesta fallita (${response.status})`, response.status);
}
