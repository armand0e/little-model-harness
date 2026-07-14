---
name: answer-verification
description: Use to audit a draft answer when correctness matters, especially after multi-step math, logic, factual research, data interpretation, or code work involving numbers, negations, units, or external claims. Provides independent checks, failure handling, and a clear verified-versus-unverified report.
---

# Answer Verification — Catch Your Own Errors

Most wrong answers are detectably wrong with 30 seconds of checking. Run this before finalizing.

## Reliable workflow

1. Split the draft into checkable claims: final conclusion, intermediate calculations, factual premises, and scope/format requirements.
2. Assign each claim a check that does not merely repeat the original reasoning: substitution, inverse operation, alternate derivation, executable test, primary source, counterexample search, or dimensional bound.
3. Check the highest-impact and least-certain claims first. Increase effort for irreversible, financial, medical, legal, security, or public-facing decisions.
4. Record each material claim as `verified`, `contradicted`, or `not verified`. Never convert `not verified` into `verified` because the claim sounds plausible.
5. If a check fails, return to the earliest unsupported step, correct the reasoning, and rerun all downstream checks.

In the final response, distinguish what was actually verified from what remains assumed or untested. Do not expose a long verification diary unless it helps the reader assess the result.

## The five universal checks

1. **Re-read the question.** Am I answering the exact thing asked? Common misses: asked for the DIFFERENCE but gave a total; asked "how many do NOT" but counted those that do; asked for units/format (percent vs fraction, feet vs meters); asked which option is FALSE and picked a true one; asked for Bob's value and computed Alice's.
2. **Substitute back.** Plug the answer into the original constraints. An equation solution must satisfy the equation; a puzzle answer must satisfy every clue; a schedule must respect every restriction.
3. **Sanity of magnitude.** Compare against a rough estimate done a different way. Ages 0–120, probabilities 0–1, percentages of a whole ≤ 100, a part smaller than its whole, speeds/costs/counts within real-world plausibility.
4. **Recompute the arithmetic independently** — different order or method. 17×23: (17×20)+(17×3)=340+51=391; check by (20−3)(20+3)=400−9=391 ✓. Check subtraction by adding back; division by multiplying back.
5. **Edge cases.** Does my reasoning still hold for zero, one, negative, empty, equal values, or the boundary itself? "Between 3 and 7" — inclusive or exclusive? Off-by-one is the classic: fenceposts (a fence of 10 sections has 11 posts), days between dates, inclusive counting (pages 12–20 is 9 pages, not 8).

## Domain-specific quick checks

- **Algebra**: solutions can be extraneous (introduced by squaring or multiplying by an expression that could be zero) — verify each candidate in the ORIGINAL equation, and check denominators ≠ 0, radicands ≥ 0.
- **Geometry**: triangle sides must satisfy the triangle inequality; angles of a triangle sum to 180°; areas can't be negative; a diagram drawn to scale exposes absurd answers.
- **Probability**: result in [0,1]; complementary events sum to 1; "at least one" computed via complement.
- **Percentages**: a 50% drop then 50% rise does NOT return to start (100→50→75). Sequential percentages multiply, never add.
- **Logic**: hunt for one counterexample to your conclusion; if found, the conclusion is wrong regardless of how sound the derivation felt.
- **Counting**: did I double-count (subtract the overlap) or miss the empty/identity case? Try the count by brute force on a tiny version (n=3) and compare with the formula.
- **Code**: trace the code by hand on one small input; check the empty input, single element, and boundary index; confirm loop bounds (< vs ≤) and integer division/rounding direction.
- **Facts/dates**: is the claim consistent with high-confidence anchors? (See `world-knowledge-anchors`.) For current or precise facts, verify against an authoritative source rather than relying on the anchor alone.

## When a check fails

Do not patch the final number to pass the check. Return to the earliest suspicious step and redo forward from there — the error usually lives earlier than it appears, and a patched answer with broken work is still wrong.

## When to say "not determinable"

If verification shows two different answers both satisfy all constraints, the honest answer is "cannot be determined from the given information" — that IS the correct answer to some questions, and stating it beats guessing.
