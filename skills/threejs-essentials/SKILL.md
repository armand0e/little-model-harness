---
name: threejs-essentials
description: Use for anything three.js / WebGL 3D in the browser - scenes, cameras, materials, lighting, loading models, animation loops, shaders-adjacent questions, and performance. Provides the mental model, correct boilerplate, and the standard pitfalls.
category: creative
hint: Three.js: scenes, meshes, lights
---
# three.js Essentials

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

1. **Draw calls** rule everything: hundreds ok, thousands bad. Merge static geometry (`BufferGeometryUtils.mergeGeometries`) or use `InstancedMesh` for many copies of one thing (grass, particles, crowds — one draw call for 10,000 instances).
2. Cap `setPixelRatio(≤2)`. Shadows are expensive — limit shadow-casting lights (each = extra scene render).
3. Reuse geometries/materials; **dispose what you remove** (`geometry.dispose()`, `material.dispose()`, `texture.dispose()`) or leak GPU memory.
4. Textures: power-of-two sizes, compressed (KTX2) at scale; keep well under 2048² unless justified.
5. Don't create objects (`new Vector3`) inside the render loop — reuse scratch vectors; the GC hitches are your stutters.

## Debug kit

`console.log(scene)` and walk the tree; `AxesHelper`, `GridHelper`, `DirectionalLightHelper`, `CameraHelper` (for shadow cameras); lil-gui for live-tweaking values (roughness, positions) — tune visually, never by reload-guessing. Stats.js/`renderer.info` for draw calls and memory.

## Single-file pages (IMPORTANT for artifacts)
A page that must work when opened from disk (file://) or in a preview iframe CANNOT use ES module imports — they fail silently (black screen). Use the global build:
`<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/0.160.0/three.min.js"></script>` then the `THREE` global. No `type="module"`, no import maps, unless the page will be served over http. write_file auto-checks saved .html in a headless browser and reports console errors — read that report and fix before telling the user it works.
