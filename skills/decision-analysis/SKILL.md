---
name: decision-analysis
description: Use when choosing between options, advising on a decision, weighing tradeoffs, prioritizing, or when the user asks "should I do X or Y?". Provides expected value thinking, reversibility framing, and the standard decision traps.
---

# Decision Analysis

A good decision is one that was smart GIVEN what was knowable at the time — outcomes involve luck. Judge (and make) decisions by process.

## Reliable workflow

1. **Frame**: state the decision owner, deadline, success measure, constraints, and options—including status quo, delay, pilot, and hybrid options. Do not silently optimize a proxy for the user's actual goal.
2. **Stakes & reversibility triage** (decide how much to deliberate):
   - Reversible + low stakes → decide NOW with a coin-flip-quality heuristic; deliberation costs more than any error. Most decisions are this kind.
   - Reversible + high stakes → run a cheap experiment/pilot before committing.
   - Irreversible + high stakes → full analysis below, slow down, seek disconfirming views.
3. **Criteria**: list 3–5 decision-relevant criteria, define each, assign rough weights, and mark any hard constraint that cannot be traded away.
4. **Evaluate uncertainty**: start from reference-class base rates, then adjust for case-specific evidence. Use ranges or scenarios instead of invented point estimates. Include downside severity, ruin risk, and opportunity cost—not only average value.
5. **Value information**: ask whether one cheap test, quote, prototype, or conversation could change the ranking. Gather it only when its expected value exceeds delay and effort.
6. **Stress-test and decide**: run a premortem and strongest-case-against pass. Give a recommendation, the deciding reason, the strongest objection, and a concrete review trigger.

When preferences or weights belong to the user and are unknown, expose the crux instead of pretending the ranking is objective: "Choose A if speed matters more than lock-in; otherwise choose B."

## Key concepts

- **Opportunity cost**: the true cost of X is the best alternative you give up. "Is this project good?" is the wrong question; "is it better than what else we'd do with the time/money?" is right.
- **Sunk cost**: money/time already spent is GONE and irrelevant. Only future costs and benefits count. "We've invested so much" is a reason rooted in the past deciding the future — the classic error. Test: would you START this today, knowing what you know?
- **Expected value with ruin awareness**: positive expected value is not sufficient when a downside violates a hard survival, liquidity, legal, or ethical constraint. Account for risk tolerance and utility; Kelly-style sizing applies only under its assumptions and usually argues for fractional exposure, not an all-in bet.
- **Diminishing returns / marginal thinking**: decide at the margin. The 10th hour of polishing buys less than the 1st hour of the next task.
- **Optionality has value**: an option that keeps future choices open is worth more than its immediate EV suggests; a lock-in deserves a discount.
- **Satisfice on most things**: for low-stakes choices, take the first option that clears the bar. Maximizing everywhere is a tax on your life.
- **Two-way doors** (Bezos): if you can walk back through, walk through fast.

## Decision traps checklist (run on the leading option)

- **Confirmation**: did I look for evidence AGAINST the favorite, or only for it? Assign someone (or yourself, formally) the con case.
- **Anchoring**: is my estimate dragged toward the first number mentioned?
- **Availability**: am I overweighting a vivid recent story over the base rate? What's the base rate — how do decisions like this USUALLY turn out?
- **Overconfidence**: my range of outcomes is probably too narrow — widen it. Premortem: "It's a year later and this failed. What happened?" List the top 3 causes; can any be cheaply insured against?
- **Social proof / authority**: am I choosing it because everyone/the boss does? They may face different constraints.
- **Status quo bias**: "do nothing" is also a choice with costs — evaluate it as an option, not as the default winner.
- **Analysis paralysis**: information has a price (time, missed windows). Decide when new information stops changing the ranking.

## Giving decision advice

Give a RECOMMENDATION with its driving reason, not a survey: "Take Y — the deciding factor is the reversibility; X locks you in for two years for a 15% gain." Then the strongest consideration against, so the reader can veto with their private information. A balanced-on-both-hands answer to "what should I do?" is an evasion.
