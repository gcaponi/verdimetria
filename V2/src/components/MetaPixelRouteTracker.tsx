import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router";
import {
  enableMetaPixel,
  isMetaPixelReady,
  readMarketingConsent,
  trackDemoView,
  trackPageView,
} from "@/lib/metaPixel";

export default function MetaPixelRouteTracker() {
  const location = useLocation();
  const firstTracked = useRef(false);
  const [allowed, setAllowed] = useState(() => readMarketingConsent() === "accepted");

  useEffect(() => {
    const sync = () => {
      const accepted = readMarketingConsent() === "accepted";
      setAllowed(accepted);
      if (accepted) enableMetaPixel();
    };
    window.addEventListener("verdimetria-consent", sync);
    return () => window.removeEventListener("verdimetria-consent", sync);
  }, []);

  useEffect(() => {
    if (!allowed) return;
    if (!isMetaPixelReady()) enableMetaPixel();
    if (!firstTracked.current) {
      firstTracked.current = true;
    } else {
      trackPageView();
    }
    if (location.pathname === "/demo") {
      trackDemoView();
    }
  }, [allowed, location.pathname, location.search]);

  return null;
}
