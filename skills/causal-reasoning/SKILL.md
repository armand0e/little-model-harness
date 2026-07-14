---
name: causal-reasoning
description: Use when a question asks whether X causes Y, interprets a study or statistic, evaluates "linked to / associated with" claims, or asks why something happened. Provides the correlation-vs-causation toolkit, confounders, and study-quality checks.
---

# Causal Reasoning

## Reliable workflow

1. Define the proposed cause, outcome, population, comparison, and time window. Replace vague claims such as "X affects Y" with an intervention-like statement: "changing X from A to B changes Y by how much, for whom, and when?"
2. Draw a small causal map containing X, Y, plausible common causes, selection variables, and mediators. Do not control for a mediator or collider merely because it is available.
3. Identify the study design and the comparison it actually supports. Check temporality, assignment, attrition, measurement, and whether groups were comparable before exposure.
4. Report effect size, absolute scale, uncertainty, and population limits before discussing mechanism.
5. Try to explain the result using reverse causation, confounding, selection, measurement error, and chance. State which alternatives the design rules out and which remain.
6. Conclude using an evidence-calibrated verb: `caused`, `probably contributed`, `is associated`, or `is not distinguishable from noise`.

Do not infer individual causation from a population average, or transport a result to a different population without arguing why the mechanism and conditions carry over.

Correlation between X and Y has FIVE standard explanations. Before accepting "X causes Y", walk all five:

1. **X causes Y** (the claim).
2. **Y causes X** (reverse causation). "Depressed people exercise less" — does low exercise cause depression, or depression reduce exercise?
3. **Z causes both** (confounder). Ice cream sales correlate with drownings — summer causes both.
4. **Selection effect** — the sample was chosen in a way that creates the pattern. Hospitals contain sicker people; comparing "people who chose X" bakes in whatever made them choose it.
5. **Coincidence / noise** — with many variables, some correlate by chance. Small samples make this worse.

## Evidence quality ladder (typical, weakest → strongest)

1. Anecdote / testimonial
2. Case series (no comparison group)
3. Cross-sectional correlation ("people who X also Y")
4. Longitudinal / cohort study (X measured before Y — rules out some reverse causation)
5. Natural experiment / instrumental variable
6. **Randomized controlled trial (RCT)** — randomization breaks confounding, because groups differ only by chance
7. Systematic review or meta-analysis of multiple relevant, high-quality RCTs

The ladder is not automatic: a biased RCT can be weaker than a careful natural experiment, and a meta-analysis inherits the quality and comparability of its studies. Headlines saying "linked to", "associated with", or "tied to" usually describe correlation. Randomized assignment or a well-defended causal design is needed to earn "causes."

## Questions to ask about any study claim

- Was there a **control group**? Compared to what?
- **Who was studied** and how many? (n=12 college students ≠ everyone.)
- Was assignment **randomized**? If not, what confounders differ between groups?
- Is the effect size meaningful, or just "statistically significant"? ("Doubles your risk" of something with base rate 1 in a million → 2 in a million.)
- **Relative vs absolute risk**: "50% increase" from 2% to 3% is 1 percentage point.
- Could **regression to the mean** explain it? (Treatments started at symptom peaks look effective as symptoms naturally recede.)
- **Publication/survivorship bias**: are we only seeing the studies/cases that showed something?

## Mechanism + counterfactual test

A causal claim is strong when you can state: (a) a plausible mechanism (HOW X produces Y), and (b) the counterfactual (if X hadn't happened, Y probably wouldn't have, other things equal). "The match caused the fire" — mechanism: ignition; counterfactual: no match, no fire. Note: causes are usually contributing, not sole — oxygen was also necessary, but the match is the salient difference-maker.

## Everyday diagnosis procedure (why did this happen?)

1. Define the effect precisely (what changed, when, where).
2. List candidate causes; for each, check timing (cause must precede effect), covariation (does effect track cause?), and mechanism.
3. Look for what changed right before onset — but beware post hoc (sequence alone isn't proof).
4. If possible, intervene: remove/restore the candidate cause and observe. Change ONE variable at a time.
5. Prefer the explanation that accounts for ALL observations with fewest assumptions (Occam), but don't force a single cause on a multi-cause event.

## Worked example

Claim: "Kids who play violent games are more aggressive, so games cause aggression."

- Reverse: aggressive kids may seek violent games. Plausible.
- Confounder: household environment, age, sex could drive both. Plausible.
- Design: cross-sectional correlation — level 3 evidence.
- Verdict: the data are consistent with causation but far from establishing it; an RCT or longitudinal design controlling for prior aggression is needed. Say "the study shows an association; causation is not established."
