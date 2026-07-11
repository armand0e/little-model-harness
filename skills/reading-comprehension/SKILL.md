---
name: reading-comprehension
description: Use when answering questions about a provided text/document/passage, summarizing, extracting requirements, or following written instructions precisely. Prevents the classic failures - answering from prior knowledge instead of the text, missing negations, and over-summarizing.
category: writing
hint: extract what a text actually says
---
# Reading Comprehension & Instruction Following

## The prime rule: the text outranks your memory

When a question is about a PROVIDED text, the answer comes from the text — even where the text is surprising, fictional, or contradicts general knowledge. If the passage says the trial was in 1993 and you remember 1995, the answer to "when, according to the passage?" is 1993. Blending memory into text questions is the #1 comprehension failure.

## Method for text questions

1. Read the QUESTION first — know what you're hunting.
2. Locate the relevant span; quote or point to it mentally ("the answer lives in paragraph 3").
3. Answer strictly from the span, in the asked format.
4. Check the question's exact wording: "according to the author", "which is NOT mentioned", "the second reason", "EXCEPT", "mainly about". Negations and superlatives ("not", "least", "except", "primary") reverse or narrow the target — underline them.
5. If the text doesn't contain the answer, SAY SO ("the passage doesn't state this") — options that are true-in-the-world but absent-from-the-text are traps.

## Distinguish the four layers

- **Stated**: explicitly in the text. Highest confidence, quote it.
- **Implied**: follows from the text with minimal inference (they "trudged through drifts" → it had snowed). Safe to infer; label as inference in strict contexts.
- **Consistent-but-unsupported**: could be true, text doesn't establish it. NOT a valid answer to "what does the passage show?"
- **Contradicted**: rule out even if it sounds worldly-true.

Also separate the author's CLAIMS from the author's REPORTS of others' claims ("critics argue X" ≠ author believes X), and watch stance markers: "supposedly", "so-called", scare quotes signal distance or irony.

## Summarizing without distortion

- Preserve: the main claim, the load-bearing reasons, key qualifications ("in mice", "under lab conditions", "except for Q4"), and quantities. Dropping a qualifier is a factual error, not a simplification.
- Don't upgrade hedges: "may reduce risk" summarized as "reduces risk" is a lie in miniature. Preserve modality (may/should/must; some/most/all).
- Attribute: keep who-said-what attached to what was said.
- Length rule: a summary answers "what would the author agree they said?" — run that test on your draft.

## Following written instructions (specs, prompts, forms)

- Extract every requirement into a checklist first — including format requirements (word limits, "answer in one word", "use JSON", "do not include X"). Instructions about FORM are as binding as instructions about content and are the most-commonly dropped.
- Note ordering and conditionals: "if A, then do B, otherwise C" — identify which branch applies before acting.
- Silent conflicts: if two instructions clash, flag it and state which you followed; don't quietly pick one.
- After producing the output, re-walk the checklist item by item against your output. "Did I follow the instructions?" as a yes-feeling is worthless; verify each item.

## Trap inventory

- Answering the neighboring question (asked "why", answered "what").
- Missing "NOT/EXCEPT" reversals.
- The vivid-detail trap: choosing the answer echoing a memorable phrase from the wrong part of the text.
- Scope creep: question asks about paragraph 2, answer imports paragraph 5.
- Pronoun mis-binding: trace every "it/this/they" to its noun explicitly when it matters.
- Instructions read once at the start, forgotten by the end — for long tasks, RE-READ the instructions right before finalizing.
