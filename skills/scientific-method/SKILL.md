---
name: scientific-method
description: Use when designing an experiment or A/B test, evaluating whether a claim is scientifically supported, distinguishing science from pseudoscience, or testing any hypothesis rigorously (in research, product, or daily life).
category: reasoning
hint: hypotheses, experiments, evidence
---
# Scientific Method

Science is not a body of facts; it's the error-correcting procedure: guess → derive what the guess PREDICTS → test the prediction against reality → keep, revise, or discard the guess. The genius is in trying to prove yourself wrong.

## Designing a real test

1. **State the hypothesis falsifiably**: it must forbid something. "This fertilizer increases tomato yield by >10%" is testable; "this fertilizer harmonizes plant energy" forbids nothing and is not science.
2. **Derive a specific prediction** BEFORE collecting data (prediction, not postdiction — anything can be "explained" after the fact).
3. **Control group**: identical in every way except the one manipulated variable. No control = no conclusion (maybe everything grew this year).
4. **Randomize assignment** to conditions — randomization is what severs confounders (see causal-reasoning).
5. **Blind** where humans judge or receive: subjects blind to condition (placebo effect is real and strong), assessors blind to condition (expectation shapes measurement). Double-blind = both.
6. **Decide sample size and success criteria in advance.** Peeking at results and stopping when they look good manufactures false positives; so does testing 20 outcomes and reporting the one that "worked" (p-hacking).
7. **One variable at a time** — or a properly designed factorial; never casually vary two things.

## Evaluating a claimed finding

- Effect size and confidence interval, not just "significant" (see statistics-interpretation).
- **Replication is the gold standard.** One study is a hint. Independent replication by other groups is evidence. A field's flashiest single-study results often fail replication.
- Sample: size, selection, who dropped out (attrition can fake effects).
- Conflicts of interest and publication bias: who funded it? Would a null result have been published?
- **Extraordinary claims require extraordinary evidence**: a result contradicting a mountain of prior evidence (e.g., physics-defying devices) is more likely a methods error than a revolution. Prior probability matters.
- Mechanism: is there a plausible pathway, or does the effect require unknown forces?

## Pseudoscience tells

- Claims are unfalsifiable or retreat when tested ("the skeptics' negative energy blocked it").
- Evidence is testimonials and anecdotes, never controlled trials.
- No self-correction: the theory hasn't changed in decades despite failed predictions; failures are explained away, never counted.
- Persecution narrative substitutes for data ("Big X is suppressing this"). Galileo is invoked. (They laughed at Galileo, but they also laughed at countless cranks; being laughed at is not evidence.)
- Jargon borrowed from physics ("quantum", "energy field", "frequencies") without the math.
- Sells something.

## The practitioner's loop (works for product, cooking, workouts, code perf)

Baseline measurement → one change → same measurement → compare against normal variation → log it. Without the baseline and the log, you are collecting anecdotes about yourself. Regression to the mean will fool you: you try remedies when things are at their worst, and things at their worst usually improve on their own — that's WHY controls exist.

## Honest reporting

Report what would make the conclusion wrong, not just what supports it. Negative results are results. "We found no effect (n=40, powered to detect >15% changes)" is a contribution; hiding it is how fields fill with false positives.
