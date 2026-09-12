import { forwardRef, useLayoutEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { prefersReducedMotion } from "../lib/motion";

const dummy = new THREE.Object3D();
const NODE_COUNT = 46;
const NEIGHBORS_PER_NODE = 2;

type NodeData = {
  base: [number, number, number];
  phase: number;
  speed: number;
  amp: number;
};

function buildNodes(): NodeData[] {
  const nodes: NodeData[] = [];
  for (let i = 0; i < NODE_COUNT; i++) {
    const radius = 1.2 + Math.random() * 2.6;
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(THREE.MathUtils.randFloatSpread(2));
    nodes.push({
      base: [
        radius * Math.sin(phi) * Math.cos(theta),
        radius * Math.sin(phi) * Math.sin(theta) * 0.6,
        radius * Math.cos(phi),
      ],
      phase: Math.random() * Math.PI * 2,
      speed: 0.25 + Math.random() * 0.35,
      amp: 0.05 + Math.random() * 0.06,
    });
  }
  return nodes;
}

function buildEdgePairs(nodes: NodeData[]): [number, number][] {
  const pairs = new Set<string>();
  const result: [number, number][] = [];

  nodes.forEach((a, i) => {
    const distances = nodes
      .map((b, j) => ({
        j,
        d: i === j ? Infinity : Math.hypot(a.base[0] - b.base[0], a.base[1] - b.base[1], a.base[2] - b.base[2]),
      }))
      .sort((x, y) => x.d - y.d)
      .slice(0, NEIGHBORS_PER_NODE);

    for (const { j } of distances) {
      const key = i < j ? `${i}-${j}` : `${j}-${i}`;
      if (pairs.has(key)) continue;
      pairs.add(key);
      result.push([i, j]);
    }
  });

  return result;
}

// The hero object: a network graph, not a decorative polyhedron — nodes
// are "monitored endpoints," edges are topology. No bulk rotation of the
// whole shape (that read as generic decoration, see
// concept-to-form.md) — instead each node drifts on its own small,
// independent phase, like a live system breathing, and a single node
// flashes on an interval to represent an incident being caught. "Calm at
// rest" means no attention-grabbing spin, not literally frozen — a
// completely static network reads as broken, not calm.
function IncidentPulse({ nodes }: { nodes: NodeData[] }) {
  const ref = useRef<THREE.Mesh>(null);
  const matRef = useRef<THREE.MeshBasicMaterial>(null);
  const reduced = useMemo(() => prefersReducedMotion(), []);
  const phaseStart = useRef<number | null>(null);
  const nextAt = useRef(2 + Math.random() * 2);
  const clock = useRef(0);
  const PULSE_DURATION = 1.1;

  useFrame((_, delta) => {
    if (reduced || !ref.current || !matRef.current) return;
    clock.current += delta;

    if (phaseStart.current === null) {
      ref.current.visible = false;
      if (clock.current >= nextAt.current) {
        const node = nodes[Math.floor(Math.random() * nodes.length)];
        ref.current.position.set(...node.base);
        phaseStart.current = clock.current;
      }
      return;
    }

    const t = (clock.current - phaseStart.current) / PULSE_DURATION;
    if (t >= 1) {
      phaseStart.current = null;
      clock.current = 0;
      nextAt.current = 3 + Math.random() * 3;
      return;
    }

    ref.current.visible = true;
    ref.current.scale.setScalar(0.012 + t * 0.05);
    matRef.current.opacity = 1 - t;
  });

  return (
    <mesh ref={ref} visible={false}>
      <sphereGeometry args={[1, 12, 12]} />
      <meshBasicMaterial ref={matRef} color="#ff5566" transparent opacity={0} toneMapped={false} />
    </mesh>
  );
}

export const NetworkGraph = forwardRef<THREE.Group>((_props, ref) => {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const lineGeoRef = useRef<THREE.BufferGeometry>(null);
  const lineMatRef = useRef<THREE.LineBasicMaterial>(null);
  const reduced = useMemo(() => prefersReducedMotion(), []);

  const nodes = useMemo(() => buildNodes(), []);
  const edgePairs = useMemo(() => buildEdgePairs(nodes), [nodes]);
  const edgePositions = useMemo(() => new Float32Array(edgePairs.length * 6), [edgePairs]);
  const livePositions = useRef(nodes.map((n) => [...n.base] as [number, number, number]));

  const writeStaticLayout = () => {
    if (!meshRef.current) return;
    nodes.forEach((n, i) => {
      dummy.position.set(...n.base);
      dummy.scale.setScalar(0.014);
      dummy.updateMatrix();
      meshRef.current!.setMatrixAt(i, dummy.matrix);
      livePositions.current[i] = n.base;
    });
    meshRef.current.instanceMatrix.needsUpdate = true;

    edgePairs.forEach(([a, b], idx) => {
      edgePositions.set([...nodes[a].base, ...nodes[b].base], idx * 6);
    });
    if (lineGeoRef.current) {
      lineGeoRef.current.attributes.position.needsUpdate = true;
    }
  };

  useLayoutEffect(writeStaticLayout, [nodes, edgePairs]);

  useFrame((state) => {
    if (reduced || !meshRef.current) return;
    const t = state.clock.elapsedTime;

    nodes.forEach((n, i) => {
      const x = n.base[0] + Math.sin(t * n.speed + n.phase) * n.amp;
      const y = n.base[1] + Math.cos(t * n.speed * 0.8 + n.phase * 1.3) * n.amp;
      const z = n.base[2] + Math.sin(t * n.speed * 0.6 + n.phase * 0.7) * n.amp;
      dummy.position.set(x, y, z);
      dummy.scale.setScalar(0.014);
      dummy.updateMatrix();
      meshRef.current!.setMatrixAt(i, dummy.matrix);
      livePositions.current[i] = [x, y, z];
    });
    meshRef.current.instanceMatrix.needsUpdate = true;

    edgePairs.forEach(([a, b], idx) => {
      edgePositions.set([...livePositions.current[a], ...livePositions.current[b]], idx * 6);
    });
    if (lineGeoRef.current) {
      lineGeoRef.current.attributes.position.needsUpdate = true;
    }

    // Data-flow shimmer: a slow opacity breathe on the connections, not
    // a spin — signals "live" without an attention-grabbing motion.
    if (lineMatRef.current) {
      lineMatRef.current.opacity = 0.14 + Math.sin(t * 0.6) * 0.05;
    }
  });

  return (
    <group ref={ref}>
      <instancedMesh ref={meshRef} args={[undefined, undefined, NODE_COUNT]}>
        <sphereGeometry args={[1, 8, 8]} />
        <meshBasicMaterial color="#7ea8ff" transparent opacity={0.65} toneMapped={false} />
      </instancedMesh>

      {/* Edges merged into one draw call — the InstancedMesh decision
          rule from patterns-and-antipatterns.md applies to lines too:
          one lineSegments geometry, not N separate line meshes. */}
      <lineSegments>
        <bufferGeometry ref={lineGeoRef}>
          <bufferAttribute attach="attributes-position" args={[edgePositions, 3]} />
        </bufferGeometry>
        <lineBasicMaterial ref={lineMatRef} color="#4f8cff" transparent opacity={0.18} toneMapped={false} />
      </lineSegments>

      <IncidentPulse nodes={nodes} />
    </group>
  );
});

NetworkGraph.displayName = "NetworkGraph";
