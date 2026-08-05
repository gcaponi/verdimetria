import { useEffect, useState } from "react";
import { Link } from "react-router";
import { ArrowLeft, CreditCard, LoaderCircle, Sprout } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/useAuth";
import {
  BillingApiError,
  getEntitlement,
  openPortal,
  startCheckout,
  type Plan,
} from "@/lib/billing";
import type { Entitlement } from "@/lib/billing";

export default function AccountPage() {
  const { isAuthenticated, getAuthHeader, logout } = useAuth();
  const [entitlement, setEntitlement] = useState<Entitlement | null>(null);
  const [loadingTier, setLoadingTier] = useState<string | null>(null);
  const [portalLoading, setPortalLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated) return;
    const controller = new AbortController();
    getAuthHeader()
      .then((authorization) => getEntitlement(authorization, controller.signal))
      .then(setEntitlement)
      .catch((loadError: unknown) => {
        if (controller.signal.aborted) return;
        if (loadError instanceof BillingApiError && loadError.status === 401) logout();
        setError(billingErrorMessage(loadError));
      });
    return () => controller.abort();
  }, [getAuthHeader, isAuthenticated, logout]);

  const shownEntitlement = isAuthenticated ? entitlement : null;

  const handleCheckout = async (priceId?: string, tierKey?: string) => {
    if (shownEntitlement?.subscribed) return;
    setLoadingTier(tierKey ?? "default");
    setError(null);
    try {
      const authorization = await getAuthHeader();
      const { url } = await startCheckout(authorization, priceId);
      window.location.assign(url);
    } catch (actionError) {
      setError(billingErrorMessage(actionError));
      setLoadingTier(null);
    }
  };

  const handlePortal = async () => {
    setPortalLoading(true);
    setError(null);
    try {
      const authorization = await getAuthHeader();
      const { url } = await openPortal(authorization);
      window.location.assign(url);
    } catch (actionError) {
      setError(billingErrorMessage(actionError));
      setPortalLoading(false);
    }
  };

  const subscribed = Boolean(entitlement?.subscribed);
  const isComp = shownEntitlement?.tier === "comp";
  // L'accesso omaggio non ha un customer Stripe: il customer portal fallirebbe.
  const canOpenPortal = subscribed && shownEntitlement?.status !== "comp";
  const currentPlan = shownEntitlement?.plans.find(
    (plan) => plan.tier === shownEntitlement.tier,
  );

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="sticky top-0 z-[600] border-b border-slate-800 bg-slate-950/90 backdrop-blur">
        <div className="flex w-full items-center gap-3 px-3 py-3 sm:px-4 xl:px-5">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-lime-400/15">
              <Sprout className="h-5 w-5 text-lime-400" />
            </div>
            <div>
              <div className="text-[15px] font-bold leading-tight">Verdimetria</div>
              <div className="text-[11px] leading-tight text-slate-500">Abbonamento</div>
            </div>
          </div>
          <div className="ml-auto">
            <Link
              to="/"
              className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-2 text-[12px] font-medium text-slate-300 transition-colors hover:border-slate-500 hover:text-white"
            >
              <ArrowLeft className="h-3.5 w-3.5" /> Torna alla mappa
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-3xl px-3 py-10 sm:px-4">
        {!isAuthenticated ? (
          <section className="mx-auto max-w-xl rounded-xl border border-slate-800 bg-slate-900/60 p-6 text-center">
            <CreditCard className="mx-auto h-8 w-8 text-lime-400" />
            <h1 className="mt-3 text-lg font-semibold">Accedi per gestire l'abbonamento</h1>
            <p className="mt-2 text-sm text-slate-400">
              Registrati o accedi dalla mappa per creare campi e lanciare analisi.
            </p>
            <Button
              asChild
              className="mt-5 bg-lime-400 text-slate-950 hover:bg-lime-300"
            >
              <Link to="/">Vai alla mappa</Link>
            </Button>
          </section>
        ) : (
          <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-6">
            <h1 className="text-lg font-semibold">Il tuo abbonamento</h1>

            {shownEntitlement === null && !error && (
              <p className="mt-4 flex items-center gap-2 text-sm text-slate-400">
                <LoaderCircle className="h-4 w-4 animate-spin" /> Caricamento stato…
              </p>
            )}

            {error && (
              <p role="alert" className="mt-4 border-l-2 border-rose-400 pl-3 text-sm text-rose-300">
                {error}
              </p>
            )}

            {shownEntitlement !== null && (
              <>
                <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-semibold">
                        {subscribed
                          ? isComp
                            ? "Abbonamento attivo — accesso omaggio"
                            : `Abbonamento attivo${currentPlan ? ` — piano ${currentPlan.label}` : ""}`
                          : "Abbonamento non attivo"}
                      </div>
                      <div className="mt-1 text-[12px] text-slate-400">
                        {subscribed
                          ? "Campi e analisi disponibili nei limiti del tuo piano."
                          : "La creazione di campi e l'avvio di analisi richiedono un piano attivo."}
                      </div>
                    </div>
                    <span
                      className={`shrink-0 rounded-full px-3 py-1 text-[11px] font-semibold ${
                        subscribed
                          ? "bg-emerald-400/15 text-emerald-400"
                          : "bg-amber-400/15 text-amber-300"
                      }`}
                    >
                      {subscribed ? "ATTIVO" : "DISATTIVO"}
                    </span>
                  </div>
                  <dl className="mt-4 grid grid-cols-2 gap-3 text-[12px] sm:grid-cols-4">
                    <div>
                      <dt className="text-slate-500">Stato Stripe</dt>
                      <dd className="mt-0.5 font-medium text-slate-200">
                        {shownEntitlement.status || "—"}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-slate-500">Scadenza periodo</dt>
                      <dd className="mt-0.5 font-medium text-slate-200">
                        {shownEntitlement.current_period_end
                          ? new Date(shownEntitlement.current_period_end).toLocaleDateString("it-IT")
                          : "—"}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-slate-500">Campi per account</dt>
                      <dd className="mt-0.5 font-medium text-slate-200">{shownEntitlement.max_fields}</dd>
                    </div>
                    <div>
                      <dt className="text-slate-500">Limite ettari</dt>
                      <dd className="mt-0.5 font-medium text-slate-200">
                        {shownEntitlement.max_hectares === null
                          ? "Illimitati"
                          : `${shownEntitlement.max_hectares} ha (cumulativi)`}
                      </dd>
                    </div>
                  </dl>
                </div>

                {subscribed ? (
                  canOpenPortal ? (
                    <div className="mt-5 flex flex-wrap items-center gap-3">
                      <Button
                        onClick={handlePortal}
                        disabled={portalLoading}
                        className="bg-lime-400 text-slate-950 hover:bg-lime-300"
                      >
                        {portalLoading ? <LoaderCircle className="animate-spin" /> : <CreditCard />}
                        {portalLoading ? "Apertura…" : "Gestisci abbonamento"}
                      </Button>
                    </div>
                  ) : null
                ) : shownEntitlement.plans.length > 0 ? (
                  <div className="mt-5 grid gap-3 sm:grid-cols-3">
                    {shownEntitlement.plans.map((plan) => (
                      <PlanCard
                        key={plan.tier}
                        plan={plan}
                        loading={loadingTier === plan.tier}
                        disabled={loadingTier !== null}
                        onChoose={() => void handleCheckout(plan.price_id, plan.tier)}
                      />
                    ))}
                  </div>
                ) : (
                  <div className="mt-5 flex flex-wrap items-center gap-3">
                    <Button
                      onClick={() => void handleCheckout()}
                      disabled={loadingTier !== null}
                      className="bg-lime-400 text-slate-950 hover:bg-lime-300"
                    >
                      {loadingTier !== null ? <LoaderCircle className="animate-spin" /> : <CreditCard />}
                      {loadingTier !== null ? "Reindirizzamento…" : "Abbonati ora"}
                    </Button>
                  </div>
                )}
              </>
            )}
          </section>
        )}
      </main>
    </div>
  );
}

function PlanCard({
  plan,
  loading,
  disabled,
  onChoose,
}: {
  plan: Plan;
  loading: boolean;
  disabled: boolean;
  onChoose: () => void;
}) {
  return (
    <div className="flex flex-col rounded-lg border border-slate-800 bg-slate-950 p-4">
      <div className="text-sm font-semibold">{plan.label}</div>
      <div className="mt-1 text-xl font-bold text-lime-400">
        {plan.amount_eur_month.toLocaleString("it-IT", {
          style: "currency",
          currency: "EUR",
        })}
        <span className="text-[11px] font-normal text-slate-400">/mese</span>
      </div>
      <div className="mt-1 text-[12px] text-slate-400">
        {plan.max_hectares === null
          ? "Ettari illimitati"
          : `Fino a ${plan.max_hectares} ha complessivi`}
      </div>
      <Button
        onClick={onChoose}
        disabled={disabled}
        className="mt-4 bg-lime-400 text-slate-950 hover:bg-lime-300"
      >
        {loading ? <LoaderCircle className="animate-spin" /> : null}
        {loading ? "Reindirizzamento…" : "Scegli"}
      </Button>
    </div>
  );
}

function billingErrorMessage(error: unknown): string {
  if (error instanceof BillingApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Connessione al backend non riuscita";
}
