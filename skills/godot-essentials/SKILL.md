---
name: godot-essentials
description: Use for Godot Engine (4.x) questions - nodes, scenes, GDScript, signals, physics bodies, input, UI, animation, and project structure. The engine-specific counterpart to game-design-fundamentals.
---

# Godot Essentials (4.x)

## Reliable workflow

1. Inspect the exact Godot version, renderer, project settings, input map, autoloads, scene tree, and error output. Do not assume every 4.x minor release or 3.x project uses the same API.
2. Reduce the task or bug to one runnable scene. Identify node ownership, lifecycle callback, coordinate space, physics step, and signal direction.
3. Choose the engine-native abstraction: node composition, resource, signal, group, animation, physics body, container, or autoload. Avoid deep parent traversal and global state without a clear owner.
4. Implement one vertical path and run it. Inspect the Remote scene tree, debugger, monitors, visible collisions, and actual property values rather than inferring them.
5. Test scene reload, pause, resize, different frame rates, missing nodes/resources, repeated signals, and the target export platform as relevant.
6. Report the exact node path, script location, setup steps, and verified engine version.

For code examples, state any required Input Map actions, scene hierarchy, collision layers/masks, and Inspector values; code alone may be incomplete.

## The mental model: everything is a node; scenes are prefabs

- A **node** does one job (Sprite2D draws, CollisionShape2D collides, Timer counts, Camera2D views). You build entities by COMPOSING nodes in a tree.
- A **scene** (.tscn) is a saved node tree — Godot's prefab. A Player scene, a Bullet scene, a Level scene that INSTANCES them. Any scene can be instanced inside any other; the game is a tree of scene instances.
- Design rule: each scene should work on its own (press F6 to run just that scene). Communicate UP the tree with signals, DOWN with direct calls ("call down, signal up") — a child should never `get_parent()` into specifics.

## GDScript in 60 seconds

```gdscript
extends CharacterBody2D                      # script attaches to a node type

@export var speed := 300.0                   # editable in the Inspector
@onready var sprite := $AnimatedSprite2D     # $ = get_node, grabbed when ready

signal died(score: int)                      # declare custom signals

func _ready() -> void:                       # once, when entering the tree
    pass

func _physics_process(delta: float) -> void: # fixed timestep — movement/physics here
    var dir := Input.get_axis("move_left", "move_right")
    velocity.x = dir * speed
    velocity.y += 980.0 * delta              # gravity
    move_and_slide()                          # CharacterBody2D's built-in mover
    if Input.is_action_just_pressed("jump") and is_on_floor():
        velocity.y = -420.0
```
Python-like, typed hints encouraged (`:=` infers). `_process(delta)` every frame (visuals), `_physics_process(delta)` fixed 60Hz (movement, physics). Always scale motion by `delta` in `_process`; `move_and_slide()` uses `velocity` (property in 4.x) internally.

## The four physics body types (choosing wrong = fighting the engine)

- **CharacterBody2D/3D**: player/NPCs you move in code — `move_and_slide()`, `is_on_floor()`. Not pushed by physics.
- **RigidBody**: real physics (crates, ragdolls, balls). DON'T set its position directly — apply forces/impulses, or it fights the solver.
- **StaticBody**: level geometry, walls, floors.
- **Area2D/3D**: no collision response, only detection — pickups, hurtboxes, triggers, zones (`body_entered` signal).
Every body needs a CollisionShape child with an actual shape. Use collision LAYERS (what I am) and MASKS (what I detect) — e.g., enemy bullets mask the player layer only, so they never hit each other.

## Signals — Godot's event system

Built-in: `body_entered`, `timeout`, `pressed`, `animation_finished`. Connect in the editor (Node panel) or code:
```gdscript
timer.timeout.connect(_on_timer_timeout)
died.emit(score)                # firing your own
```
Signals decouple: the coin emits `collected`; the HUD and sound manager listen; the coin knows neither. For genuinely cross-scene events or state, a small **autoload** (Project Settings → Globals) can own shared signals or run-persistent state. Keep its interface narrow; not every convenient reference belongs in a global singleton.

## Input

Define actions in Project Settings → Input Map ("jump", "move_left" — bind keys AND gamepad to the same action; never hardcode keys). `Input.is_action_pressed` (held) / `is_action_just_pressed` (this frame) / `Input.get_axis(neg, pos)` / `get_vector` for 2D movement.

## Common recipes

- Spawn things: `const BULLET := preload("res://bullet.tscn")` → `var b := BULLET.instantiate(); get_tree().current_scene.add_child(b); b.global_position = muzzle.global_position` (add bullets to the level, NOT the gun, or they inherit the gun's motion).
- Change level: `get_tree().change_scene_to_file("res://level_2.tscn")`. Reload: `get_tree().reload_current_scene()`.
- Timers: one-shot delay = `await get_tree().create_timer(0.5).timeout` right in a function.
- Tweens (code-driven animation — see animation-principles for easing choice): `create_tween().tween_property(sprite, "scale", Vector2(1.3,1.3), 0.1).set_ease(Tween.EASE_OUT)`.
- **AnimationPlayer** keyframes ANY property of any node (sprites, sounds, function calls) — cutscenes, attack combos; **AnimatedSprite2D** for simple frame animation; **AnimationTree** + state machine for blending character animations (walk↔run↔jump), driven by your code's state.
- UI: Control nodes with **containers** (VBox/HBox/Margin/Grid) + anchors so it survives resizing — don't pixel-position UI. CanvasLayer keeps HUD fixed over a moving camera.
- Pause: `get_tree().paused = true`; set the pause menu's Process Mode to "When Paused".

## Debugging & structure

`print()` and the Remote tab (inspect the LIVE scene tree while running — invaluable for "where did my node go"); breakpoints in the script editor; Visible Collision Shapes in the Debug menu (the "why don't these collide" answer is visible instantly — usually layer/mask or a missing shape). Errors about null nodes = wrong `$` path or accessing before `_ready`. Organize: one directory per entity (player/player.tscn + player.gd + sprites), snake_case files, PascalCase node names. Godot-specific scoping advice and design theory: game-design-fundamentals.
