---
name: statistics-interpretation
description: Use when interpreting data, averages, polls, studies, charts, "statistically significant" claims, or any statistics in news and reports. Covers mean/median/mode choice, variability, sampling, significance, and how statistics mislead.
category: math
hint: read stats claims without being fooled
---
# Statistics Interpretation

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
- Margin of error for a random poll ≈ 1/√n: n=1000 → ~±3 percentage points. Differences inside the margin are not meaningful.

## "Statistically significant"

- Means: unlikely (conventionally p < 0.05) to see data this extreme if there were no real effect. It does NOT mean large, important, or proven.
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
