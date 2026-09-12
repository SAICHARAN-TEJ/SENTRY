# Three.js — Core Mental Model

Source: threejs.org/manual (fundamentals, lights)

## The five building blocks

1. **Renderer** (`THREE.WebGLRenderer`) — takes a Scene + Camera, draws the visible portion to a canvas.
   ```js
   const renderer = new THREE.WebGLRenderer({ antialias: true, canvas });
   ```
2. **Camera** — defines the viewing frustum. `PerspectiveCamera` for realistic depth (the default for almost everything), `OrthographicCamera` for flat/isometric.
   ```js
   const camera = new THREE.PerspectiveCamera(fov, aspect, near, far);
   camera.position.z = 2;
   ```
3. **Scene** (`THREE.Scene`) — root of the scenegraph, a hierarchical tree; children's transforms are relative to their parent.
4. **Mesh** (`THREE.Mesh`) — Geometry (vertex data/shape) + Material (surface appearance) + Transform (position/rotation/scale).
   ```js
   const geometry = new THREE.BoxGeometry(1, 1, 1);
   const material = new THREE.MeshPhongMaterial({ color: 0x44aa88 });
   const mesh = new THREE.Mesh(geometry, material);
   scene.add(mesh);
   ```
5. **Material** — `MeshBasicMaterial` ignores lights entirely; `MeshPhongMaterial`/`MeshStandardMaterial` respond to lights. Reach for Standard/Physical for anything that needs to look real.

## Render loop

```js
function render(time) {
  time *= 0.001; // ms → s
  mesh.rotation.x = time;
  mesh.rotation.y = time;
  renderer.render(scene, camera);
  requestAnimationFrame(render);
}
requestAnimationFrame(render);
```

**Reuse geometry/material across meshes** — creating either inside the render loop is the #1 way to tank frame rate (see `patterns-and-antipatterns.md`).

## Lights — pick the cheapest one that does the job

| Light | Constructor | Cost | Use for |
|---|---|---|---|
| `AmbientLight` | `(color, intensity)` | minimal | fill so nothing is pure black — no directionality, no shadows |
| `HemisphereLight` | `(skyColor, groundColor, intensity)` | minimal | cheap "outdoor" base — sky-tint from above, ground-tint from below |
| `DirectionalLight` | `(color, intensity)` + needs `.target` | moderate | sun-like parallel rays; `scene.add(light, light.target)` |
| `PointLight` | `(color, intensity)`, optional `.distance` | higher | bulbs/lanterns, omnidirectional |
| `SpotLight` | `(color, intensity)`, `.angle`, `.penumbra` | higher | focused cone, needs `.target` too |
| `RectAreaLight` | `(color, intensity, width, height)` | **highest** — only `MeshStandardMaterial`/`MeshPhysicalMaterial`, needs `RectAreaLightUniformsLib.init()` first | large panel light (skylight, softbox) |

Direct quote from the manual, worth internalizing: *"Each light you add to the scene slows down how fast three.js renders the scene so you should always try to use as few as possible to achieve your goals."*

Baseline recipe that covers most "premium" 3D scenes: `AmbientLight` or `HemisphereLight` for fill + 1–2 `DirectionalLight` for shape. Reach for Point/Spot only for a specific practical light source in shot. Cap shadow-casting lights at 1–3 — shadows are the expensive part, not the light itself.
