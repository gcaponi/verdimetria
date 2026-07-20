import { useContext } from "react";
import { AuthContext, type AuthState } from "@/hooks/auth-context";

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth deve essere usato dentro <AuthProvider>");
  return context;
}