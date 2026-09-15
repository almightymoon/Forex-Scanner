"use client";

import { useEffect, useState } from "react";

/** Sticky header compact state + ambient parallax from page scroll. */
export function useScrollEffects() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let ticking = false;

    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(() => {
        const y = window.scrollY || 0;
        setScrolled(y > 12);
        if (!reduce) {
          const shift = Math.min(y * 0.08, 48);
          document.documentElement.style.setProperty("--scroll-shift", `${shift}px`);
        }
        ticking = false;
      });
    };

    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      document.documentElement.style.removeProperty("--scroll-shift");
    };
  }, []);

  return { scrolled };
}
