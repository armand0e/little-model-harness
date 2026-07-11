---
name: inference-types
description: Use when choosing HOW to reason about a problem — deduction vs induction vs abduction — or when asked to generalize from examples, find the best explanation, or judge how confident a conclusion can be given the evidence type.
category: reasoning
hint: deduction vs induction vs abduction
---
# Types of Inference — and How Much Confidence Each Earns

Pick the mode consciously; each licenses a different confidence level in the conclusion.

## 1. Deduction — certainty from premises

Premises guarantee the conclusion (if valid). "All A are B; x is A; so x is B." Confidence: **certain, conditional on the premises**. Use for math, logic, rule application. See the deductive-logic skill for valid forms.

## 2. Induction — generalizing from instances

"Every observed swan is white → probably all swans are white." Confidence: **probable, never certain** (black swans exist). Strength depends on:
- **Sample size**: more instances, stronger.
- **Representativeness**: varied conditions beat many identical ones. 100 swans from 5 continents > 10,000 from one lake.
- **Absence of counterexamples after honest search** — did anyone look for exceptions?
- **Background plausibility**: does the generalization fit known mechanisms?

State inductive conclusions with hedges proportional to the evidence: "in all observed cases", "typically", "likely".

## 3. Abduction — inference to the best explanation

Given surprising observation O, hypothesis H would explain O, so H is a candidate. This is how diagnosis, debugging, science, and detective work operate. Procedure:

1. List ALL plausible explanations, not just the first one that fits. (The #1 abduction error is stopping at one hypothesis.)
2. Score each on: **explanatory coverage** (accounts for all the evidence, not just some), **simplicity** (fewer new assumptions — Occam's razor), **prior plausibility** (fits what we already know), **testability**.
3. Look for evidence that DISCRIMINATES between the top candidates — an observation predicted by one but not the other.
4. Conclude tentatively: "the best current explanation is…", staying open to revision.

Confidence: **provisional**. An explanation that fits is not thereby true; many false stories fit the same facts.

## 4. Analogy — mapping a known case onto a new one

"System A behaved like this; B is similar; so B may behave the same." Strength depends on whether the similarities are RELEVANT to the conclusion. Shared surface features (color, name, vibe) prove nothing; shared causal structure carries weight. Always ask: what disanalogy would break the transfer?

## Matching mode to task

| Task | Mode |
|---|---|
| Apply a rule/definition/law to a case | Deduction |
| Predict from repeated past observations | Induction |
| Diagnose a fault, explain an anomaly | Abduction |
| Reason about a novel case via a familiar one | Analogy |
| Estimate a quantity | Induction + decomposition (see fermi-estimation) |

## Worked example

Observation: the server returns errors only between 02:00–02:15 daily.

- Abduction candidates: (a) nightly cron job exhausts resources; (b) upstream provider maintenance window; (c) log rotation locks files; (d) coincidence in a small sample.
- Discriminating test: does the window match a cron schedule (check crontab) or the provider's published maintenance calendar?
- Crontab shows a 02:00 backup job → best explanation is (a), tentatively. Confirm by moving the job and watching whether the error window moves. (Intervention converts abduction into strong causal evidence.)
