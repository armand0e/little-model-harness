---
name: blender-animation-rigging
description: Use for Blender animation and rigging - keyframes, the Graph Editor, armatures, weight painting, IK/FK, walk cycles, and exporting animations to game engines or three.js. Pairs with animation-principles for the artistic side.
category: creative
hint: Blender rigging and animation
---
# Blender Animation & Rigging

Artistic principles (easing, anticipation, arcs, timing) live in the animation-principles skill; this is the Blender machinery.

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
- Don't hand-build production character rigs when **Rigify** (bundled addon) generates a full IK/FK-switching rig from a metarig you fit to the character.

## Walk cycle quick recipe (see animation-principles for theory)

24–32 frames, 4 key poses per side: **Contact** (heel strikes, legs widest) → **Down** (weight lands, body lowest) → **Passing** (free leg passes, body highest... rising) → **Up** (push off). Do poses at frames 1/…/loop, hips animated FIRST (they carry the mass: bounce twice per cycle, sway side to side, rotate), arms opposite legs, offset by a few frames (overlap). Make it cyclic in the Graph Editor.

## NLA & multiple actions (for games)

Each clip (idle, walk, run, jump) is an **Action** (Dope Sheet → Action Editor; the shield icon / fake user prevents Blender discarding unused actions on save — the classic lost-work trap). Stash actions into NLA tracks; on glTF export each action becomes a named animation clip that three.js (`AnimationMixer`) and Godot (AnimationPlayer) can play and crossfade.

## Export checklist (glTF → engines/three.js)

Apply object scale/rotation (`Ctrl+A`) BEFORE rigging (after = broken weights). Root the character at world origin, feet at Z=0. In the glTF exporter: include Animations, all actions; sample/bake if using constraints or IK (engines can't evaluate Blender constraints — baking converts them to plain keyframes). Test the .glb in an online glTF viewer before blaming the engine.

## Blender 4/5 scripting gotchas (animation)
- Keyframe with `obj.keyframe_insert(data_path="location", frame=n)` (also "rotation_euler", "scale"). NEVER use `action.fcurves.new()` / `adt.fcurves` — removed in 5.x.
- Interpolation defaults to Bezier; to change it, set `bpy.context.preferences.edit.keyframe_new_interpolation_type` BEFORE inserting keys.
- `scene.render.fps = 24`; frame range via `scene.frame_start/frame_end`.
- Constraints: `obj.constraints.new('TRACK_TO')` (enum string), then set `.target`.
- Verify by running `& '<blender.exe>' --background --python script.py` and reading stderr; render a preview with `--render-anim` only after the script runs clean.
