import { useState, type FormEvent } from "react";
import {
  ArrowLeft,
  CheckCircle2,
  LoaderCircle,
  LogIn,
  LogOut,
  Mail,
  UserRound,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/hooks/useAuth";
import { AuthError, confirmPasswordReset, requestPasswordReset } from "@/lib/auth";

type AuthMode = "login" | "register" | "reset-request" | "reset-confirm";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAuthenticated: () => void;
}

export default function AuthControl({ open, onOpenChange, onAuthenticated }: Props) {
  const { user, isAuthenticated, login, register, logout } = useAuth();
  const [mode, setMode] = useState<AuthMode>("login");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resetEmail, setResetEmail] = useState("");
  const [resetDebug, setResetDebug] = useState<{ uid: string; token: string } | null>(null);
  const [resetSuccess, setResetSuccess] = useState(false);

  if (isAuthenticated && user) {
    return (
      <div className="flex min-w-0 items-center gap-2">
        <div className="hidden min-w-0 text-right sm:block">
          <div className="truncate text-[11px] font-medium text-slate-200">{user.email}</div>
          <div className="text-[10px] text-lime-400">Sessione attiva</div>
        </div>
        <Button
          type="button"
          variant="outline"
          size="icon"
          onClick={logout}
          title="Esci"
          aria-label="Esci"
          className="border-slate-700 bg-slate-950 text-slate-300 hover:bg-slate-800 hover:text-white"
        >
          <LogOut />
        </Button>
      </div>
    );
  }

  const resetAuthState = () => {
    setMode("login");
    setError(null);
    setResetEmail("");
    setResetDebug(null);
    setResetSuccess(false);
    setPending(false);
  };

  const handleOpenChange = (nextOpen: boolean) => {
    onOpenChange(nextOpen);
    if (!nextOpen) resetAuthState();
  };

  const selectMode = (nextMode: AuthMode) => {
    setMode(nextMode);
    setError(null);
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setPending(true);
    setError(null);
    const form = new FormData(event.currentTarget);

    try {
      if (mode === "login") {
        const email = String(form.get("email") ?? "").trim();
        const password = String(form.get("password") ?? "");
        await login(email, password);
        onAuthenticated();
        onOpenChange(false);
      } else if (mode === "register") {
        const email = String(form.get("email") ?? "").trim();
        const password = String(form.get("password") ?? "");
        await register({
          email,
          password,
          first_name: String(form.get("first_name") ?? "").trim(),
          last_name: String(form.get("last_name") ?? "").trim(),
        });
        onAuthenticated();
        onOpenChange(false);
      } else if (mode === "reset-request") {
        const email = String(form.get("email") ?? "").trim();
        setResetEmail(email);
        const result = await requestPasswordReset(email);
        if (result.debug) setResetDebug(result.debug);
        selectMode("reset-confirm");
      } else if (mode === "reset-confirm") {
        const newPassword = String(form.get("password") ?? "");
        const uid = resetDebug?.uid ?? String(form.get("uid") ?? "").trim();
        const token = resetDebug?.token ?? String(form.get("token") ?? "").trim();
        if (!uid || !token) {
          setError("Dati di recupero mancanti. Richiedi un nuovo link.");
          return;
        }
        await confirmPasswordReset(uid, token, newPassword);
        setResetSuccess(true);
      }
    } catch (submitError) {
      setError(authErrorMessage(submitError));
    } finally {
      setPending(false);
    }
  };

  return (
    <>
      <Button
        type="button"
        variant="outline"
        onClick={() => onOpenChange(true)}
        className="border-slate-700 bg-slate-950 text-slate-200 hover:bg-slate-800 hover:text-white"
      >
        <LogIn /> Accedi
      </Button>
      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent className="border-slate-700 bg-slate-950 text-slate-100 sm:max-w-md">
          {mode === "reset-confirm" || mode === "reset-request" ? (
            <>
              {resetSuccess ? (
                <>
                  <DialogHeader>
                    <div className="mb-1 flex h-10 w-10 items-center justify-center rounded-md bg-emerald-400/15 text-emerald-400">
                      <CheckCircle2 className="h-5 w-5" />
                    </div>
                    <DialogTitle>Password aggiornata</DialogTitle>
                    <DialogDescription className="text-slate-400">
                      Ora puoi accedere con la nuova password.
                    </DialogDescription>
                  </DialogHeader>
                  <Button
                    type="button"
                    onClick={() => {
                      resetAuthState();
                      onOpenChange(false);
                    }}
                    className="w-full bg-lime-400 text-slate-950 hover:bg-lime-300"
                  >
                    <LogIn /> Accedi ora
                  </Button>
                </>
              ) : (
                <>
                  <DialogHeader>
                    <div className="mb-1 flex h-10 w-10 items-center justify-center rounded-md bg-lime-400/15 text-lime-400">
                      <Mail className="h-5 w-5" />
                    </div>
                    <DialogTitle>Recupera password</DialogTitle>
                    <DialogDescription className="text-slate-400">
                      {mode === "reset-request"
                        ? "Inserisci l'email del tuo account."
                        : `Controlla la posta di ${resetEmail}. ${resetDebug ? "Sviluppo locale: usa i dati qui sotto." : "Segui il link che hai ricevuto."}`}
                    </DialogDescription>
                  </DialogHeader>

                  {mode === "reset-request" ? (
                    <form className="space-y-4" onSubmit={handleSubmit}>
                      <AuthField
                        label="Email"
                        name="email"
                        type="email"
                        autoComplete="email"
                        required
                      />
                      {error && (
                        <p role="alert" className="border-l-2 border-rose-400 pl-3 text-sm text-rose-300">
                          {error}
                        </p>
                      )}
                      <div className="flex items-center gap-3">
                        <Button
                          type="submit"
                          disabled={pending}
                          className="flex-1 bg-lime-400 text-slate-950 hover:bg-lime-300"
                        >
                          {pending ? <LoaderCircle className="animate-spin" /> : <Mail />}
                          {pending ? "Invio…" : "Invia richiesta"}
                        </Button>
                      </div>
                    </form>
                  ) : (
                    <form className="space-y-4" onSubmit={handleSubmit}>
                      {resetDebug && (
                        <div className="space-y-2 rounded-md border border-amber-400/30 bg-amber-400/5 p-3 text-[11px]">
                          <p className="mb-1 font-medium text-amber-300">Debug locale</p>
                          <AuthField
                            label="UID"
                            name="uid"
                            autoComplete="off"
                            defaultValue={resetDebug.uid}
                          />
                          <AuthField
                            label="Token"
                            name="token"
                            autoComplete="off"
                            defaultValue={resetDebug.token}
                          />
                        </div>
                      )}
                      <AuthField
                        label="Nuova password"
                        name="password"
                        type="password"
                        autoComplete="new-password"
                        required
                      />
                      {error && (
                        <p role="alert" className="border-l-2 border-rose-400 pl-3 text-sm text-rose-300">
                          {error}
                        </p>
                      )}
                      <Button
                        type="submit"
                        disabled={pending}
                        className="w-full bg-lime-400 text-slate-950 hover:bg-lime-300"
                      >
                        {pending ? <LoaderCircle className="animate-spin" /> : <CheckCircle2 />}
                        {pending ? "Salvataggio…" : "Imposta nuova password"}
                      </Button>
                    </form>
                  )}

                  <button
                    type="button"
                    onClick={() => selectMode(mode === "reset-request" ? "login" : "reset-request")}
                    className="flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-200"
                  >
                    <ArrowLeft className="h-4 w-4" />
                    {mode === "reset-request" ? "Torna al login" : "Correggi email"}
                  </button>
                </>
              )}
            </>
          ) : (
            <>
              <DialogHeader>
                <div className="mb-1 flex h-10 w-10 items-center justify-center rounded-md bg-lime-400/15 text-lime-400">
                  <UserRound className="h-5 w-5" />
                </div>
                <DialogTitle>{mode === "login" ? "Accedi" : "Crea account"}</DialogTitle>
                <DialogDescription className="text-slate-400">
                  {mode === "login"
                    ? "Entra nel tuo account Verdimetria."
                    : "Crea il profilo che conservera i tuoi campi."}
                </DialogDescription>
              </DialogHeader>

              <div className="grid grid-cols-2 rounded-md border border-slate-800 bg-slate-900 p-1">
                <button
                  type="button"
                  aria-pressed={mode === "login"}
                  onClick={() => selectMode("login")}
                  className={`h-8 rounded text-sm font-medium transition-colors ${
                    mode === "login" ? "bg-slate-700 text-white" : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  Accedi
                </button>
                <button
                  type="button"
                  aria-pressed={mode === "register"}
                  onClick={() => selectMode("register")}
                  className={`h-8 rounded text-sm font-medium transition-colors ${
                    mode === "register" ? "bg-slate-700 text-white" : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  Registrati
                </button>
              </div>

              <form className="space-y-4" onSubmit={handleSubmit}>
                {mode === "register" && (
                  <div className="grid gap-3 sm:grid-cols-2">
                    <AuthField label="Nome" name="first_name" autoComplete="given-name" />
                    <AuthField label="Cognome" name="last_name" autoComplete="family-name" />
                  </div>
                )}
                <AuthField
                  label="Email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  required
                />
                <AuthField
                  label="Password"
                  name="password"
                  type="password"
                  autoComplete={mode === "login" ? "current-password" : "new-password"}
                  required
                />
                {mode === "login" && (
                  <button
                    type="button"
                    onClick={() => selectMode("reset-request")}
                    className="block w-full text-left text-[12px] text-slate-500 underline underline-offset-2 hover:text-slate-300"
                  >
                    Password dimenticata?
                  </button>
                )}
                {error && (
                  <p role="alert" className="border-l-2 border-rose-400 pl-3 text-sm text-rose-300">
                    {error}
                  </p>
                )}
                <Button
                  type="submit"
                  disabled={pending}
                  className="w-full bg-lime-400 text-slate-950 hover:bg-lime-300"
                >
                  {pending ? <LoaderCircle className="animate-spin" /> : mode === "login" ? <LogIn /> : <UserRound />}
                  {pending ? "Attendi" : mode === "login" ? "Accedi" : "Crea account"}
                </Button>
              </form>
            </>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}

interface AuthFieldProps {
  label: string;
  name: string;
  type?: string;
  autoComplete: string;
  required?: boolean;
  defaultValue?: string;
}

function AuthField({ label, name, type = "text", autoComplete, required, defaultValue }: AuthFieldProps) {
  return (
    <div className="space-y-2">
      <Label htmlFor={`auth-${name}`} className="text-slate-300">
        {label}
      </Label>
      <Input
        id={`auth-${name}`}
        name={name}
        type={type}
        autoComplete={autoComplete}
        required={required}
        defaultValue={defaultValue}
        className="border-slate-700 bg-slate-900 text-slate-100 placeholder:text-slate-600"
      />
    </div>
  );
}

function authErrorMessage(error: unknown): string {
  if (!(error instanceof AuthError)) return "Connessione al backend non riuscita";
  const fieldMessage = error.fieldErrors
    ? Object.values(error.fieldErrors).flat().find(Boolean)
    : undefined;
  return fieldMessage ?? error.message;
}