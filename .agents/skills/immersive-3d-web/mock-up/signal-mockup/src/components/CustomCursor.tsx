import { useEffect, useRef } from "react";
import { isCoarsePointer } from "../lib/motion";

const INTERACTIVE = 'a, button, input, textarea, select, [role="button"], [data-cursor-hover]';

// Dot tracks the cursor 1:1, ring trails behind via per-frame lerp (not a
// CSS transition) — see immersive-3d-web skill,
// reference/state-and-feedback.md.
export function CustomCursor() {
  const dotRef = useRef<HTMLDivElement>(null);
  const ringRef = useRef<HTMLDivElement>(null);
  const mouse = useRef({ x: -100, y: -100 });
  const ring = useRef({ x: -100, y: -100 });
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    if (isCoarsePointer()) return;

    document.body.style.cursor = "none";

    const isInteractive = (el: EventTarget | null) =>
      el instanceof Element && el.closest(INTERACTIVE);

    const onMove = (e: MouseEvent) => {
      mouse.current.x = e.clientX;
      mouse.current.y = e.clientY;
    };
    const onOver = (e: MouseEvent) => {
      if (isInteractive(e.target)) document.body.classList.add("cursor-hovering");
    };
    const onOut = (e: MouseEvent) => {
      if (isInteractive(e.target)) document.body.classList.remove("cursor-hovering");
    };

    window.addEventListener("mousemove", onMove);
    document.addEventListener("mouseover", onOver);
    document.addEventListener("mouseout", onOut);

    const loop = () => {
      if (dotRef.current) {
        dotRef.current.style.transform = `translate(${mouse.current.x}px, ${mouse.current.y}px)`;
      }
      ring.current.x += (mouse.current.x - ring.current.x) * 0.18;
      ring.current.y += (mouse.current.y - ring.current.y) * 0.18;
      if (ringRef.current) {
        ringRef.current.style.transform = `translate(${ring.current.x}px, ${ring.current.y}px)`;
      }
      rafRef.current = requestAnimationFrame(loop);
    };
    rafRef.current = requestAnimationFrame(loop);

    return () => {
      document.body.style.cursor = "";
      document.body.classList.remove("cursor-hovering");
      window.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseover", onOver);
      document.removeEventListener("mouseout", onOut);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  if (isCoarsePointer()) return null;

  return (
    <>
      <div ref={ringRef} className="cursor-ring" aria-hidden="true" />
      <div ref={dotRef} className="cursor-dot" aria-hidden="true" />
    </>
  );
}
