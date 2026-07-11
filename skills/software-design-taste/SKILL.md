---
name: software-design-taste
description: Use when designing or reviewing code structure - modules, abstractions, naming, when to refactor, how much flexibility to build - or when asked "how should I structure this?". Encodes the taste of a senior engineer - simplicity first, abstractions earned not speculated.
category: software
hint: judgment for clean architecture
---
# Software Design Taste

The dominant cost of software is READING and CHANGING it, not writing it. Every design choice is judged by: how hard does this make the next change, for someone who isn't you?

## The prime directives

1. **Solve the problem you have.** Not the general version, not the imagined future version. Speculative flexibility (extra config, plugin systems, abstract base classes with one subclass) is a cost paid now for a benefit that usually never comes — and the future need, when it arrives, is usually shaped differently than you guessed (YAGNI).
2. **Duplication is cheaper than the wrong abstraction.** Copy code twice; on the THIRD occurrence, when you can see what actually varies, extract the abstraction around that real axis of variation. An abstraction extracted too early, around the wrong axis, forces every future change through a lie — undoing it costs more than the duplication ever did.
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

Comments explain WHY — the constraint, the non-obvious reason, the workaround's cause — never WHAT the next line does (the code says that) and never the change history (version control says that). If you need a comment to explain what code does, first try rewriting the code to not need it.

## When reviewing/refactoring

- The best code is no code: first ask if the feature/branch/flag can be deleted or an existing utility reused.
- Leave the campsite cleaner, but in SEPARATE commits from behavior changes: a diff should be either "refactor, no behavior change" or "behavior change, minimal diff" — never an ambiguous mix.
- A design is good when the common change requests touch one place each. If every feature touches five files, the boundaries are wrong.
