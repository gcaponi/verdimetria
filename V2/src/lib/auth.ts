const API_URL =
  import.meta.env.VITE_DJANGO_API_URL ??
  (import.meta.env.PROD ? "https://api.verdimetria.cais.uno" : "http://127.0.0.1:8000");
const TOKENS_KEY = "verdimetria.tokens";
const USER_KEY = "verdimetria.user";

export interface AuthUser {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
}

export interface AuthTokens {
  access: string;
  refresh: string;
}

interface JwtPayload {
  user_id?: string | number;
  exp?: number;
  token_type?: string;
}

export class AuthError extends Error {
  readonly status: number;
  readonly fieldErrors?: Record<string, string[]>;

  constructor(
    message: string,
    status: number,
    fieldErrors?: Record<string, string[]>,
  ) {
    super(message);
    this.name = "AuthError";
    this.status = status;
    this.fieldErrors = fieldErrors;
  }
}

function parseFieldErrors(payload: unknown): Record<string, string[]> | undefined {
  if (typeof payload !== "object" || payload === null) return undefined;
  const out: Record<string, string[]> = {};
  let hasAny = false;
  for (const [key, value] of Object.entries(payload as Record<string, unknown>)) {
    if (Array.isArray(value) && value.every((v) => typeof v === "string")) {
      out[key] = value;
      hasAny = true;
    } else if (typeof value === "string") {
      out[key] = [value];
      hasAny = true;
    }
  }
  return hasAny ? out : undefined;
}

async function readError(response: Response): Promise<AuthError> {
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
  return new AuthError(message, response.status, parseFieldErrors(payload));
}

export function getStoredTokens(): AuthTokens | null {
  try {
    const raw = localStorage.getItem(TOKENS_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<AuthTokens>;
    if (typeof parsed.access !== "string" || typeof parsed.refresh !== "string") {
      return null;
    }
    return { access: parsed.access, refresh: parsed.refresh };
  } catch {
    return null;
  }
}

export function getStoredUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

function persistSession(user: AuthUser, tokens: AuthTokens): void {
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  localStorage.setItem(TOKENS_KEY, JSON.stringify(tokens));
}

export function clearSession(): void {
  localStorage.removeItem(USER_KEY);
  localStorage.removeItem(TOKENS_KEY);
}

function decodeJwt(token: string): JwtPayload | null {
  try {
    const part = token.split(".")[1];
    if (!part) return null;
    const normalized = part.replace(/-/g, "+").replace(/_/g, "/");
    const json = atob(normalized);
    return JSON.parse(json) as JwtPayload;
  } catch {
    return null;
  }
}

export function isAccessExpired(tokens: AuthTokens): boolean {
  const payload = decodeJwt(tokens.access);
  if (!payload?.exp) return true;
  return payload.exp * 1000 <= Date.now() + 30_000;
}

export interface RegisterPayload {
  email: string;
  password: string;
  first_name?: string;
  last_name?: string;
}

export async function register(
  payload: RegisterPayload,
): Promise<{ user: AuthUser; tokens: AuthTokens }> {
  const response = await fetch(`${API_URL}/api/v1/auth/register/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw await readError(response);
  const user = (await response.json()) as AuthUser;
  const tokens = await login(payload.email, payload.password);
  return { user: { ...user, ...mergeNames(user, payload) }, tokens };
}

function mergeNames(user: AuthUser, payload: RegisterPayload): Partial<AuthUser> {
  return {
    first_name: user.first_name || payload.first_name || "",
    last_name: user.last_name || payload.last_name || "",
  };
}

export async function login(
  email: string,
  password: string,
): Promise<AuthTokens> {
  const response = await fetch(`${API_URL}/api/v1/auth/token/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) throw await readError(response);
  const tokens = (await response.json()) as AuthTokens;
  return tokens;
}

export async function refreshAccess(refresh: string): Promise<AuthTokens> {
  const response = await fetch(`${API_URL}/api/v1/auth/token/refresh/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh }),
  });
  if (!response.ok) throw await readError(response);
  const payload = (await response.json()) as { access: string };
  return { access: payload.access, refresh };
}

export async function authenticate(
  email: string,
  password: string,
): Promise<{ user: AuthUser; tokens: AuthTokens }> {
  const tokens = await login(email, password);
  const user = userFromToken(tokens.access, email);
  persistSession(user, tokens);
  return { user, tokens };
}

export async function registerAndAuthenticate(
  payload: RegisterPayload,
): Promise<{ user: AuthUser; tokens: AuthTokens }> {
  const { user, tokens } = await register(payload);
  persistSession(user, tokens);
  return { user, tokens };
}

function userFromToken(access: string, fallbackEmail: string): AuthUser {
  const decoded = decodeJwt(access);
  const id = decoded?.user_id ? Number(decoded.user_id) : 0;
  return { id, email: fallbackEmail, first_name: "", last_name: "" };
}

export async function ensureFreshToken(): Promise<string> {
  const tokens = getStoredTokens();
  if (!tokens) throw new AuthError("Sessione scaduta", 401);
  if (!isAccessExpired(tokens)) return tokens.access;
  try {
    const refreshed = await refreshAccess(tokens.refresh);
    const user = getStoredUser();
    if (user) persistSession(user, refreshed);
    else localStorage.setItem(TOKENS_KEY, JSON.stringify(refreshed));
    return refreshed.access;
  } catch (error) {
    clearSession();
    if (error instanceof AuthError) throw error;
    throw new AuthError("Sessione scaduta", 401);
  }
}

export interface PasswordResetRequest {
  uid: string;
  token: string;
}

export async function requestPasswordReset(
  email: string,
): Promise<{ detail: string; debug?: PasswordResetRequest }> {
  const response = await fetch(`${API_URL}/api/v1/auth/password-reset/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  if (!response.ok) throw await readError(response);
  return (await response.json()) as { detail: string; debug?: PasswordResetRequest };
}

export async function confirmPasswordReset(
  uid: string,
  token: string,
  newPassword: string,
): Promise<void> {
  const response = await fetch(`${API_URL}/api/v1/auth/password-reset/confirm/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ uid, token, new_password: newPassword }),
  });
  if (!response.ok) throw await readError(response);
}

export function getApiBaseUrl(): string {
  return API_URL;
}
