export const PIXEL_ID = "1078239551216372";

declare global {
  interface Window {
    fbq?: (...args: unknown[]) => void;
  }
}

export function trackPageView() {
  window.fbq?.("track", "PageView");
}

export function trackDemoView() {
  window.fbq?.("track", "ViewContent", {
    content_name: "verdimetria-demo",
    content_category: "demo",
  });
}
