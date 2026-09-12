# Performance — many objects, one frame budget

Source: threejs.org/manual (optimize-lots-of-objects), threejs.org/docs (InstancedMesh)

Three.js scales by **draw calls**, not triangle count. 19,000 tiny meshes will choke a scene that would happily render 19,000× the triangles in one draw call. Two techniques, pick by whether the objects move independently.

## 1. Merge geometries (static objects, one shared material)

If objects never need independent per-instance transforms after creation — data-viz points, terrain chunks, decorative clutter — merge them into a single `BufferGeometry` up front.

```js
import * as BufferGeometryUtils from 'three/addons/utils/BufferGeometryUtils.js';

const mergedGeometry = BufferGeometryUtils.mergeGeometries(geometries, false);
const material = new THREE.MeshBasicMaterial({ vertexColors: true });
const mesh = new THREE.Mesh(mergedGeometry, material);
scene.add(mesh);
```

Measured on the manual's own example: ~19,000 separate meshes = under 20fps; merged into one draw call = 60fps.

Since a merged mesh has one material, use **vertex colors** for per-object color variation instead of per-object materials:

```js
const colorAttrib = new THREE.BufferAttribute(colors, 3, true); // Uint8Array, normalized
geometry.setAttribute('color', colorAttrib);
// material needs vertexColors: true
```

Trade-off: you lose the ability to move/transform individual pieces after the merge. If you need that, use instancing instead.

## 2. Instancing (many copies, each independently transformed)

`THREE.InstancedMesh` — one geometry + one material, N independent transforms (and optionally colors), rendered in a single draw call.

```js
const mesh = new THREE.InstancedMesh(geometry, material, count);

const matrix = new THREE.Matrix4();
matrix.setPosition(x, y, z);
mesh.setMatrixAt(index, matrix);
mesh.instanceMatrix.needsUpdate = true; // required after any setMatrixAt call

mesh.setColorAt(index, color); // requires material to support instanceColor
```

- `count` is fixed at construction — need a different count, make a new `InstancedMesh`.
- `getMatrixAt(index, matrix)` / `getColorAt(index, color)` read back into a matrix/color you provide.
- This is the tool for particle fields, crowds, foliage, repeated product variants — anything "many of the same thing, each somewhere different."

## 3. Scene graph hygiene

Don't create helper `Object3D`s per item when a single reused helper will do the same matrix math:

```js
// slow: 3 helpers × 19,000 items = 60,000 scenegraph nodes
// fast: one shared helper, read its matrixWorld after each update, discard
positionHelper.updateWorldMatrix(true, false);
geometry.applyMatrix4(originHelper.matrixWorld);
```

Baking a transform into geometry vertices via `.applyMatrix4()` is cheaper than carrying it as a live mesh transform when the object never needs to move again.

## Rule of thumb

| Objects move independently after creation? | Technique |
|---|---|
| No | Merge geometries |
| Yes, but share geometry/material | `InstancedMesh` |
| Yes, and each is visually unique | Neither helps — budget your draw calls directly |
