---
name: combinatorics-and-counting
description: Use for counting questions - "how many ways", arrangements, committees, passwords, handshakes, permutations vs combinations - and the counting stage of probability problems. Provides the decision tree that picks the right formula.
---

# Combinatorics & Counting

## Reliable workflow

1. Define one outcome precisely. State whether objects and positions are distinguishable, whether order matters, whether repetition is allowed, and which constraints apply.
2. Partition the outcome space into disjoint cases, or count a simpler superset and subtract invalid outcomes. Never add overlapping cases without inclusion-exclusion.
3. Build the count from explicit choices. After every multiplication, say what each factor chooses; after every division, say why each outcome was counted that many times.
4. Compute symbolically before evaluating large factorials. Cancel factors early to reduce arithmetic errors.
5. Verify on a tiny instance by listing or brute force, then cross-check with a complement, recurrence, symmetry, or second decomposition when practical.

Return the counting model before the number. If outcomes are not equally likely, do not turn the count directly into a probability.

## The decision tree

Ask two questions about the selection:

1. **Does order matter?** (Is arrangement AB different from BA?)
2. **Is repetition allowed?** (Can the same item be picked twice?)

| | Repetition allowed | No repetition |
|---|---|---|
| **Order matters** | nᵏ (passwords, PINs) | P(n,k) = n!/(n−k)! (rankings, seatings) |
| **Order doesn't matter** | C(n+k−1, k) (scoops of ice cream) | C(n,k) = n!/(k!(n−k)!) (committees, hands) |

Cues: "arrange, order, sequence, schedule, rank, word" → order matters. "Choose, select, committee, group, hand, subset" → order doesn't.

## Core principles

- **Multiplication principle**: independent sequential choices multiply. 4 shirts × 3 pants = 12 outfits.
- **Addition principle**: mutually exclusive alternatives add. Routes via A (3) or via B (2): 5 total.
- **Complement counting**: "at least one X" = total − "no X". Almost always easier.
- **Inclusion–exclusion**: |A or B| = |A| + |B| − |A and B| (subtract the double-counted overlap).

## Facts & formulas

- n! = n·(n−1)·…·1; 0! = 1. Values: 3!=6, 4!=24, 5!=120, 6!=720, 7!=5040, 8!=40320, 10!=3,628,800.
- C(n,k) = C(n,n−k). C(n,0)=1, C(n,1)=n, C(n,2)=n(n−1)/2.
- Handshakes/pairs among n people: C(n,2) = n(n−1)/2. 10 people → 45.
- Arrangements of a word with repeated letters: n! / (repeats!). "LEVEL": 5!/(2!·2!) = 30.
- Circular arrangements of n people: (n−1)! (rotations identical). If reflections also identical: (n−1)!/2.
- Distribute n identical items into k boxes: C(n+k−1, k−1) (stars and bars).
- Subsets of an n-element set: 2ⁿ (each element in or out).

## Standard traps

- **"At least"** by direct addition double-counts — use the complement.
- **Adjacent-together constraints**: glue the pair into one block (count block arrangements × 2 for internal order). "Not together" = total − together.
- **Overcounting unordered picks**: choosing 2 of 5 people sequentially gives 5×4=20, but each pair was counted twice → 10 = C(5,2). If you counted ordered, divide by k!.
- **Mixed constraints**: place the restricted items FIRST (e.g., seats for people who must sit at the ends), then fill the rest.
- Digits problems: leading digit can't be 0; count that position separately.

## Worked example

"A 4-person committee from 6 women and 5 men, needing at least 2 women. How many?"

1. Order doesn't matter, no repetition → combinations.
2. "At least 2 women" → cases: exactly 2, 3, or 4 women.
3. C(6,2)C(5,2) + C(6,3)C(5,1) + C(6,4)C(5,0) = 15·10 + 20·5 + 15·1 = 150+100+15 = **265**.
4. Check by complement: total C(11,4)=330; 0 women: C(5,4)=5; 1 woman: C(6,1)C(5,3)=6·10=60; 330−65=265 ✓.

Two independent methods agreeing = high confidence. Make this your habit for counting problems.
