import { Suspense, useEffect, useRef } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { OrbitalScene } from "./OrbitalScene";
import { prefersReducedMotion } from "../lib/motion";

gsap.registerPlugin(ScrollTrigger);

function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t;
}

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
    camera.position.z = lerp(7, 4, p);
    camera.position.y = lerp(2.2, 0.8, p);
    camera.lookAt(0, 0, 0);
  });

  return null;
}

export function HeroScene({ pinTargetRef }: { pinTargetRef: React.RefObject<HTMLElement | null> }) {
  // Safety net: force a re-measure shortly after mount — see
  // immersive-3d-web skill, patterns-and-antipatterns.md ("Canvas stuck
  // at the browser's default 300x150 intrinsic size").
  useEffect(() => {
    const id = window.setTimeout(() => window.dispatchEvent(new Event("resize")), 60);
    return () => window.clearTimeout(id);
  }, []);

  return (
    <Canvas dpr={[1, 2]} camera={{ position: [0, 2.2, 7], fov: 40 }} gl={{ antialias: true }}>
      <Suspense fallback={null}>
        <OrbitalScene />
        <ScrollDolly pinTargetRef={pinTargetRef} />
      </Suspense>
    </Canvas>
  );
}
