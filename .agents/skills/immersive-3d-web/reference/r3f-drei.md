# React Three Fiber + drei

Source: r3f.docs.pmnd.rs, drei.docs.pmnd.rs

## Why R3F instead of raw Three.js

React Three Fiber is a React renderer for Three.js — not a wrapper, a renderer. Its own stated tenets:

- **No limitations**: *"Everything that works in Threejs will work here without exception."*
- **No performance overhead**: *"There is no overhead. Components render outside of React."*
- **Automatic feature parity**: new Three.js releases work without waiting on library updates, because JSX elements map 1:1 to Three.js constructors.

## JSX → Three.js mapping

Every Three.js export is available as a lowercased JSX tag: `<mesh />` becomes `new THREE.Mesh()`, `<ambientLight />` becomes `new THREE.AmbientLight()`, `<boxGeometry />` becomes `new THREE.BoxGeometry()`. Props become constructor args / property assignments.

```jsx
<Canvas>
  <ambientLight intensity={0.5} />
  <directionalLight position={[-1, 2, 4]} />
  <mesh>
    <boxGeometry args={[1, 1, 1]} />
    <meshStandardMaterial color="#44aa88" />
  </mesh>
</Canvas>
```

`<Canvas>` is the root: owns the renderer, scene, default camera, and the render loop. Everything 3D goes inside it; regular DOM/React goes outside it.

## Core hooks

- **`useFrame((state, delta) => { ... })`** — subscribes to the render loop, runs every frame. Always animate off `delta`, not a fixed increment, so motion is frame-rate independent:
  ```js
  useFrame((state, delta) => (meshRef.current.rotation.x += delta))
  ```
- **`useThree()`** — grab the live `camera`, `scene`, `gl` (renderer), `viewport`, `size` from context instead of prop-drilling them.
- **`useLoader(Loader, url)`** — declarative asset loading with suspense.
- Combine with a plain `useRef` for imperative access to the underlying Three.js object (position/rotation/scale mutations happen outside React state, on purpose — that's the "no overhead" part).

## drei — the helper library, not raw Three.js reinvented

`@react-three/drei` is "a growing collection of useful helpers and ready-made abstractions" for R3F. Reach for these before hand-rolling the Three.js equivalent:

**Cameras & controls**
- `PerspectiveCamera` / `OrthographicCamera` — declarative camera setup
- `CameraControls` — orbit/pan/zoom manipulation
- `ScrollControls` — ties scene state to page scroll position (see `gsap-scroll.md` for the GSAP alternative/complement)

**Loaders**
- `useGLTF` — load 3D models (glTF/GLB)
- `useTexture` — load textures
- `useFont` — load typography for 3D text

**Staging & environment** — this is the fastest path to the "premium product render" look:
- `Environment` — HDRI-based lighting + reflections in one component
- `ContactShadows` — cheap, good-looking ground shadow without full shadow-map setup
- `Sky` — atmospheric sky dome

**Utilities**
- `Html` — mount real DOM/React content anchored to a 3D position (labels, tooltips, UI overlays inside the scene)
- `useProgress` — track asset loading for a loading screen
- `useFBO` — off-screen render targets (custom post-processing, portals, render-to-texture effects)

## Practical default

For a "powerful 3D site" hero (the HorizonX-style look): `Canvas` + `Environment` (lighting done in one line) + `ContactShadows` (grounding without shadow-map tuning) + `useGLTF` for the hero asset + `CameraControls` or a `useFrame`-driven camera path. Add GSAP ScrollTrigger on top to drive camera/object state from scroll — R3F doesn't fight this, since `useFrame` and imperative refs are exactly the escape hatch for external animation libraries.
