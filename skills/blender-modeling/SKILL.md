---
name: blender-modeling
description: Use for Blender questions about modeling, topology, modifiers, materials/shading, UVs, rendering, and exporting to game engines or three.js. Covers the workflow, the shortcuts that matter, and the classic beginner traps.
category: creative
hint: Blender modeling, materials, rendering
---
# Blender Modeling

## Orientation (the 20 shortcuts that are 90% of modeling)

- Modes: `Tab` toggles Object/Edit mode. In Edit mode: `1/2/3` = vertex/edge/face select.
- Transform: `G` grab, `R` rotate, `S` scale — then `X/Y/Z` to lock axis (`Shift+Z` = all but Z), type a number for exact amounts, `Enter` to confirm. These work on objects, vertices, bones, keyframes — everywhere.
- Add mesh `Shift+A`; duplicate `Shift+D`; delete `X`. `E` extrude, `I` inset, `Ctrl+B` bevel, `Ctrl+R` loop cut (scroll for count), `K` knife, `F` fill face, `M` merge vertices.
- `A` select all, `Alt+Click` select edge loop, `L` select linked, `Ctrl+L` select connected.
- View: numpad `1/3/7` front/right/top (`Ctrl+` for opposite), `5` ortho/persp, `.` (numpad) frame selected. `Z` shading pie menu (wireframe/solid/material/rendered).
- `N` side panel (exact transforms), `F9` redo-last-operation panel (where the options for what you just did live — beginners miss this constantly).

## The workflow: block → refine → detail

1. **Block out** the whole object from primitives at correct PROPORTIONS first. Judge silhouette before any detail. Reference images in the viewport (drag in, or Shift+A → Image).
2. **Refine** with loop cuts, extrusions, bevels. Work at the lowest polycount that holds the shape.
3. **Detail** last — and prefer modifiers/normal maps over real geometry.

## Modifiers (non-destructive power — use instead of manual work)

Order matters (top executes first). The big five:
- **Subdivision Surface** (`Ctrl+1/2/3`): smooths by subdividing. Control the shape with edge loops placed near edges you want sharp (or `Shift+E` crease). The universal "make it smooth" tool.
- **Mirror**: model half, get both. Delete the other half FIRST, enable clipping so center verts weld. Do this for every symmetric object — faces, vehicles, characters.
- **Array**: rows of duplicates (fences, stairs) — combine with Curve modifier to follow paths.
- **Bevel (modifier)**: nothing real has razor edges; a small bevel catches light and instantly reads "manufactured, not CGI."
- **Boolean**: cut/join shapes — powerful but leaves messy topology; fine for hard-surface + bevel-by-shading, risky before subdivision.

Apply modifiers (`Ctrl+A` → or in the dropdown) only when you must (export, further sculpting) — keep them live as long as possible.

## Topology rules (why models shade badly or animate badly)

- **Quads** (4-sided faces) are the goal wherever the mesh deforms or gets subdivided; triangles okay on flat static areas; **n-gons** (5+) cause shading artifacts and subdivision pinching — trapped only on flat faces.
- Even quad flow following the form's curvature; **edge loops encircle** joints (shoulder, elbow, knee, mouth, eyes) so deformation has hinges.
- **Poles** (verts with 3 or 5+ edges) are unavoidable — steer them AWAY from deforming/curved areas.
- Artifact diagnosis: weird shading streaks = n-gons/poles on a curve, or **flipped normals** (fix: select all, `Shift+N` recalculate outside), or doubled vertices (`M` → Merge by Distance — the classic fix for "black seams" and "subdivision looks crumpled").
- **Scale in Object mode is a trap**: it changes the object's scale property, silently breaking modifier thickness, texture density, and physics. After scaling an object, `Ctrl+A → Apply Scale`. Rule: apply rotation & scale before rigging, exporting, or adding modifiers that measure distance (Bevel, Solidify).

## Materials, UVs, baking (the path to game/three.js assets)

- Shading workspace; the **Principled BSDF** is the everything-shader: Base Color, Roughness, Metallic (0 or 1, rarely between), Normal. Maps plug into these sockets via Image Texture nodes (set non-color data for roughness/normal maps!).
- **UV unwrap**: in Edit mode mark seams (`Ctrl+E` → Mark Seam) along hidden edges like a tailor, select all, `U` → Unwrap. Check with a checker texture — squares should be square and evenly sized. Smart UV Project is acceptable for hard-surface props.
- High-detail → low-poly workflow: sculpt/model high, retopo or decimate low, bake normal map from high onto low. Games/three.js want the low mesh + baked maps.

## Render & export

- **Cycles** = path-traced, realistic, slower (denoiser on). **Eevee** = rasterized, real-time, great for stylized/preview. Lighting beats materials: an HDRI environment (World → Environment Texture) + one key light outperforms hours of shader fiddling.
- **Export to three.js/Godot: glTF 2.0 (.glb)**. Before exporting: apply scale/rotation, check +Y-up option (default handles it), pack or keep textures relative, name objects sensibly. Only Principled BSDF-based materials survive export — procedural node tricks must be BAKED to textures first.
- Units: Blender unit = 1 meter by default; keep real-world scale (a door ≈ 2m) so physics and lighting behave everywhere downstream.

## Scripting Blender headlessly (Blender 4/5 — IMPORTANT)
Blender is usually at `C:\Program Files\Blender Foundation\Blender <ver>\blender.exe`. Find it with `run("Get-ChildItem 'C:\Program Files\Blender Foundation' -Filter blender.exe -Recurse | Select -First 1 -Expand FullName")` — a PowerShell parse error does NOT mean Blender is missing; invoke exes with spaces via `& 'C:\path\blender.exe' args`.

Workflow: write a Python script, run `& '<blender.exe>' --background --python script.py`, READ the stderr, fix, rerun.

API gotchas (Blender 4/5 renamed things — do not trust older snippets):
- Modifiers belong to OBJECTS not meshes: `obj.modifiers.new("Name", 'SUBSURF')` (type is `SUBSURF`, not SUBDIVISION).
- FPS: `scene.render.fps = 24` (not `scene.fps`).
- Constraints use enum types: `obj.constraints.new('TRACK_TO')`.
- Animation: use `obj.keyframe_insert(data_path="location", frame=n)` — do NOT touch `action.fcurves` / `adt.fcurves` (the slotted-action API replaced them in 5.x and is a trap).
- Meshes: build with `mesh.from_pydata(verts, edges, faces)` then `mesh.update()`.
- If an API call errors, `web_search` the current Blender API before guessing again.
