"use client";

import { useEffect, useRef } from "react";

/**
 * Attaches IntersectionObserver to a container and adds `.in-view` to each
 * child that has `.reveal-ready`, triggering the CSS 3D reveal transition.
 * Acts as a fallback for browsers without animation-timeline: view().
 */
export function useScrollReveal() {
  const ref = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const container = ref.current;
    if (!container) return;

    const targets = container.querySelectorAll<HTMLElement>(".reveal-ready");
    if (!targets.length) return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("in-view");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.1, rootMargin: "0px 0px -40px 0px" }
    );

    targets.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, []);

  return ref;
}
