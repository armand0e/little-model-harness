---
name: blender-animation-rigging
description: Use for Blender animation and rigging - keyframes, the Graph Editor, armatures, weight painting, IK/FK, walk cycles, and exporting animations to game engines or three.js. Pairs with animation-principles for the artistic side.
---

# Blender Animation & Rigging

Artistic principles (easing, anticipation, arcs, timing) live in the animation-principles skill; this is the Blender machinery.

## Reliable workflow

1. Confirm the Blender version, target renderer/engine, frame rate, unit scale, clip list, root-motion convention, and export format before rigging.
2. Preserve a clean rest-pose source. Apply intended object transforms, fix topology and normals, name deform/control bones consistently, and test scale/orientation before detailed weights.
3. Build and validate one limb chain first: joint placement, roll, parent relationships, constraints, IK pole direction, deformation, and control reset.
4. Block key poses on stepped interpolation, approve timing, then polish curves, contacts, arcs, overlap, and transitions. Keep controls and deform bones conceptually separate.
5. Test extreme poses and inspect weight sums, volume loss, twists, foot/hand sliding, and constraint cycles.
6. Bake constraint-driven motion as required, export a minimal clip, and round-trip it in the target runtime before producing all actions.

Return exact mode, selection order, editor, and property names for procedural instructions. UI paths and bundled extensions can change across Blender releases, so verify version-specific steps.

## Keyframe basics

- `I` inserts a keyframe on the selected object/bone (Location/Rotation/Scale — or set up auto-keying: the record button in the timeline, powerful but dangerous: it keys EVERY tweak, so watch for accidental keys).
- Timeline scrub; `Spacebar` play; frame rate in Output properties (24 film / 30 / 60 game preview). Keyframes appear as diamonds; drag to retime.
- Three editors, one data: **Timeline** (scrubbing), **Dope Sheet** (retiming many keys — think columns of poses), **Graph Editor** (the actual F-curves — where quality happens).

## Graph Editor — where animation is actually polished

Every animated property is a curve of value vs time. Interpolation (`T`): **Constant/stepped** for blocking poses, **Bezier** for final. Handles (`V`): Auto-Clamped default, Vector for sharp impacts, Free for manual control.

Workflow: block all key poses on CONSTANT interpolation → judge timing by scrubbing → convert to bezier → polish curves: smooth arcs, ease-in/out clustering at pose extremes, offset curves so limbs don't all peak on the same frame (overlap), flatten foot curves during ground contact (kills foot-slide). `Shift+E` → cyclic modifier makes walk cycles loop.

## Rigging (armatures)

1. `Shift+A` → Armature. In Edit mode, `E` extrude bones from the root outward: hips → spine → head; hips → legs; chest → arms. Name every bone NOW (`spine.001` junk = pain later); use `.L`/`.R` suffixes and Blender mirrors behavior automatically (Symmetrize does the other side).
2. Bone placement = joint pivots: knee bone head at the actual knee, slight forward bend built into knees/elbows so IK knows which way to fold.
3. **Parent mesh to armature**: select mesh, shift-select armature, `Ctrl+P` → **Armature Deform with Automatic Weights**. This works 80%; fix the rest by weight painting.
4. **Weight painting** (select armature bone in Pose mode, then mesh → Weight Paint mode): red = fully driven by the bone, blue = not at all. Fix candy-wrapper twists and "thigh moves the belly" by smoothing/subtracting weights around joints. Each vertex's weights are normalized across bones.
5. Pose mode (`Ctrl+Tab`) is where animation happens; Edit mode edits the rest pose. `Alt+G/R/S` clears a bone's pose.

## IK vs FK

- **FK** (default): rotate each bone down the chain — natural for arcs (swinging arms, tails).
- **IK**: place a target, the chain solves — essential for feet planted on ground and hands on fixed objects. Add via bone constraint (Inverse Kinematics, chain length 2 for a leg) with a separate non-deforming target bone + pole target (aims the knee/elbow).
- Legs: almost always IK. Arms: FK for gesture/swing, IK for contact — rigs often switch.
- Consider **Rigify** or another maintained rig generator for conventional characters instead of hand-building every control. Availability and installation differ by Blender version; generated rigs still require fitting, deformation tests, and export validation.

## Walk cycle quick recipe (see animation-principles for theory)

24–32 frames, 4 key poses per side: **Contact** (heel strikes, legs widest) → **Down** (weight lands, body lowest) → **Passing** (free leg passes, body highest... rising) → **Up** (push off). Do poses at frames 1/…/loop, hips animated FIRST (they carry the mass: bounce twice per cycle, sway side to side, rotate), arms opposite legs, offset by a few frames (overlap). Make it cyclic in the Graph Editor.

## NLA & multiple actions (for games)

Each clip (idle, walk, run, jump) is an **Action** (Dope Sheet → Action Editor; the shield icon / fake user prevents Blender discarding unused actions on save — the classic lost-work trap). Stash actions into NLA tracks; on glTF export each action becomes a named animation clip that three.js (`AnimationMixer`) and Godot (AnimationPlayer) can play and crossfade.

## Export checklist (glTF → engines/three.js)

Apply object scale/rotation (`Ctrl+A`) BEFORE rigging (after = broken weights). Root the character at world origin, feet at Z=0. In the glTF exporter: include Animations, all actions; sample/bake if using constraints or IK (engines can't evaluate Blender constraints — baking converts them to plain keyframes). Test the .glb in an online glTF viewer before blaming the engine.
