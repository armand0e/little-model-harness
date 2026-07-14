---
name: probabilistic-reasoning
description: Use for any question involving probability, chance, likelihood, uncertainty, medical-test accuracy, false positives, gambling odds, Bayes' rule, expected value, or "what are the chances". Provides formulas, the natural-frequency method, and the classic traps.
---

# Probabilistic Reasoning

## Reliable workflow

1. Define the events, population, time horizon, and conditioning information. Rewrite `given`, `at least`, `exactly`, `either`, and `both` in event notation.
2. Draw a tree, 2×2 table, or natural-frequency table before choosing a formula. Mark which branches are conditional.
3. Test independence rather than assuming it. If learning A changes the chance of B, use conditional probability.
4. Calculate with unrounded values, then check bounds, complements, and whether component probabilities sum correctly.
5. Compare the result with a base-rate estimate or simulation on a small case. Explain any counterintuitive result through the denominator or conditioning set.
6. Report the probability, assumptions, and sensitivity to the most uncertain input. Distinguish aleatory uncertainty from missing knowledge when it matters.

Never assign exact probabilities without a model, data, or explicit subjective assumptions. For one-off high-stakes choices, report downside and uncertainty as well as expected value.

## Core rules

- Probabilities are between 0 and 1. P(not A) = 1 − P(A).
- **AND (independent)**: P(A and B) = P(A) × P(B). Only when independent!
- **AND (general)**: P(A and B) = P(A) × P(B given A).
- **OR (mutually exclusive)**: P(A or B) = P(A) + P(B).
- **OR (general)**: P(A or B) = P(A) + P(B) − P(A and B).
- **At least one** in n independent tries: 1 − P(none) = 1 − (1−p)ⁿ. Never add p n times (that can exceed 1).
- Odds of a:b means probability a/(a+b). "3 to 1 against" = probability 1/4.

## Bayes via natural frequencies (the reliable method)

For "test/evidence accuracy" problems, DON'T plug into the formula — convert to counts of 10,000 people. Errors nearly vanish this way.

**Example**: Disease affects 1% of people. Test catches 90% of sick people (sensitivity); 5% of healthy people test positive (false-positive rate). You test positive. P(sick)?

1. Imagine 10,000 people.
2. Sick: 1% → 100. Healthy: 9,900.
3. Sick AND positive: 90% of 100 = 90.
4. Healthy AND positive: 5% of 9,900 = 495.
5. Total positives: 90 + 495 = 585.
6. P(sick | positive) = 90 / 585 ≈ **15.4%** — not 90%!

The lesson: **when the condition is rare, most positives are false positives.** Always start from the base rate.

Formula form: P(H|E) = P(E|H)·P(H) / [P(E|H)·P(H) + P(E|¬H)·P(¬H)].

## Expected value

EV = Σ (outcome value × its probability). A $10 bet winning $50 with probability 0.15: EV = 0.15×50 − 10 = −$2.50. Negative EV repeated many times loses money. Compare options by EV, but note variance matters when you can't repeat (ruin risk).

## Classic traps

- **Gambler's fallacy**: independent events have no memory. After 5 heads, P(heads) is still 1/2. Past flips don't "owe" a tails.
- **Hot hand vs regression**: extreme streaks tend to be followed by more average results (regression to the mean) — not because of a compensating force, but because the extreme was partly luck.
- **Conjunction fallacy**: P(A and B) ≤ P(A), always. "Linda is a feminist bank teller" can't be more likely than "Linda is a bank teller."
- **Base rate neglect**: vivid evidence (a positive test, a matching description) doesn't override how rare the category is.
- **Inverse confusion**: P(A|B) ≠ P(B|A). P(rain|clouds) ≠ P(clouds|rain).
- **Ignoring selection**: "Every survey respondent loved it" — who chose to respond?
- **Monty Hall**: 3 doors, host knowingly opens a goat door, switching wins 2/3. The host's knowledge concentrates probability on the remaining door.
- **Birthday problem**: 23 people → >50% chance two share a birthday. Pairs grow as n(n−1)/2, so collisions come fast.

## Combinatoric probability quick method

P = (favorable outcomes) / (total equally-likely outcomes). Count both with the combinatorics-and-counting skill. For "at least one" questions, count the complement ("none") — it's almost always easier.

## Self-check

- Does my probability lie in [0,1]? Did percentages that should sum to 100 do so?
- Did I multiply probabilities of events that aren't independent?
- For evidence/test questions: did I start from the base rate and use the 10,000-people table?
- For "at least one": did I use 1 − (1−p)ⁿ instead of adding?
- Sanity-check against intuition: if the disease is rare and the test imperfect, a positive should NOT mean near-certainty.
