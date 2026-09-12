import { useEffect, useRef, useState } from "react";
import { prefersReducedMotion } from "../lib/motion";

// Animates from the previously displayed value to `target` with an
// easeOutCubic curve — see immersive-3d-web skill,
// reference/state-and-feedback.md. Skips straight to the target under
// prefers-reduced-motion.
export function useCountUp(target: number, active: boolean, duration = 1100) {
  const [display, setDisplay] = useState(0);
  const rafRef = useRef<number | null>(null);
  const fromRef = useRef(0);
  const startRef = useRef<number | null>(null);

  useEffect(() => {
    if (!active) return;

    if (prefersReducedMotion()) {
      setDisplay(target);
      return;
    }

    fromRef.current = 0;
    startRef.current = null;

    const animate = (ts: number) => {
      if (startRef.current === null) startRef.current = ts;
      const p = Math.min((ts - startRef.current) / duration, 1);
      const eased = 1 - Math.pow(1 - p, 3);
      setDisplay(fromRef.current + (target - fromRef.current) * eased);
      if (p < 1) rafRef.current = requestAnimationFrame(animate);
    };
    rafRef.current = requestAnimationFrame(animate);

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [target, active, duration]);

  return display;
}
