---
name: explaining-concepts
description: Use when teaching, explaining a concept, writing documentation or tutorials, answering "how does X work?" or "explain like I'm five", or making a technical idea land for a non-expert. Provides the concrete-first method and audience calibration.
---

# Explaining Concepts

An explanation succeeds when the listener can USE the idea — predict with it, apply it, spot it — not when the explainer has said true things.

## Reliable workflow

1. Identify the audience's starting point and the behavior the explanation should enable: recognize, predict, calculate, build, or decide.
2. Give a one-sentence core in known vocabulary, then one concrete example whose details map directly to the concept.
3. Explain one causal or logical chain at a time. Make every link explicit; introduce at most a few new terms per layer.
4. Show a contrasting non-example or boundary so the learner does not overgeneralize.
5. Check transfer: ask the learner to predict a new case, paraphrase the idea, or solve one tiny problem. Use the result to repair the explanation if interaction is available.
6. Offer deeper formalism only after the operational model is correct.

Never trade correctness for simplicity. Label a simplified model, state where it breaks, and avoid analogies that support a false inference.

**Output:** Give the core sentence, concrete example, mechanism, boundary/non-example, and one transfer check at the requested depth.

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
