import { Suspense, useEffect, useRef } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import * as THREE from "three";
import { NetworkGraph } from "./NetworkGraph";
import { prefersReducedMotion } from "../lib/motion";

gsap.registerPlugin(ScrollTrigger);

function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t;
}

// Camera-only dolly on scroll — the graph itself stays still (see
// NetworkGraph.tsx / concept-to-form.md: this scene deliberately has no
// idle spin, motion is reserved for the incident-pulse event).
function ScrollDolly({ pinTargetRef }: { pinTargetRef: React.RefObject<HTMLElement | null> }) {
  const { camera } = useThree();
  const progress = useRef(0);
  const reduced = useRef(prefersReducedMotion());

  useEffect(() => {
    if (reduced.current) return;

    const mm = gsap.matchMedia();

    mm.add({ isDesktop: "(min-width: 768px)" }, (context) => {
      const { isDesktop } = context.conditions as { isDesktop: boolean };
      if (!isDesktop || !pinTargetRef.current) return;

      const trigger = ScrollTrigger.create({
        trigger: pinTargetRef.current,
        start: "top top",
        end: "+=100%",
        scrub: 1,
        pin: true,
        onUpdate: (self) => {
          progress.current = self.progress;
        },
      });

      return () => trigger.kill();
    });

    return () => mm.revert();
  }, [pinTargetRef]);

  useFrame(() => {
    const p = progress.current;
    camera.position.z = lerp(6, 3.6, p);
    camera.position.y = lerp(0.2, -0.05, p);
    camera.lookAt(0, 0, 0);
  });

  return null;
}

export function HeroScene({
  pinTargetRef,
}: {
  pinTargetRef: React.RefObject<HTMLElement | null>;
}) {
  // Safety net: R3F's Canvas sizes itself off its container on mount via
  // ResizeObserver, and on this build that first measurement occasionally
  // landed before the container had settled, leaving the canvas stuck at
  // the browser's default 300x150 intrinsic size. A resize event forces a
  // re-measure; nudging it once, shortly after mount, is enough. See
  // immersive-3d-web skill, patterns-and-antipatterns.md.
  useEffect(() => {
    const id = window.setTimeout(() => window.dispatchEvent(new Event("resize")), 60);
    return () => window.clearTimeout(id);
  }, []);

  return (
    <Canvas dpr={[1, 2]} camera={{ position: [0, 0.2, 6], fov: 35 }} gl={{ antialias: true }}>
      <Suspense fallback={null}>
        <NetworkGraph />
        <ScrollDolly pinTargetRef={pinTargetRef} />
      </Suspense>
    </Canvas>
  );
}
