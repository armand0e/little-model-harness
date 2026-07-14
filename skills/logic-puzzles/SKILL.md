---
name: logic-puzzles
description: Use for constraint puzzles - knights and knaves, truth-tellers and liars, grid/zebra puzzles ("who owns the fish"), seating arrangements, river crossings, weighing/balance puzzles, and lateral logic riddles. Provides systematic methods that avoid guesswork.
---

# Logic Puzzle Methods

Never solve by intuition or by "trying an answer that feels right." Every puzzle type below has a mechanical method. Write down state; do not hold it in your head.

## Reliable workflow

1. Define variables and their possible values. Number every clue and translate each into an explicit constraint.
2. Propagate forced consequences before guessing. Keep candidate sets visible; after fixing a value, remove it everywhere the puzzle requires uniqueness.
3. When stuck, branch on the variable with the fewest remaining values. Copy the state, assume one value, and stop the branch immediately on contradiction.
4. Preserve every surviving solution if uniqueness has not been established. One valid assignment proves possibility, not necessity.
5. Verify the final assignment against every numbered clue and search for a second solution when the question asks what `must` be true.

Return the answer plus a compact proof: forced deductions, any case split, and the uniqueness result. If multiple solutions survive, answer `cannot be determined` and show two witnesses.

## Knights and knaves (truth-tellers and liars)

Knights always tell the truth; knaves always lie.
- Method: **case split**. Assume speaker is a knight → their statement is true → derive consequences. Assume knave → statement is FALSE → derive. Discard cases that contradict.
- Key insight: nobody on the island can say "I am a knave" (knight can't truthfully; knave can't lie into it). Any statement equivalent to "I am lying" is impossible.
- A knave negates the WHOLE statement: knave says "A and B" → truth is "not A OR not B" (De Morgan), not "not A and not B".
- "Are you a knight?" — both types answer "yes". Useless question.
- The embedded-question trick: asking anyone "If I asked you Q, would you say yes?" gets the true answer to Q from both types (a lie about a lie cancels).

## Grid / zebra puzzles (5 houses, 5 owners...)

1. Draw a table: one row per position/person, one column per attribute.
2. Enter direct clues first (fixed positions: "the Norwegian lives in the first house").
3. Convert relational clues to candidate eliminations ("green is immediately left of white" → white ≠ house 1, green ≠ house 5).
4. Loop: whenever a cell is fixed, eliminate that value elsewhere in its column; whenever a value has only one possible cell, fix it.
5. If stuck, pick the cell with exactly 2 candidates and case-split; a contradiction in one branch proves the other.
6. Re-verify EVERY clue against the finished grid before answering.

## Seating / ordering puzzles

Draw the line or circle explicitly. For circles, fix one person's seat first (rotations are equivalent) to anchor everything. Translate "left/right" carefully: in a circle facing center, A's right is counterclockwise... unless stated otherwise — define it once and stay consistent.

## River crossing puzzles

State = who is on each bank + boat position. Rules: enumerate allowed moves; check the forbidden combinations after EVERY move (including who's left behind when the boat departs). Classic wolf-goat-cabbage insight: you may need to bring something BACK. Search systematically (breadth-first over states), pruning repeats.

## Weighing / balance puzzles

n weighings on a balance distinguish at most 3ⁿ outcomes (left / right / balance). 12-coins-one-fake needs 3 weighings because 3³=27 ≥ 24 possibilities. Strategy: each weighing should split remaining possibilities as evenly as possible into three groups. Weigh group vs group, leaving a third group ASIDE — the aside group gives you information when the scale balances.

## "Impossible" riddle checklist

If a riddle seems contradictory, question hidden assumptions:
- Are two people mentioned actually the same person? Is "the doctor" a woman? Is "the surgeon's son" the surgeon's own child?
- Are events simultaneous or sequential? Same day/year?
- Words with double meanings (a "bank", "arms", "pounds")?
- Is the answer trivial once an assumption drops? (Fathers and sons: 3 people can be 2 fathers and 2 sons.)

## Universal self-check

1. Re-read the puzzle; list every constraint with a number.
2. After solving, verify the answer against each numbered constraint one by one.
3. Check uniqueness if asked "who must…": could another assignment also satisfy everything? If yes, the puzzle answer is "cannot be determined" — a legitimate answer.
