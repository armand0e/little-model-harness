---
name: problem-decomposition
description: Use at the START of any hard, multi-step, or vague problem - math word problems, planning tasks, debugging, essays, anything that can't be answered in one step. Provides the restate-plan-execute-verify loop that prevents rushed wrong answers.
---

# Problem Decomposition — the Universal Loop

Hard problems fail when attacked whole. The loop: **Restate → Inventory → Plan → Execute stepwise → Verify → Answer.** Skipping straight to an answer is the #1 cause of errors.

## Reliable workflow

Maintain a compact work state:

```text
Goal:
Deliverable and constraints:
Known / observed:
Unknown / assumed:
Plan:
Checks:
```

Break the task into chunks that each produce a checkable artifact or decision. Complete and verify one dependency before using it downstream. If two attempts fail for the same reason, change the representation, isolate a smaller case, or seek missing evidence instead of repeating the attempt. Keep the internal plan detailed enough to prevent omissions, but return only the reasoning needed to make the result understandable and auditable.

1. Fill the work state from the request and available evidence.
2. Order chunks by dependency and risk; mark the next concrete action.
3. Execute and verify each chunk before consuming its result downstream.
4. Reconcile the final artifact with every deliverable and constraint.

**Output:** Lead with the completed result, then the minimum evidence, assumptions, and unresolved blocker needed to use it.

## 1. Restate

Rewrite the problem in your own words, in one or two sentences. Name the exact deliverable: a number? a yes/no? a name? a plan? If you can't restate it, you don't understand it yet — re-read.

Explicitly note: what is ASKED (many errors answer a neighboring question — e.g., computing the price when asked for the discount, or Alice's age when asked for Bob's).

## 2. Inventory

List what you're given (quantities, constraints, facts) and what's unknown. Assign symbols to unknowns. Note units. Flag information that looks irrelevant — puzzles include distractors, but confirm irrelevance rather than assuming it.

## 3. Plan

Choose a strategy BEFORE computing:
- **Work forward** from givens when the path is clear.
- **Work backward** from the goal when it's not ("to find X I need Y; to find Y I need Z; I have Z").
- **Split into cases** when a condition branches (even/odd, rain/no rain).
- **Solve a simpler version first** (smaller numbers, 2 items instead of 100) to find the pattern, then scale.
- **Draw the situation** — a table, timeline, or diagram — whenever entities relate to each other.
- **Try small examples** and look for the pattern when the problem says "for any n".

Write the plan as numbered steps. Each step should be small enough to do without error.

## 4. Execute one step at a time

Do the steps in order. Show intermediate results. Never combine three operations into one line "to save time" — that's where arithmetic slips hide. Carry units through every calculation (see unit-conversion skill).

If a step fails or produces something absurd, STOP and revisit the plan — don't push a broken path harder.

## 5. Verify (non-negotiable)

- **Substitute back**: does the answer satisfy the original conditions?
- **Sanity scale**: is the magnitude plausible? (A car speed of 400 mph, a person's age of 200, a probability of 1.4 → error.)
- **Units**: does the answer carry the unit the question asked for?
- **Recompute differently**: check by an independent route if cheap (estimate first, exact second).
- **Re-read the question one last time**: am I answering what was asked, in the asked format?

## 6. Answer

State the final answer plainly and first, then supporting work if useful. If the problem was ambiguous, state the interpretation you chose.

## Worked example

"A shirt costs $40 after a 20% discount. What was the original price?"

1. Restate: find pre-discount price P such that P minus 20% of P equals 40.
2. Inventory: final=40, discount=20%, unknown P.
3. Plan: 0.8·P = 40 → P = 40/0.8.
4. Execute: P = 50.
5. Verify: 20% of 50 = 10; 50−10 = 40 ✓. Trap avoided: the naive answer 40×1.2 = 48 fails verification (48−9.6=38.4≠40) — percentages don't invert by adding back.
6. Answer: **$50**.
