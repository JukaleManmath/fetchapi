"use client";

import { useRef, useCallback } from "react";

const MAX_TILT = 8; // degrees

export function useTilt() {
  const ref = useRef<HTMLDivElement | null>(null);

  const onMouseMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const el = ref.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width - 0.5;
    const y = (e.clientY - rect.top) / rect.height - 0.5;
    el.style.transform = `perspective(800px) rotateY(${x * MAX_TILT * 2}deg) rotateX(${-y * MAX_TILT * 2}deg) scale(1.01)`;
  }, []);

  const onMouseLeave = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    el.style.transform = "perspective(800px) rotateY(0deg) rotateX(0deg) scale(1)";
  }, []);

  return { ref, onMouseMove, onMouseLeave };
}
