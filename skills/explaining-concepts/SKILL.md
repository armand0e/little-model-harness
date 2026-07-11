---
name: explaining-concepts
description: Use when teaching, explaining a concept, writing documentation or tutorials, answering "how does X work?" or "explain like I'm five", or making a technical idea land for a non-expert. Provides the concrete-first method and audience calibration.
category: writing
hint: teach ideas clearly at any level
---
# Explaining Concepts

An explanation succeeds when the listener can USE the idea — predict with it, apply it, spot it — not when the explainer has said true things.

## The structure that works

1. **One-sentence core**: the idea compressed to its essence, in words the audience already knows. ("Inflation: money buys less over time because prices rise.")
2. **Concrete example FIRST**: a specific, familiar scenario showing the idea in action. Concrete-then-abstract beats abstract-then-concrete for almost every learner.
3. **The mechanism**: WHY it works, one causal chain, no branches on the first pass.
4. **A boundary**: where it does NOT apply, or the nearest wrong idea it should not be confused with. ("Inflation is a rise in the general price level — one product getting pricier isn't inflation.")
5. **A check**: a tiny question or application letting the learner test themselves.

## Calibrating to the audience

- Identify what they already know and anchor to it. Explain the new in terms of the known: "a database index is like a book's index" works because everyone has used a book index.
- Vocabulary rule: each unavoidable new term gets defined at first use, in one clause. If you need more than ~2 new terms, the explanation is at the wrong altitude — zoom out.
- "Explain like I'm 5/12/a-new-grad" changes the ANALOGY BUDGET and vocabulary, not the truth. Simplify by omitting detail, never by asserting falsehoods you must retract later ("lies-to-children" are okay only if flagged: "this is the simplified picture").
- For experts: skip the scaffolding, lead with the delta from what they'd expect.

## Analogy discipline

A good analogy maps the causal structure, not the surface. Electricity:water-in-pipes works for voltage/pressure and current/flow; it breaks for capacitance subtleties — USE it, and drop it at the breaking point with a one-line flag. Test any analogy: does the inference the learner will naturally draw from it hold in the real domain? If not, it teaches a bug.

## Progressive disclosure

Layer 1: the core sentence (everyone gets this far). Layer 2: example + mechanism. Layer 3: exceptions, edge cases, formalism — only when asked or needed. Don't front-load caveats; a hedge-riddled first paragraph teaches nothing. Get the 90%-true simple picture landed, then refine.

## Common failure modes

- **Curse of knowledge**: skipping steps that are obvious to you. Fix: walk the chain as if each link must be shown.
- **Definition ping-pong**: defining terms with other undefined terms.
- **Example-free abstraction**: three paragraphs of generality the reader can't picture.
- **Kitchen-sink completeness**: every exception up front. Completeness is for references, not explanations.
- **Wrong altitude**: answering "how does the internet work" with TCP packet headers, or "why is my code slow" with a lecture on big-O. Match the question's altitude, offer to zoom.

## Worked micro-example

Q: "What's a hash function?" (non-programmer)

"A hash function is a blender for data: put anything in, and you get a fixed-size fingerprint out (1). The same input always gives the same fingerprint, but you can't un-blend the fingerprint back into the input, and even a tiny change to the input gives a completely different fingerprint (3). It's how websites check your password without storing it: they keep the fingerprint of your password, blend what you type at login, and compare fingerprints (2). It's not encryption — encryption is meant to be reversed by someone with the key; hashing is one-way by design (4). Quick check: if two files have the same fingerprint, what do you know? — almost certainly the same file (5)."
