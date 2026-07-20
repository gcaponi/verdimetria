import { useCallback, useState, type ReactNode } from "react";
import { AuthContext, type AuthState } from "@/hooks/auth-context";
import {
  authenticate,
  clearSession,
  ensureFreshToken,
  getStoredTokens,
  getStoredUser,
  registerAndAuthenticate,
  type AuthUser,
  type RegisterPayload,
} from "@/lib/auth";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() =>
    getStoredTokens() ? getStoredUser() : null,
  );

  const login = useCallback(async (email: string, password: string) => {
    const { user: sessionUser } = await authenticate(email, password);
    setUser(sessionUser);
  }, []);

  const register = useCallback(async (payload: RegisterPayload) => {
    const { user: sessionUser } = await registerAndAuthenticate(payload);
    setUser(sessionUser);
  }, []);

  const logout = useCallback(() => {
    clearSession();
    setUser(null);
  }, []);

  const getAuthHeader = useCallback(async () => {
    try {
      const access = await ensureFreshToken();
      return `Bearer ${access}`;
    } catch (error) {
      setUser(null);
      throw error;
    }
  }, []);

  const value: AuthState = {
    user,
    isAuthenticated: Boolean(user),
    login,
    register,
    logout,
    getAuthHeader,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}