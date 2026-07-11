---
name: algebra-word-problems
description: Use for math word problems requiring equations - ages, coins, consecutive numbers, two-variable systems, quadratics, and "translate English to algebra" tasks. Provides the translation table and setup patterns that prevent wrong equations.
category: math
hint: turn word problems into equations
---
# Algebra Word Problems

The hard part is the SETUP, not the solving. A correct equation nearly solves itself; a wrong one is unrecoverable.

## English → algebra translation table

| English | Algebra |
|---|---|
| "5 more than x" | x + 5 |
| "5 less than x" | x − 5 (order flips! not 5 − x) |
| "twice x" / "x doubled" | 2x |
| "half of x" | x/2 |
| "3 less than twice x" | 2x − 3 |
| "the sum/difference/product/quotient of a and b" | a+b / a−b / ab / a/b |
| "is / was / will be / equals / gives" | = |
| "x exceeds y by 7" | x = y + 7 |
| "x is 3 times as large as y" | x = 3y (the LARGER gets the plain variable) |
| "consecutive integers" | n, n+1, n+2 |
| "consecutive even/odd" | n, n+2, n+4 |
| "a two-digit number with tens digit t, units u" | 10t + u |
| "the number reversed" | 10u + t |

## Setup discipline

1. Define each variable IN WORDS with units: "let x = Sara's age now, in years." Ambiguous variables cause equations about the wrong moment or person.
2. One equation per stated fact. Count: unknowns should equal independent equations.
3. Before solving, test the equation with a made-up plausible number — does it express the sentence?

## Standard templates

- **Age problems**: ages shift together. "In 5 years, Ann will be twice Ben's age": A+5 = 2(B+5) — add the years to BOTH people. "3 years ago" subtracts from both. Age differences stay constant forever; ratios change.
- **Coins/tickets**: two equations — count and value. n_q + n_d = 30 and 25·n_q + 10·n_d = 480 (work in cents to avoid decimals).
- **Sum & difference**: x+y = S, x−y = D → x = (S+D)/2, y = (S−D)/2.
- **Perimeter/area**: translate "length is 3 more than twice the width" then use the geometry formula.
- **Number digits**: use the 10t+u form; "digits sum to 9" → t+u = 9.

## Solving reminders

- Whatever you do to one side, do to the whole other side. Distribute minus signs across parentheses fully: −(2x − 5) = −2x + 5.
- Multiplying/dividing an inequality by a negative FLIPS the sign.
- Quadratics: try factoring (find p·q = c, p+q = b for x²+bx+c); else x = (−b ± √(b²−4ac)) / (2a). Two roots — check both against the story (a negative length or age is rejected, but say why).
- Squaring both sides or multiplying by an expression containing x can create extraneous roots — verify every solution in the ORIGINAL equation.
- Systems: substitution when one variable is isolated; elimination when coefficients align. Check the solution in BOTH equations.

## Worked example

"A two-digit number's digits sum to 11. Reversing the digits increases the number by 27. Find it."

1. Let t = tens digit, u = units digit. Number = 10t+u.
2. Facts: t+u = 11; (10u+t) = (10t+u) + 27.
3. Second: 9u − 9t = 27 → u − t = 3. With t+u=11: u = 7, t = 4.
4. Number = 47. Verify: 4+7=11 ✓; 74−47 = 27 ✓. Answer: **47**.
