---
name: answer-verification
description: Use BEFORE giving any final answer to a math, logic, factual, or code question - a fast checklist that catches most wrong answers. Especially when the problem had multiple steps, numbers, negations, or units.
category: reasoning
hint: check answers before finalizing
---
# Answer Verification — Catch Your Own Errors

Most wrong answers are detectably wrong with 30 seconds of checking. Run this before finalizing.

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
- **Facts/dates**: is the claim consistent with anchor facts I'm confident of? (See fact-anchors skills.) If two things I believe conflict, flag uncertainty rather than asserting either.

## When a check fails

Do not patch the final number to pass the check. Return to the earliest suspicious step and redo forward from there — the error usually lives earlier than it appears, and a patched answer with broken work is still wrong.

## When to say "not determinable"

If verification shows two different answers both satisfy all constraints, the honest answer is "cannot be determined from the given information" — that IS the correct answer to some questions, and stating it beats guessing.
