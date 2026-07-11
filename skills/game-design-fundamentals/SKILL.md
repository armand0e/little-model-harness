---
name: game-design-fundamentals
description: Use when designing a game - mechanics, difficulty, progression, "why isn't my game fun", scoping a game project, or engine-agnostic architecture (game loop, state machines, entities). The design layer above any specific engine.
category: creative
hint: mechanics, loops, balance, playtesting
---
# Game Design Fundamentals

## The loop is the game

Every game is a **core loop** the player repeats hundreds of times: (act → feedback → reward/consequence → slightly changed situation → act). Mario: run/jump → land or die → progress. Design and polish the core loop FIRST; if 60 seconds of the raw loop isn't engaging with placeholder art, more content won't save it. Content multiplies fun; it cannot create it.

## What makes it fun (usable levers)

- **Meaningful decisions**: fun ≈ interesting choices under constraint (which weapon, risk the shortcut?, spend or save). If one option is always right, it's not a choice — buff the others or cut it.
- **Mastery curve**: easy to learn, hard to master. The player should always have something they're getting better AT, and FEEL it (old levels feel easy now).
- **Flow channel**: difficulty tracks skill. Too hard → frustration; too easy → boredom. Ramp difficulty, then briefly release after peaks (a breather room after the boss). Difficulty should come from the challenge itself, never from bad controls or unclear information.
- **Feedback & juice**: every action visibly/audibly lands (see animation-principles → game feel). Weak feedback reads as "floaty/unresponsive" long before players can articulate why.
- **Clear goals at 3 ranges**: right now (kill this enemy), this session (finish the level), long term (beat the game / build the base).
- **Fairness**: deaths must feel like the player's fault. Telegraph attacks, keep hitboxes honest (slightly generous TOWARD the player: bullets smaller than sprites, ledge grabs forgiving), never off-screen cheap shots. Players forgive difficulty; they quit over unfairness.

## Scope — the #1 killer of game projects

Your first estimate is 5–10× too small (see cognitive-biases → planning fallacy). Rules:
- First finished game: ONE mechanic, one level, one enemy type, one week. Finishing teaches more than five abandoned epics. An MMO/open-world/roguelike-with-everything as a first project has a ~100% mortality rate.
- Build a **vertical slice** (one polished minute of real gameplay) before ANY content breadth.
- Cut features, not quality. The feature that defines your game gets 80% of the time; everything else ships minimal or dies. Placeholder art until the design is proven.

## Engine-agnostic architecture

- **The game loop**: `input → update(dt) → render`, repeating. ALL movement/timers scale by `dt` (delta time, seconds since last frame) so behavior is identical at 30 and 144 fps. Fixed-timestep updates for physics; variable for rendering (engines like Godot expose both: `_physics_process` vs `_process`).
- **State machines everywhere**: game states (menu→playing→paused→game-over) and entity states (idle→run→jump→fall→attack) as explicit enums with allowed transitions. Booleans multiplying (`isJumping && !isAttacking && canDash…`) = you needed a state machine three bugs ago.
- **Composition over inheritance**: entities as containers of parts (position, sprite, health, AI) rather than a `Player extends Actor extends Entity` tower. Engines embody this — Godot nodes/scenes, Unity components.
- **Decouple with events/signals**: the enemy emits "died"; scoring, sound, and spawner listen. Nobody holds references into everybody.
- Separate SIMULATION from PRESENTATION: game logic shouldn't know about sprites; makes testing, replays, and multiplayer feasible.

## Difficulty & progression tools

Introduce mechanics one at a time: **teach in isolation → test in combination → escalate → twist** (Nintendo's kishōtenketsu level pattern). New ability? First room requires it in a safe context. Economy/progression: reward curve should front-load (fast early wins) then stretch; watch for degenerate strategies (grinding the safest option) — players optimize the fun out of your game if the optimal path is boring; make the fun thing the effective thing.

## Playtesting (the design feedback loop)

Watch someone play WITHOUT helping or explaining — every instruction you blurt is a design failure noted. Watch for: where they look confused, what they try that doesn't work, where they die repeatedly, when they check their phone. Ask afterward what they thought was happening (their model vs yours). One real playtest beats ten internal debates. Iterate: designs are discovered, not specified.
