---
name: statistics-interpretation
description: Use when interpreting data, averages, polls, studies, charts, "statistically significant" claims, or any statistics in news and reports. Covers mean/median/mode choice, variability, sampling, significance, and how statistics mislead.
---

# Statistics Interpretation

## Reliable workflow

1. Define the estimand: population, outcome, comparison, time window, and whether the target is descriptive, predictive, or causal.
2. Inspect provenance and shape before summarizing: collection process, missingness, exclusions, units, denominator, distribution, outliers, and subgroup composition.
3. Choose summaries and visuals that match the data and question. Report center with spread, counts with rates, and estimates with uncertainty.
4. Check sampling, measurement, multiple testing, model assumptions, attrition, and researcher degrees of freedom.
5. Translate the result into absolute scale and practical effect. Separate statistical evidence from causal interpretation and decision importance.
6. State what the data support, what they do not support, and which limitation could most change the conclusion.

Never infer an individual outcome from a group average, combine groups without weights, or report more precision than the design and sample support.

## Center: mean, median, mode

- **Mean** = sum/count. Sensitive to outliers. One billionaire in a bar makes "average patron wealth" meaningless.
- **Median** = middle value. Robust to outliers — prefer it for skewed data: incomes, house prices, wait times.
- **Mode** = most frequent. Use for categories.
- Cue: if mean ≫ median, the distribution is right-skewed (a few huge values). Ask which one a claim uses — "average" is often chosen to flatter.
- Weighted mean: course grade = Σ(score×weight). Combining group averages requires weighting by group SIZE — the average of averages is wrong when groups differ in size.

## Spread matters as much as center

Two cities with mean 15°C: one ranges 10–20, the other −10 to 40. Always ask for range/standard deviation. In a normal distribution: ~68% within 1 SD of the mean, ~95% within 2 SD, ~99.7% within 3.

## Sampling — where most statistics go wrong

- A sample only informs about the population it was drawn from. Twitter polls describe Twitter users who chose to answer.
- **Bias beats size**: a huge biased sample is worse than a small random one (the 1936 Literary Digest poll: 2.4M responses, dead wrong).
- Watch for: self-selection (volunteers differ), survivorship (only successes visible), convenience samples, leading question wording, non-response bias.
- For a simple random proportion near 50%, an approximate 95% margin of error is `1/√n`: n=1000 gives about ±3 percentage points. Weighting, clustering, nonresponse, wording, and model error can make total uncertainty larger; overlapping margins do not by themselves prove no difference.

## "Statistically significant"

- A p-value is the probability, assuming the null model and other analysis assumptions, of data at least as incompatible with that model as what was observed. It is not the probability that the null is true and does not measure effect size, importance, or proof.
- p < 0.05 will occur by chance ~1 in 20 tests of null effects — many comparisons → some false hits guaranteed (multiple-comparisons problem; cue: study tested many outcomes and reports one).
- Non-significant ≠ no effect; may be an underpowered (too small) study.
- Ask instead: what is the EFFECT SIZE and its confidence interval, and was the study preregistered/replicated?

## How statistics mislead (detection checklist)

- **Truncated y-axis** makes small differences look huge. Check where the axis starts.
- **Relative risk without base rate**: "doubles the risk" of a 1-in-a-million event is 2 in a million. Demand absolute numbers.
- **Percent vs percentage point** confusion (5%→10% is +5 points, +100% relative).
- **Cherry-picked windows**: "sales up 40% since March" — what happened in March?
- **Simpson's paradox**: a trend can hold in every subgroup yet reverse in the aggregate (or vice versa) when group sizes differ. If a comparison mixes groups with different compositions (e.g., admission rates by department), check within-group numbers before concluding.
- **Denominator neglect**: "most accidents happen near home" — because most driving happens near home. Compare RATES, not raw counts.
- **Correlation presented as cause** — route to the causal-reasoning skill.
- **Precision theater**: "37.2% of people…" from a survey of 27 people. Precision should match sample size.

## Worked example

"Hospital A: 900 of 1000 survive (90%). Hospital B: 800 of 1000 survive (80%). So choose A?"

Not yet — check case mix. If A mostly takes mild cases and B takes severe ones, B could be better for BOTH mild and severe patients (Simpson's paradox). Demand survival rates stratified by severity before concluding.
