import { useEffect, useState } from "react";

/**
 * Mobile app-chrome breakpoint in CSS pixels.
 * Must stay in sync with `@media (max-width: 768px)` and `--bp-mobile` in tokens.css.
 */
export const MOBILE_BREAKPOINT_PX = 768;

/**
 * Subscribe to a CSS media query. Updates on match changes (including resize / orientation).
 *
 * Edge cases:
 * - SSR / missing `window.matchMedia`: returns `false` and never updates.
 * - Query changes: tears down the previous listener and re-subscribes.
 */
export default function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return false;
    }
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return;
    }

    const media = window.matchMedia(query);
    function onChange(event: MediaQueryListEvent) {
      setMatches(event.matches);
    }

    setMatches(media.matches);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}

/** True when viewport width is at or below the mobile app-chrome breakpoint. */
export function useIsMobile(): boolean {
  return useMediaQuery(`(max-width: ${MOBILE_BREAKPOINT_PX}px)`);
}
