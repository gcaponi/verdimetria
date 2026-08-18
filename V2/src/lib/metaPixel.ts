export const PIXEL_ID = "1078239551216372";
export const CONSENT_KEY = "verdimetria.consent.marketing";

export type MarketingConsent = "accepted" | "rejected" | null;

declare global {
  interface Window {
    fbq?: (...args: unknown[]) => void;
    _fbq?: (...args: unknown[]) => void;
  }
}

let pixelReady = false;

export function readMarketingConsent(): MarketingConsent {
  try {
    const value = localStorage.getItem(CONSENT_KEY);
    if (value === "accepted" || value === "rejected") return value;
  } catch {
    /* private mode */
  }
  return null;
}

export function writeMarketingConsent(value: Exclude<MarketingConsent, null>) {
  try {
    localStorage.setItem(CONSENT_KEY, value);
  } catch {
    /* ignore */
  }
  window.dispatchEvent(new CustomEvent("verdimetria-consent", { detail: value }));
}

export function enableMetaPixel() {
  if (pixelReady || typeof window === "undefined") return;

  const fbq = function (...args: unknown[]) {
    const queued = window.fbq as ((...inner: unknown[]) => void) & {
      callMethod?: (...inner: unknown[]) => void;
      queue: unknown[];
      loaded?: boolean;
      version?: string;
      push?: unknown;
    };
    if (queued.callMethod) {
      queued.callMethod(...args);
    } else {
      queued.queue.push(args);
    }
  } as typeof window.fbq & {
    callMethod?: (...args: unknown[]) => void;
    queue: unknown[];
    loaded?: boolean;
    version?: string;
    push?: unknown;
  };

  if (!window.fbq) {
    fbq.queue = [];
    fbq.loaded = true;
    fbq.version = "2.0";
    fbq.push = fbq;
    window.fbq = fbq;
    window._fbq = fbq;
    const script = document.createElement("script");
    script.async = true;
    script.src = "https://connect.facebook.net/en_US/fbevents.js";
    document.head.appendChild(script);
  }

  window.fbq?.("init", PIXEL_ID);
  window.fbq?.("track", "PageView");
  pixelReady = true;
}

export function isMetaPixelReady() {
  return pixelReady;
}

export function trackPageView() {
  if (!pixelReady) return;
  window.fbq?.("track", "PageView");
}

export function trackDemoView() {
  if (!pixelReady) return;
  window.fbq?.("track", "ViewContent", {
    content_name: "verdimetria-demo",
    content_category: "demo",
  });
}
