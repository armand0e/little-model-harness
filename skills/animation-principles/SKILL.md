---
name: animation-principles
description: Use when designing or critiquing motion in UI, games, 2D, or 3D—especially timing, easing, weight, anticipation, overlap, readability, or reduced-motion behavior. Provides a medium-aware blocking, review, and polish workflow plus compact animation principles.
---

# Animation Principles

Motion often reads as alive when timing and spacing communicate physics and intent; it can read as robotic when interpolation is uniform without purpose. The principles transfer across a bouncing ball in Blender, a modal in CSS, and a jump in Godot, but their strength and implementation differ by medium.

## Reliable workflow

1. Define the action, intent, viewer focus, medium, frame rate, interaction constraints, and physical/stylistic reference.
2. Block only the key states or poses: start, anticipation if needed, action/extreme, overshoot or impact, and settle. Judge silhouette and staging before interpolation.
3. Set timing from distance, mass, force, and narrative importance. Preview at delivery speed and on the target device; do not judge motion by scrubbing alone.
4. Add easing, arcs, overlap, follow-through, and secondary motion one layer at a time. Preserve the primary action's readability.
5. Check frame-rate independence, loops, contacts, foot or object sliding, interruption/reversal, input latency, and `prefers-reduced-motion` or equivalent accessibility behavior.
6. Compare against reference and remove motion that has no communicative or tactile purpose.

When critiquing, identify the observed symptom, the likely motion cause, and the smallest change to test. Timing values below are starting ranges, not universal constants.

**Output:** Provide either a motion plan (`states/poses → timing → easing/overlap → tests`) or a critique (`symptom → cause → smallest change → verification`).

## The core: choose interpolation intentionally

Many physical and expressive motions accelerate or decelerate. **Ease-out** often suits entry or direct response, **ease-in** often suits exit or falling away, and **ease-in-out** often suits travel between resting states. Use `linear` for intentionally constant rates such as progress, conveyor motion, or continuous rotation. Choose from the motion's cause and perception rather than applying an entering/exiting rule mechanically.

CSS: `transition-timing-function: cubic-bezier(0.22, 1, 0.36, 1)` (snappy ease-out) beats the anemic default `ease`. In code, easing = a function mapping t∈[0,1] → progress: easeOutCubic `1-(1-t)³`, easeInCubic `t³`, easeInOutCubic, easeOutBack (overshoots slightly — great for pop-ins), easeOutElastic (springy).

## The 12 principles (Disney/Illusion of Life), condensed to what you'll use

1. **Squash & stretch** — deformation shows weight and speed. A ball flattens on impact, stretches in flight. VOLUME stays constant (squash wider when flatter). Subtle in UI (a button "presses"), strong in cartoons.
2. **Anticipation** — wind up before the action: crouch before jump, pull back before dash. Without it, actions read as teleports. Games: 2–6 frames of anticipation makes attacks readable.
3. **Staging** — one idea at a time; the important motion happens where the eye already is.
4. **Follow-through & overlapping action** — parts stop at different times: hair, cloth, antennae keep moving after the body stops; the hips lead, the arm follows. Nothing starts/stops all at once.
5. **Slow in / slow out** — the easing rule above; in keyframe tools, cluster frames near the ends of a move.
6. **Arcs** — natural motion travels in arcs, not straight lines. A head turn dips; a thrown ball is a parabola. Straight-line limb movement = robot.
7. **Secondary action** — small supporting motions (a walk + a swinging bag) enrich without distracting.
8. **Timing** — frame count IS the physics: fewer frames = fast/light/snappy, more frames = slow/heavy. A heavy door and a light door differ only in timing.
9. **Exaggeration** — push poses/speeds ~20–30% past realistic; captured-real motion reads as lifeless.
10. **Solid drawing/posing** — silhouettes must read; a good pose is recognizable in pure black silhouette.
11. **Appeal** — clear, asymmetric, non-stiff poses.
12. **(Straight-ahead vs pose-to-pose)** — workflow: block the KEY poses first at correct times, polish in-betweens later. Never animate frame-by-frame from the start.

## UI motion — the numbers

- Micro-interactions (hover, press, toggle): **100–150ms**. Small transitions (dropdown, tooltip): **150–250ms**. Larger (modal, page element, drawer): **250–400ms**. Anything > 500ms that blocks the user is too slow; users feel it immediately on the second use.
- Prefer compositor-friendly `transform` and `opacity` for frequent UI motion. Layout-affecting properties can be valid when layout change is the meaning, but measure them and consider FLIP or equivalent techniques when performance matters.
- Motion must MEAN something: show where a thing came from/went (the modal grows from the button that opened it), preserve continuity, direct attention. Decorative motion on every element is noise — and respect `prefers-reduced-motion`.
- Stagger list items entering by ~20–50ms each; full-list simultaneous fade looks cheap, but >80ms stagger feels slow.

## Game feel (juice)

Impact = many small cues layered: 2–4 frames of **hitstop** (freeze both actors), a 2–5px camera shake decaying over ~150ms, a flash on the hit target, particles, sound, and knockback with ease-out. Jumps: variable height (holding = higher), **coyote time** (~80ms grace to jump after leaving a ledge), input buffering (~100ms early inputs count). These forgivenesses are why good games feel "tight."

## 3D/character notes (Blender, three.js)

- Block key poses on stepped/constant interpolation first; judge timing; then switch to bezier and polish curves in the Graph Editor — curves, not keyframes, are where quality lives (check for unintended dips, kill foot-slide).
- Walk cycle anchors: contact → down → passing → up, ~24–32 frames/cycle at 24fps; hips are the root of everything, animate them first.
- In three.js/games, drive motion with easing/spring functions of elapsed time or use the mixer for baked clips — never move things by a fixed amount per frame (frame-rate dependent; see javascript-game-dev on delta time).

## Critique checklist

Robotic? → no easing, no arcs. Floaty? → too slow, no weight difference between light/heavy things, missing ease-in on falls. Teleporty? → no anticipation/follow-through. Mushy? → too long durations, too many things moving at once. Cheap? → everything moves at the same time with the same easing.
