---
name: javascript-game-dev
description: Use for building games in the browser with JavaScript - Canvas 2D games, three.js 3D games, the game loop, input, collision, simple physics, and browser-specific gotchas (audio unlock, timing, performance). Engine-level how-to; design theory lives in game-design-fundamentals.
category: creative
hint: browser games: canvas, loops, physics
---
# JavaScript Game Development (Canvas 2D & three.js 3D)

## The loop — get this right first

```js
let last = performance.now();
function frame(now) {
  const dt = Math.min((now - last) / 1000, 0.1); // seconds; clamp huge tab-switch gaps
  last = now;
  update(dt);
  render();
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
```
- ALL movement scales by dt: `x += speed * dt` (speed in px- or units-per-SECOND). `x += 5` per frame = double speed on 120Hz monitors — the classic bug.
- Clamp dt (tab-switch pauses give a giant dt → player teleports through walls).
- For physics needing determinism, accumulate dt and run fixed steps (e.g., 1/60) inside the loop.

## Input — state, not events

Events fire once; games need "is it held NOW":
```js
const keys = new Set();
addEventListener('keydown', e => keys.add(e.code));
addEventListener('keyup',   e => keys.delete(e.code));
// in update: if (keys.has('ArrowLeft')) player.vx = -SPEED;
```
Use `e.code` (layout-independent: 'KeyW'). Prevent default on arrows/space (page scrolls!). Mouse: track position from `mousemove` + button state; for canvas coords subtract `canvas.getBoundingClientRect()`. Touch: pointer events cover both. Feel-good extras: input buffering and coyote time (see animation-principles → game feel).

## Canvas 2D core

```js
const ctx = canvas.getContext('2d');
// each frame:
ctx.clearRect(0, 0, canvas.width, canvas.height);
ctx.drawImage(sprite, x, y);                    // or sheet: drawImage(img, sx,sy,sw,sh, dx,dy,dw,dh)
```
- Resolution: set `canvas.width/height` attributes (drawing buffer), scale with CSS; for crisp pixel art add `image-rendering: pixelated` and `ctx.imageSmoothingEnabled = false`, and draw at integer coordinates (`Math.round`) to avoid blur.
- Transforms: `ctx.save() → translate/rotate/scale → draw → ctx.restore()`. Rotate around a sprite's center: translate to center, rotate, draw at (-w/2, -h/2).
- Camera = draw everything offset by `-camera.x, -camera.y` (wrap the frame in one translate). Screen shake = random small camera offset decaying over ~150ms.
- Sprite animation: sprite sheet + `frame = Math.floor(t * fps) % frameCount`, draw the sub-rectangle.

## Collision (2D)

- **AABB** (axis-aligned boxes) covers 90%: `a.x < b.x+b.w && a.x+a.w > b.x && a.y < b.y+b.h && a.y+a.h > b.y`.
- Circles: `dx*dx + dy*dy < (r1+r2)**2` (compare squared — no sqrt).
- Resolution, not just detection: move on X, resolve X overlaps, THEN move on Y, resolve Y — separating axes kills the "sticks on walls/corners" bug. Fast objects tunnel through thin walls: sub-step the movement or raycast.
- Platformer gravity: `vy += GRAVITY*dt; y += vy*dt;` grounded check = collided below this frame. Jump = `vy = -JUMP_V` only when grounded (+ coyote time).
- Many entities? Broad-phase with a spatial grid before pairwise checks (n² dies around a few hundred entities).

## three.js for 3D games

Rendering/setup lives in threejs-essentials. Game-specific additions:
- Player-relative movement: get camera forward `camera.getWorldDirection(v)`, flatten (`v.y=0; v.normalize()`), strafe = cross with up; move by `dir * speed * dt`. First-person: `PointerLockControls`; third-person: lerp the camera toward a target offset behind the player (`pos.lerp(target, 1 - Math.pow(damp, dt))` for framerate-independent smoothing).
- Collision: keep GAMEPLAY collision simple (spheres/AABBs/`Box3`, raycast down for ground height) even when visuals are complex meshes. Real physics → a library: **Rapier** (best current choice) or cannon-es: physics world steps fixed, you copy body transforms onto meshes each frame.
- Animations: `AnimationMixer`, crossfade clips on state change (`action.fadeIn(0.2)`, old one `fadeOut`), driven by the entity's state machine.
- Shooting/interaction: `Raycaster` from camera center.

## Browser gotchas

- **Audio is locked until a user gesture**: create/resume `AudioContext` (or play sounds) only after first click/keypress — the silent-game bug. Pool `Audio` clones or use WebAudio for overlapping SFX.
- Asset loading is async: `await` image/model/audio loads (or a loading manager) BEFORE starting the loop; drawing an unloaded image silently draws nothing.
- Save games: `localStorage` (JSON.stringify; wrap in try/catch — private mode throws).
- Performance: don't allocate in the loop (reuse vectors/objects/arrays — GC pauses are your stutters); object-pool bullets/particles; measure with the Performance tab before optimizing anything.
- Ship = a static page. Test on a phone early: touch input, aspect ratios, and perf cliffs surprise late.

## Starting-point architecture (see game-design-fundamentals)

`Game` holds state (menu/playing/paused switch in update+render), an entities array (each with `update(dt)`/`render(ctx)`), input module, asset store. Entity states as explicit state machines. Resist building "an engine" — build the game; extract reusable parts after they exist twice.
