---
name: decision-analysis
description: Use when choosing between options, advising on a decision, weighing tradeoffs, prioritizing, or when the user asks "should I do X or Y?". Provides expected value thinking, reversibility framing, and the standard decision traps.
category: reasoning
hint: structure choices, weigh options
---
# Decision Analysis

A good decision is one that was smart GIVEN what was knowable at the time — outcomes involve luck. Judge (and make) decisions by process.

## The core procedure

1. **Frame**: what's actually being decided, by when, and what does success look like? Check the option list isn't artificially narrow — "X or Y?" often has better answers Z (do both partially, do neither, get more info first, renegotiate the constraint).
2. **Stakes & reversibility triage** (decide how much to deliberate):
   - Reversible + low stakes → decide NOW with a coin-flip-quality heuristic; deliberation costs more than any error. Most decisions are this kind.
   - Reversible + high stakes → run a cheap experiment/pilot before committing.
   - Irreversible + high stakes → full analysis below, slow down, seek disconfirming views.
3. **Criteria**: list what matters and roughly weight it. 3–5 criteria; more means you haven't decided what matters.
4. **Evaluate**: score options against criteria. For uncertain outcomes, think expected value: EV = Σ p(outcome)·value(outcome) — see probabilistic-reasoning. For unquantifiable factors, still rank them; "can't quantify" doesn't mean "ignore."
5. **Stress-test the leader** (see traps below), then decide, record WHY (one paragraph — future you will want it), and set a review trigger ("revisit if churn exceeds 5%").

## Key concepts

- **Opportunity cost**: the true cost of X is the best alternative you give up. "Is this project good?" is the wrong question; "is it better than what else we'd do with the time/money?" is right.
- **Sunk cost**: money/time already spent is GONE and irrelevant. Only future costs and benefits count. "We've invested so much" is a reason rooted in the past deciding the future — the classic error. Test: would you START this today, knowing what you know?
- **Expected value with ruin awareness**: positive-EV bets are good ONLY if you survive the downside. A 90% chance to double the company + 10% chance of bankruptcy is usually a bad bet — you can't average over ruin. Kelly logic: bet fractions, never everything.
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
