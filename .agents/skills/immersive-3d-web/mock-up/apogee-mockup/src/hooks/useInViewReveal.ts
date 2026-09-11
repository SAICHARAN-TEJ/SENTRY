import { useEffect, useRef, useState } from "react";
import { prefersReducedMotion } from "../lib/motion";

export function useInViewReveal<T extends HTMLElement>(threshold = 0.2) {
  const ref = useRef<T | null>(null);
  const [visible, setVisible] = useState(() => prefersReducedMotion());

  useEffect(() => {
    if (prefersReducedMotion() || !ref.current) {
      setVisible(true);
      return;
    }

    const node = ref.current;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { threshold },
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, [threshold]);

  return { ref, className: `reveal ${visible ? "reveal-visible" : ""}` };
}
