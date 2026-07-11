---
name: debugging-method
description: Use when anything is broken - code bugs, failing tests, system faults, "it worked yesterday", or any troubleshooting (software or otherwise). Provides the hypothesis-driven method that beats random tweaking.
category: software
hint: systematic bug isolation and fixing
---
# Debugging Method

Debugging is applied science: observe, hypothesize, test the hypothesis with the cheapest discriminating experiment, repeat. Random tweaking ("maybe if I change this…") destroys evidence and wastes hours.

## The method

1. **Reproduce it.** A bug you can trigger on demand is half-solved. Find the minimal reliable trigger. If it's intermittent, find what makes it more frequent (load? timing? specific data?). Don't fix what you can't reproduce — you won't know you fixed it.
2. **Read the actual error.** The full message, the full stack trace, top frame in YOUR code. The error text usually names the file, line, and cause. Resist skimming: `KeyError: 'user_id'` is not a mystery, it's an address.
3. **State what changed.** Code worked before? Something changed: your code, a dependency, the data, the environment, the clock. `git diff`, recent deploys, new data shapes. Bisect history if needed (git bisect is O(log n) — 1000 commits is 10 checks).
4. **Form hypotheses — at least two.** The #1 debugging failure is anchoring on the first theory. Write down the top 2–3 suspects with a quick prior on each.
5. **Discriminate cheaply.** Design the observation that best splits your hypotheses: a print/log of the value AT the suspect boundary, a check whether the input is what you think, a run with the feature disabled. Change/observe ONE variable at a time.
6. **Localize by bisection.** Cut the pipeline in half: is the data already wrong at the midpoint? Wrong → bug upstream; right → downstream. Repeat. Works on code, configs, data pipelines, and hardware alike.
7. **Fix the cause, not the symptom.** Adding a `try/except` around the crash, a null-check that hides the missing value, or a `sleep()` for a race — these bury the bug for a worse day. Ask "why was the value null AT ALL?" — apply five-whys until you hit a cause whose fix prevents the class of bug.
8. **Verify the fix + hunt siblings.** Re-run the original reproduction (must now pass), run the broader tests (must not newly fail), and grep for the same pattern elsewhere — bugs come in families. Add a regression test that would have caught it.

## Heuristics that pay rent

- **Check the dumb things first**: is it plugged in / saved / deployed / the right environment / the right database / the file you think you're editing? Print `"AM I EVEN RUNNING"` — a shocking fraction of "impossible" bugs are the wrong code running.
- **The bug is almost never in the compiler/OS/library.** It's in the newest, least-tested code: yours. Suspect your own diff first.
- **Question assumptions in order of least-verified.** "It can't be the input" — have you LOOKED at the input? Actual data beats assumed data.
- **Rubber-duck it**: explain the code line-by-line aloud/in writing to no one. The act of serializing your assumptions exposes the false one.
- **Heisenbugs** (vanish when observed) scream timing/concurrency/uninitialized memory. **Works-on-my-machine** screams environment: versions, env vars, locale, path separators, timezone.
- **Off-by-one zone**: loop bounds, array ends, fencepost counts, inclusive/exclusive ranges, `<` vs `<=`.
- **Fresh state test**: does it reproduce after a clean restart / clean checkout / incognito window? Splits "stale state" from "real logic bug" in one move.
- If truly stuck for two cycles: take a break, or write the "help me" message describing everything you know — writing it usually reveals the answer before you send it.

## What NOT to do

- Change three things, see it pass, ship it. (Which one fixed it? Is it even fixed, or masked?)
- Assume the reported symptom is at the fault site — errors surface far downstream of their cause; trace the bad value BACKWARD to where it was born.
- Delete the reproduction before adding the regression test.
