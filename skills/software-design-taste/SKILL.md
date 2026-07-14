---
name: software-design-taste
description: Use when designing or reviewing code structure - modules, abstractions, naming, when to refactor, how much flexibility to build - or when asked "how should I structure this?". Encodes the taste of a senior engineer - simplicity first, abstractions earned not speculated.
---

# Software Design Taste

The dominant cost of software is READING and CHANGING it, not writing it. Every design choice is judged by: how hard does this make the next change, for someone who isn't you?

## Reliable workflow

1. Name the concrete behavior and the next 2–3 plausible change scenarios. Do not design for an unnamed future.
2. Map the current boundaries, data ownership, dependencies, and failure paths. Prefer the existing codebase's vocabulary and seams.
3. Sketch the simplest design that satisfies today's invariant. State where it is intentionally rigid and what evidence would justify another abstraction.
4. Walk one normal request, one failure, and one change scenario through the design. Count coordination points, state transitions, and places that must change together.
5. Compare alternatives on complexity, coupling, operability, testability, migration cost, and reversibility—not elegance alone.
6. Record the decision and rejected alternatives briefly. Validate with code or a thin vertical slice when uncertainty is implementation-shaped.

Prefer designs whose invariants are enforced at one boundary and whose common changes touch one obvious owner.

**Output:** Give the recommended structure, invariants and ownership, request/failure walkthrough, rejected alternative, migration path if needed, and evidence that would trigger redesign.

## The prime directives

1. **Solve the problem you have.** Not the general version, not the imagined future version. Speculative flexibility (extra config, plugin systems, abstract base classes with one subclass) is a cost paid now for a benefit that usually never comes — and the future need, when it arrives, is usually shaped differently than you guessed (YAGNI).
2. **Duplication is often cheaper than the wrong abstraction.** A third occurrence is a useful prompt—not a law—to inspect what truly varies and extract only around that demonstrated axis. An abstraction extracted too early, around the wrong axis, forces every future change through a lie.
3. **Make it work, make it right, make it fast — in that order.** Optimize only what a measurement shows is slow. But don't write gratuitously wasteful code either: use the obvious right data structure from the start (a set for membership, a dict for lookup).
4. **Match the codebase.** Consistency with surrounding style, idioms, and structure beats your personal preference. A locally-perfect patch in a foreign style makes the whole file worse.

## Naming — the highest-leverage skill

- A name should say what the thing IS or DOES, at the caller's level of abstraction: `retry_delay_seconds`, not `x`, not `temporalBackoffParameterValue`.
- Booleans read as assertions: `is_valid`, `has_expired`. Functions with side effects are verbs (`send_invoice`); pure queries are nouns/getters (`total_price`).
- If you can't name it crisply, the design is wrong — a function needing a name like `validate_and_save_and_notify` is three functions.
- Same concept, same word everywhere (don't alternate fetch/get/retrieve for one operation); different concepts, visibly different words.

## Functions and modules

- A function does one thing at one level of abstraction; its body reads like steps of that one thing. Mixed altitude (three lines of business logic, then twelve lines of byte-fiddling) means extract the low-level part.
- Short is a symptom of good decomposition, not a goal — never chop a coherent 30-line function into 6 fragments that must be read together anyway.
- Depend on interfaces narrower than the implementation: take the specific values you need, not a grab-bag object. Deep modules (simple interface, substantial implementation) beat shallow ones (interface as complex as what it hides).
- Isolate I/O and side effects at the edges; keep the core logic pure and testable.

## State and errors

- Minimize mutable state; the bugs live where state changes. Prefer values in, values out.
- Make illegal states unrepresentable where cheap (an enum instead of a magic string; a type that can't hold a negative quantity).
- Fail fast and loud on programmer errors (bad arguments → raise immediately); handle expected external failures (network, user input) explicitly at the boundary. Never swallow an exception silently — the empty catch block is where debugging goes to die.

## Comments

Prefer comments that preserve a non-obvious reason, invariant, protocol detail, or workaround cause. Avoid narrating obvious syntax or duplicating change history; when code is difficult to understand, first improve its names and structure, but retain explanatory comments where the representation cannot be made self-evident.

## When reviewing/refactoring

- The best code is no code: first ask if the feature/branch/flag can be deleted or an existing utility reused.
- Leave the campsite cleaner, but in SEPARATE commits from behavior changes: a diff should be either "refactor, no behavior change" or "behavior change, minimal diff" — never an ambiguous mix.
- A design is good when the common change requests touch one place each. If every feature touches five files, the boundaries are wrong.
