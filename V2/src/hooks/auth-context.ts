import { createContext } from "react";
import type { AuthUser, RegisterPayload } from "@/lib/auth";

export interface AuthState {
  user: AuthUser | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<void>;
  logout: () => void;
  getAuthHeader: () => Promise<string>;
}

export const AuthContext = createContext<AuthState | null>(null);