import { useCallback, useRef, type ReactNode } from "react";
import { isCoarsePointer, prefersReducedMotion } from "../lib/motion";

// Lightweight 3D tilt on hover, writes the transform directly to the DOM
// node (no React re-render per mousemove). Restrained max angle — see
// immersive-3d-web skill, reference/micro-interactions.md: tilt intensity
// is a brand-register decision, not a fixed constant.
export function Tilt({
  children,
  max = 6,
  className = "",
}: {
  children: ReactNode;
  max?: number;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);

  const onMove = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      const el = ref.current;
      if (!el || prefersReducedMotion() || isCoarsePointer()) return;
      const r = el.getBoundingClientRect();
      const px = (e.clientX - r.left) / r.width - 0.5;
      const py = (e.clientY - r.top) / r.height - 0.5;
      el.style.transition = "transform 60ms ease-out";
      el.style.transform = `perspective(700px) rotateX(${(-py * max).toFixed(2)}deg) rotateY(${(px * max).toFixed(2)}deg)`;
    },
    [max],
  );

  const onLeave = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    el.style.transition = "transform 400ms cubic-bezier(0.22, 1, 0.36, 1)";
    el.style.transform = "";
  }, []);

  return (
    <div ref={ref} className={`tilt-card ${className}`} onMouseMove={onMove} onMouseLeave={onLeave}>
      {children}
    </div>
  );
}
