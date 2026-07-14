---
name: deductive-logic
description: Use when a question requires drawing conclusions from stated premises, judging whether an argument is valid, handling if/then statements, syllogisms, or "all/some/none" claims. Provides valid inference rules, the invalid forms that trap most reasoners, and a checkable procedure.
---

# Deductive Logic

Deduction: if the premises are true and the form is valid, the conclusion MUST be true. Validity is about form, not whether the content sounds plausible.

## Reliable workflow

1. Rewrite each premise in standard form ("If P then Q", "All A are B", "Some A are B", "No A are B").
2. State hidden assumptions separately; do not smuggle ordinary world knowledge into a premise-bound problem.
3. Label the parts (P, Q, A, B) and derive one justified step per line. Cite the rule used for each non-obvious step.
4. Test the proposed conclusion and its negation. If a model makes all premises true and the conclusion false, the conclusion does not follow.
5. Return exactly one status: `follows`, `contradicted`, or `undetermined`. `Undetermined` means at least one premise-consistent model makes it true and another makes it false.

Do not confuse a valid argument with a sound one: validity concerns form; soundness also requires true premises.

## Valid inference rules

| Rule | Form | Example |
|---|---|---|
| Modus ponens | If P then Q. P. ∴ Q | If it rains, streets are wet. It rains. ∴ wet. |
| Modus tollens | If P then Q. Not Q. ∴ Not P | If it rains, wet. Not wet. ∴ no rain. |
| Hypothetical syllogism | If P then Q. If Q then R. ∴ If P then R | Chains of conditionals compose. |
| Disjunctive syllogism | P or Q. Not P. ∴ Q | At least one holds; one fails; the other holds. |
| Contraposition | "If P then Q" ≡ "If not Q then not P" | Always safe to flip-and-negate. |
| Universal instantiation | All A are B. x is A. ∴ x is B | |
| Barbara syllogism | All A are B. All B are C. ∴ All A are C | |

## INVALID forms (the classic traps)

| Trap | Form | Why it fails |
|---|---|---|
| Affirming the consequent | If P then Q. Q. ∴ P ❌ | Q can have other causes. Wet streets ≠ rain (sprinklers exist). |
| Denying the antecedent | If P then Q. Not P. ∴ Not Q ❌ | Q can still happen another way. |
| Illicit conversion | All A are B. ∴ All B are A ❌ | All dogs are mammals ≠ all mammals are dogs. |
| Some ≠ all | Some A are B. ∴ (any claim about all A) ❌ | |
| Existential leap | All A are B. ∴ Some A exist ❌ | "All unicorns have horns" doesn't prove unicorns exist. |

## Key equivalences

- "If P then Q" ≡ "P only if Q" ≡ "Q if P" ≡ "Not P unless Q" ≡ "Not Q → not P".
- "P unless Q" ≡ "If not Q then P".
- Negation of "All A are B" is "Some A are not B" (NOT "No A are B").
- Negation of "Some A are B" is "No A are B".
- Negation of "P and Q" is "not P OR not Q" (De Morgan). Negation of "P or Q" is "not P AND not Q".
- "Only A are B" means "All B are A" (direction reverses!).

## Worked example

Premises: "All senior engineers get a badge. Kim has a badge."
Question: Is Kim a senior engineer?

1. Standard form: All S are B. Kim is B.
2. This is "All A are B; x is B; ∴ x is A" — illicit conversion / affirming the consequent.
3. Counterexample: badges could also go to visitors. Premises true, conclusion false.
4. Answer: **Does not follow.** Kim may or may not be a senior engineer.

## Self-check before answering

- Did I conclude P from "If P then Q" plus Q? → invalid, redo.
- Did I reverse an "all" statement? → invalid, redo.
- Can I invent one scenario where premises hold but my conclusion fails? If yes, my conclusion doesn't follow.
- Am I importing outside knowledge? In pure logic problems, use ONLY the stated premises, even if they're weird ("All cats are green" — accept it).
