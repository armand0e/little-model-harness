---
name: threejs-essentials
description: Use for anything three.js / WebGL 3D in the browser - scenes, cameras, materials, lighting, loading models, animation loops, shaders-adjacent questions, and performance. Provides the mental model, correct boilerplate, and the standard pitfalls.
---

# three.js Essentials

## Reliable workflow

1. Inspect the installed three.js revision, package/import-map setup, browser targets, renderer, color-management settings, asset encodings, and existing render loop. Match examples to that version.
2. Reduce to one visible primitive with camera, renderer, resize handling, and known lighting before adding models, postprocessing, controls, or interaction.
3. Add one subsystem at a time and verify coordinate space, units, transforms, material/light requirements, async loading, and ownership/disposal.
4. For visual defects, use helpers, unlit diagnostic materials, wireframe/normals, bounding boxes, and camera/frustum inspection. For performance, measure `renderer.info`, frame time, GPU time when available, and asset cost.
5. Test resize, high-DPI caps, context loss where relevant, loading failure, disposal/reload, and representative desktop/mobile hardware.
6. Return a minimal runnable example with exact imports and required DOM/CSS. State the verified three.js revision and any version-sensitive API.
7. For a delivered scene, use `visual_check` at desktop/mobile and capture multiple meaningful states or animation times with distinct `state_label` and `wait_ms` values. Inspect every attached image for composition, clipping, camera framing, lighting, and motion continuity; one initial frame is insufficient.

Do not repair an invisible object by randomly changing scale, camera, material, and lighting together; isolate one cause per test.

## The mental model

three.js = **scene graph** (tree of Object3Ds: meshes, lights, groups, cameras) + **renderer** that draws the graph from a camera's view every frame. A **Mesh = Geometry (shape) + Material (surface)**. Everything positioned in meters-ish world units, y-up, right-handed.

## Minimal correct setup (memorize this shape)

```js
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(75, innerWidth/innerHeight, 0.1, 1000);
camera.position.set(3, 2, 5);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(innerWidth, innerHeight);
renderer.setPixelRatio(Math.min(devicePixelRatio, 2)); // cap for perf
document.body.appendChild(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);

const mesh = new THREE.Mesh(
  new THREE.BoxGeometry(1, 1, 1),
  new THREE.MeshStandardMaterial({ color: 0x4488ff })
);
scene.add(mesh);
scene.add(new THREE.AmbientLight(0xffffff, 0.4));
const sun = new THREE.DirectionalLight(0xffffff, 2);
sun.position.set(5, 10, 7);
scene.add(sun);

const clock = new THREE.Clock();
renderer.setAnimationLoop(() => {          // preferred over raw rAF (XR-safe)
  const dt = clock.getDelta();
  mesh.rotation.y += dt * 0.8;             // scale ALL motion by dt
  controls.update();
  renderer.render(scene, camera);
});

addEventListener('resize', () => {
  camera.aspect = innerWidth/innerHeight;
  camera.updateProjectionMatrix();          // forget this = stretched scene
  renderer.setSize(innerWidth, innerHeight);
});
```

## Materials — which one

- `MeshBasicMaterial`: unlit, ignores lights (UI, flat color, debugging "why is it black").
- `MeshStandardMaterial`: PBR default — `color`, `roughness` (0 shiny→1 matte), `metalness`. Use this.
- `MeshPhysicalMaterial`: Standard + clearcoat/transmission (glass: `transmission:1, roughness:0`).
- Cheap stylized: `MeshLambertMaterial`/`MeshToonMaterial`. Points/lines have their own materials.
- **"My object is black"**: Standard/Lambert/Phong need LIGHTS. **"My object is invisible"**: camera inside it, wrong scale (model is 0.001 or 1000 units), or material `side` — set `side: THREE.DoubleSide` for planes seen from behind.

## Lights & shadows

Typical rig: dim `AmbientLight` or better `HemisphereLight` (sky/ground) + one `DirectionalLight` as sun. Shadows are OPT-IN everywhere: `renderer.shadowMap.enabled = true`, light `.castShadow = true`, each mesh `.castShadow`/`.receiveShadow = true`, and size the directional light's shadow camera to fit the scene. An `HDR/environment map` (`scene.environment` via `RoomEnvironment` or an HDRI) upgrades PBR materials from flat to gorgeous in five lines — highest quality-per-effort move in three.js.

## Loading models

glTF (.glb) is THE format — from Blender, export glTF; use `GLTFLoader` (+`DRACOLoader` if compressed). `gltf.scene` is a group: add it, then fix scale (`scene.scale.setScalar()`) and center if needed. Animations arrive as `gltf.animations`: play with `AnimationMixer` — create mixer per model, `mixer.clipAction(clip).play()`, and call `mixer.update(dt)` in the loop (forgetting the update = frozen animation).

## Interaction & structure

- Picking: `Raycaster` + normalized mouse coords (`(x/width)*2-1`, `-(y/height)*2+1`), `raycaster.setFromCamera`, `intersectObjects(scene.children, true)`.
- Group related objects in `THREE.Group`s; parent transforms compose (child position is relative to parent). To orbit B around A, add B as child of a pivot Group at A and rotate the pivot.
- Rotations: prefer `.rotation` (Euler) for simple cases; `Quaternion`/`lookAt` for aiming; beware gimbal issues when combining Euler axes.

## Performance (in impact order)

1. **Draw calls** are often a major CPU-side cost, but acceptable counts depend on device, material passes, geometry, shaders, and scene. Measure first; merge compatible static geometry or use `InstancedMesh` for many copies of one thing.
2. Cap `setPixelRatio(≤2)`. Shadows are expensive — limit shadow-casting lights (each = extra scene render).
3. Reuse geometries/materials; **dispose what you remove** (`geometry.dispose()`, `material.dispose()`, `texture.dispose()`) or leak GPU memory.
4. Use appropriately sized, mipmapped, and compressed textures such as KTX2 when the pipeline supports them. Power-of-two dimensions are useful or required for some formats/features, not a universal modern-WebGL rule.
5. Avoid high-volume transient allocation in hot loops when profiling shows garbage-collection pressure; reuse scratch objects where it improves measured frame stability.

## Debug kit

`console.log(scene)` and walk the tree; `AxesHelper`, `GridHelper`, `DirectionalLightHelper`, `CameraHelper` (for shadow cameras); lil-gui for live-tweaking values (roughness, positions) — tune visually, never by reload-guessing. Stats.js/`renderer.info` for draw calls and memory.
