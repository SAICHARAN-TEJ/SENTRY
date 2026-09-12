import { useLayoutEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { prefersReducedMotion } from "../lib/motion";

// Kepler-accurate orbit: r(θ) from the polar ellipse equation, angular
// rate dθ/dt = L / r² (conservation of angular momentum) — the body
// genuinely moves faster near periapsis and slower near apoapsis, not a
// hand-tuned ease. See immersive-3d-web skill, reference/concept-to-form.md:
// motion should borrow from how the real referent moves, and an orbit's
// defining trait *is* this non-uniform speed.
function orbitRadius(theta: number, semiMajor: number, eccentricity: number) {
  return (semiMajor * (1 - eccentricity * eccentricity)) / (1 + eccentricity * Math.cos(theta));
}

function OrbitPath({ semiMajor, eccentricity, inclination, color }: { semiMajor: number; eccentricity: number; inclination: number; color: string }) {
  const positions = useMemo(() => {
    const SEGMENTS = 128;
    const pts = new Float32Array((SEGMENTS + 1) * 3);
    for (let i = 0; i <= SEGMENTS; i++) {
      const theta = (i / SEGMENTS) * Math.PI * 2;
      const r = orbitRadius(theta, semiMajor, eccentricity);
      const x = r * Math.cos(theta);
      const zFlat = r * Math.sin(theta);
      pts.set([x, zFlat * Math.sin(inclination), zFlat * Math.cos(inclination)], i * 3);
    }
    return pts;
  }, [semiMajor, eccentricity, inclination]);

  return (
    <lineLoop>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <lineBasicMaterial color={color} transparent opacity={0.16} toneMapped={false} />
    </lineLoop>
  );
}

function OrbitBody({
  semiMajor,
  eccentricity,
  inclination,
  angularMomentum,
  phaseOffset,
  size,
  color,
}: {
  semiMajor: number;
  eccentricity: number;
  inclination: number;
  angularMomentum: number;
  phaseOffset: number;
  size: number;
  color: string;
}) {
  const ref = useRef<THREE.Mesh>(null);
  const theta = useRef(phaseOffset);
  const reduced = useMemo(() => prefersReducedMotion(), []);

  useFrame((_, delta) => {
    if (!ref.current) return;
    const r = orbitRadius(theta.current, semiMajor, eccentricity);
    if (!reduced) {
      theta.current += (angularMomentum / (r * r)) * delta;
    }
    const x = r * Math.cos(theta.current);
    const zFlat = r * Math.sin(theta.current);
    ref.current.position.set(x, zFlat * Math.sin(inclination), zFlat * Math.cos(inclination));
    ref.current.rotation.y += reduced ? 0 : delta * 0.3;
  });

  return (
    <mesh ref={ref}>
      <sphereGeometry args={[size, 20, 20]} />
      <meshStandardMaterial color={color} roughness={0.75} metalness={0.05} />
    </mesh>
  );
}

const STARFIELD_COUNT = 260;
const dummy = new THREE.Object3D();

// Distant stars: deliberately static, not "calm drift." Unlike a live
// monitored system (see concept-to-form.md's network-graph correction),
// the real referent here — background starlight — genuinely doesn't move
// at any timescale a viewer would notice. Motion should match the
// subject either way; sometimes the honest answer really is stillness.
function Starfield() {
  const meshRef = useRef<THREE.InstancedMesh>(null);

  useLayoutEffect(() => {
    if (!meshRef.current) return;
    for (let i = 0; i < STARFIELD_COUNT; i++) {
      const radius = 8 + Math.random() * 10;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(THREE.MathUtils.randFloatSpread(2));
      dummy.position.set(
        radius * Math.sin(phi) * Math.cos(theta),
        radius * Math.sin(phi) * Math.sin(theta),
        radius * Math.cos(phi),
      );
      const s = 0.01 + Math.random() * 0.02;
      dummy.scale.setScalar(s);
      dummy.updateMatrix();
      meshRef.current.setMatrixAt(i, dummy.matrix);
    }
    meshRef.current.instanceMatrix.needsUpdate = true;
  }, []);

  return (
    <instancedMesh ref={meshRef} args={[undefined, undefined, STARFIELD_COUNT]}>
      <sphereGeometry args={[1, 5, 5]} />
      <meshBasicMaterial color="#f5f1e6" transparent opacity={0.7} toneMapped={false} />
    </instancedMesh>
  );
}

const ORBITS = [
  { semiMajor: 1.4, eccentricity: 0.15, inclination: 0.25, angularMomentum: 0.55, phaseOffset: 0.4, size: 0.09, color: "#8fa3d9" },
  { semiMajor: 2.2, eccentricity: 0.35, inclination: -0.35, angularMomentum: 0.7, phaseOffset: 2.6, size: 0.13, color: "#c98f5c" },
  { semiMajor: 3.1, eccentricity: 0.08, inclination: 0.55, angularMomentum: 0.85, phaseOffset: 4.8, size: 0.07, color: "#9fd0c7" },
];

export function OrbitalScene() {
  return (
    <>
      <ambientLight intensity={0.08} />
      <pointLight position={[0, 0, 0]} intensity={12} color="#e8b96a" distance={12} decay={1.4} />

      {/* The star — the light source itself, unlit material so it reads
          as self-illuminated rather than lit-from-outside. */}
      <mesh>
        <sphereGeometry args={[0.42, 24, 24]} />
        <meshBasicMaterial color="#e8b96a" toneMapped={false} />
      </mesh>

      {ORBITS.map((o, i) => (
        <group key={i}>
          <OrbitPath semiMajor={o.semiMajor} eccentricity={o.eccentricity} inclination={o.inclination} color={o.color} />
          <OrbitBody {...o} />
        </group>
      ))}

      <Starfield />
    </>
  );
}
