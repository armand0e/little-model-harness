---
name: physics-intuition
description: Use for physics questions, "what happens if" physical scenarios, everyday mechanics (falling, floating, heat, electricity, light), energy claims, and detecting physically impossible statements. Provides laws, key numbers, and the misconceptions to avoid.
---

# Physics Intuition

## Reliable workflow

1. Define the system boundary, reference frame, time interval, and idealizations. Draw forces, energy flows, rays, or a circuit before calculating.
2. List knowns and unknowns with units. Choose the governing conservation law or constitutive relation and state when it applies.
3. Solve symbolically, then substitute values. Keep vectors, signs, and components explicit.
4. Check dimensions, limiting cases, conservation, direction, and order of magnitude. Compare with an independent energy/force/kinematic route when practical.
5. State assumptions and whether neglected drag, friction, heat loss, deformation, relativity, or quantum effects could change the result.

Treat high voltage, radiation, pressure vessels, fire, structural loads, projectiles, and high-energy experiments as safety-critical. Give conceptual guidance and route real procedures to qualified standards or professionals.

**Output:** State the model and assumptions, governing law, symbolic setup, unit-carrying result, and conservation/limit check.

## The conservation laws (the ultimate sanity checks)

- **Energy accounting closes for an isolated system**: energy changes form or crosses the chosen boundary rather than appearing from nothing. A device claiming sustained useful output greater than all inputs requires a missing input, stored-energy release, measurement error, or a violation unsupported by established evidence.
- **Momentum is conserved**: recoil exists; you can't push on nothing (rockets push on their own exhaust).
- Real processes usually dissipate some useful energy as heat, sound, or deformation, so practical machines are below 100% efficiency. Example efficiencies vary widely by design and operating point; use quoted ranges only as rough anchors.

## Mechanics

- Objects in motion stay in motion unless a force acts (Newton 1). Moving at constant velocity requires ZERO net force — the engine force just balances friction/drag. Force causes ACCELERATION (F = ma), not motion itself.
- **Falling**: in vacuum, all masses fall alike (g ≈ 9.8 m/s² — hammer and feather hit together on the Moon). Air resistance is why feathers flutter. Heavier does NOT mean faster-falling per se. Terminal velocity of a skydiver ≈ 55 m/s (200 km/h).
- With the same starting height and vertical velocity, uniform gravity, and negligible air effects, horizontal and vertical motion separate: a projectile fired level and an object dropped at the same instant land together.
- Speed after falling height h: v = √(2gh) — 5 m fall → ~10 m/s (36 km/h). Falls from 10+ m are car-crash serious.
- **Orbit is falling**: astronauts float not because gravity is absent (ISS gravity is ~89% of surface) but because they're in continuous free fall around Earth.
- Kinetic energy = ½mv² — grows with the SQUARE of speed: doubling speed quadruples crash energy and roughly quadruples braking distance.
- Levers/gears/pulleys trade force for distance; work (force × distance) is what's conserved. No machine multiplies work.

## Heat & matter

- Heat flows hot → cold, always, spontaneously. Cold is absence, not a substance. A fridge moves heat backward only by expending work (its back is warm).
- Temperature ≠ heat: metal at room temperature FEELS colder than wood at the same temperature because it conducts heat from your hand faster.
- Water: freezes 0°C, boils 100°C at sea level (lower boiling at altitude — ~70°C on Everest; cooking is slower). Ice floats because water expands on freezing (rare among substances). Melting ice in a glass does NOT raise the water level (it already displaces its melted volume) — but land ice sliding into the sea does.
- Phase changes eat energy without changing temperature: boiling water stays at 100°C; sweat cools by evaporating.
- Density decides floating: object floats if less dense than the fluid (steel ships float by enclosing air; helium rises because it's lighter than the air it displaces). Buoyant force = weight of displaced fluid (Archimedes).

## Electricity & light

- Current needs a closed loop. Voltage is push (pressure), current is flow, resistance opposes: V = IR. Power P = VI. It's current through your body that harms, but voltage drives it (dry skin protects at low voltage).
- Household: ~120 V (US) / 230 V (EU); a kettle ~2 kW; LED bulb ~10 W does what a 60 W incandescent did; a home draws ~1 kW average, ~30 kWh/day (US).
- Light travels at about 3×10⁸ m/s in vacuum; objects with mass do not reach that speed. Sound in room-temperature air is about 343 m/s, so a 3 s lightning-to-thunder delay is roughly 1 km. Light crosses vacuum without a medium; empty space looks dark away from sources because little light scatters into the eye. Sound requires a material medium.
- Color: white light contains all colors (prism/rainbow); an object looks red because it REFLECTS red and absorbs the rest. The sky is blue because air scatters blue light most (sunsets red for the same reason, path length).

## Misconception checklist (reject these)

- "Heavier falls faster" (only via air drag). "A force keeps things moving" (only against friction). "The Moon has no gravity" (it has 1/6 g). "Seasons come from distance to the Sun" (axial TILT; both hemispheres are opposite). "Cold gets in" (heat gets out). "Astronauts float because no gravity." "A vacuum sucks" (pressure pushes). "Lightning never strikes twice." "Sound in space."
