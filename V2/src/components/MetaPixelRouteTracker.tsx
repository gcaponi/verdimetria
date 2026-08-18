import { useEffect, useRef } from "react";
import { useLocation } from "react-router";
import { trackDemoView, trackPageView } from "@/lib/metaPixel";

/** First PageView is fired from index.html; this covers SPA navigations. */
export default function MetaPixelRouteTracker() {
  const location = useLocation();
  const firstLoad = useRef(true);

  useEffect(() => {
    if (firstLoad.current) {
      firstLoad.current = false;
    } else {
      trackPageView();
    }
    if (location.pathname === "/demo") {
      trackDemoView();
    }
  }, [location.pathname, location.search]);

  return null;
}
