"use client";

import { useEffect } from "react";

/** Keeps --header-height in sync with the real sticky header so nothing slides underneath. */
export function useHeaderHeight() {
  useEffect(() => {
    const header = document.querySelector<HTMLElement>(".header");
    if (!header) return;

    const sync = () => {
      document.documentElement.style.setProperty(
        "--header-height",
        `${header.getBoundingClientRect().height}px`,
      );
    };

    sync();
    const observer = new ResizeObserver(sync);
    observer.observe(header);
    window.addEventListener("resize", sync);

    return () => {
      observer.disconnect();
      window.removeEventListener("resize", sync);
    };
  }, []);
}
