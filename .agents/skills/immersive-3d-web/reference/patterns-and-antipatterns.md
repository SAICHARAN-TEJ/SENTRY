# Patterns and anti-patterns for premium 3D web sites

Synthesized from three-core.md, performance.md, r3f-drei.md, gsap-scroll.md — this file is the "how the pieces combine" layer, not a new source.

## The recipe behind most Awwwards-style 3D hero sites

1. `Canvas` (R3F) fills the viewport, `position: fixed` or pinned via ScrollTrigger.
2. Lighting via drei `Environment` (HDRI) instead of hand-placed lights — one line, looks "product photography" immediately.
3. `ContactShadows` for grounding instead of a real shadow map — cheap, looks expensive.
4. Hero asset via `useGLTF`, camera or object driven every frame from `ScrollTrigger`'s `onUpdate` progress (see `gsap-scroll.md`), applied inside `useFrame`.
5. Repeated background elements (particles, floating shapes) via `InstancedMesh`, never as N separate meshes.
6. `matchMedia()` breakpoint that disables/simplifies the scroll-3D on mobile.

## Anti-patterns (each one is a real, common perf killer)

- **Allocating geometry/material inside the render loop or `useFrame`.** Every `new THREE.BoxGeometry(...)` inside a per-frame callback is a GC pause waiting to happen. Create once, mutate properties (position/rotation/scale) per frame.
- **One `Mesh` per data point / particle instead of `InstancedMesh` or merged geometry.** This is *the* documented failure mode (19k meshes: <20fps; merged: 60fps). Decide up front: do these move independently after creation? → instancing. Are they static? → merge.
- **Stacking `PointLight`/`SpotLight` for atmosphere.** Each shadow-casting light is a full extra render pass. Start from `AmbientLight`/`HemisphereLight` + 1–2 `DirectionalLight`; add expensive lights only for a specific practical source that's actually in shot.
- **Animating with a fixed per-frame increment instead of `delta`.** `rotation.x += 0.01` runs at different real-world speed on a 144Hz vs 60Hz vs throttled-mobile display. Always `rotation.x += delta * speed`.
- **Driving Three.js object properties through GSAP's default DOM/CSS tweening.** Three.js props aren't CSS properties; read `ScrollTrigger` progress in `onUpdate` and apply it explicitly inside `useFrame`, don't `gsap.to(mesh.position, ...)` and assume it's free — it works, but it bypasses R3F's render scheduling, so prefer the explicit read-and-apply pattern for anything perf-sensitive.
- **No mobile fallback for scroll-jacked 3D.** A pinned full-viewport WebGL scene with scrub animation is a common battery/frame-rate disaster on phones. Use GSAP's `matchMedia()` to serve a static image or simplified scene below a breakpoint — a deliberate scope decision, not an afterthought.
- **No `prefers-reduced-motion` fallback.** Scroll-jacked pins, camera dollies, and continuous idle rotation are exactly the motion this media query exists to suppress — treat it as an accessibility bug, not a nice-to-have. Check `matchMedia("(prefers-reduced-motion: reduce)")` before creating the `ScrollTrigger` (skip the pin/dolly, leave the camera at rest) and inside continuous `useFrame` rotation (skip the write, render static). See `hero-dressing.md` for the full pattern including the CSS-side equivalent for non-WebGL entrance animation.
- **Not disposing geometries/textures/materials on unmount in R3F.** Three.js objects hold GPU memory that React's garbage collector doesn't know about. Long-lived SPAs that mount/unmount 3D scenes repeatedly (route changes) leak GPU memory unless geometries/materials/textures are explicitly `.dispose()`d — R3F handles some of this automatically for objects it owns, but manually created resources (e.g. inside `useMemo`) are your responsibility.
- **Skipping DPR clamping.** Rendering at full device pixel ratio on a high-DPI phone (3x) can be 9x the fragment shader cost of 1x for zero visible benefit at arm's length. R3F's `<Canvas dpr={[1, 2]}>` caps it — set it explicitly rather than trusting the default on unknown devices.
- **Canvas stuck at the browser's default 300×150 intrinsic size.** Observed directly: a `<Canvas>` mounted correctly, its parent container measured the right size in the DOM, no console error — but the WebGL canvas itself rendered at 300×150 and nothing was visible (confirmed by reading back canvas pixels: fully transparent). R3F sizes the canvas off its container via `ResizeObserver` on mount, and on that occasion the first measurement landed before the container had settled, and no later layout event re-triggered it. Manually dispatching a `resize` event (`window.dispatchEvent(new Event("resize"))`) forced an immediate correct re-measure. Cheap defensive fix: dispatch one resize event ~50–100ms after the `Canvas`-containing component mounts. If a scene ever renders as a blank/transparent canvas with no errors, check `canvas.width`/`canvas.height` (not `clientWidth`/`clientHeight`) before assuming the scene graph itself is broken — a 300×150 result means it's a sizing issue, not a rendering one.
