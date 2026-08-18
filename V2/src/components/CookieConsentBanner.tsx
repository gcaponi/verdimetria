import { useEffect, useState } from "react";
import {
  enableMetaPixel,
  readMarketingConsent,
  writeMarketingConsent,
  type MarketingConsent,
} from "@/lib/metaPixel";

export default function CookieConsentBanner() {
  const [choice, setChoice] = useState<MarketingConsent>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const stored = readMarketingConsent();
    setChoice(stored);
    setReady(true);
    if (stored === "accepted") enableMetaPixel();
  }, []);

  if (!ready || choice !== null) return null;

  return (
    <div
      role="dialog"
      aria-labelledby="cookie-consent-title"
      className="fixed inset-x-0 bottom-0 z-[800] border-t border-slate-700 bg-slate-950/95 p-4 text-slate-200 shadow-2xl backdrop-blur"
    >
      <div className="mx-auto flex max-w-3xl flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="max-w-xl">
          <p id="cookie-consent-title" className="text-sm font-semibold text-slate-100">
            Cookie di misurazione
          </p>
          <p className="mt-1 text-xs leading-relaxed text-slate-400">
            Se accetti, carichiamo il Pixel di Meta per misurare le visite alla demo e le
            inserzioni. Il sito funziona anche se rifiuti. Scelta salvata su questo dispositivo.
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          <button
            type="button"
            className="rounded-md border border-slate-600 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800"
            onClick={() => {
              writeMarketingConsent("rejected");
              setChoice("rejected");
            }}
          >
            Rifiuta
          </button>
          <button
            type="button"
            className="rounded-md bg-lime-400 px-3 py-2 text-sm font-semibold text-slate-950 hover:bg-lime-300"
            onClick={() => {
              writeMarketingConsent("accepted");
              enableMetaPixel();
              setChoice("accepted");
            }}
          >
            Accetta
          </button>
        </div>
      </div>
    </div>
  );
}
