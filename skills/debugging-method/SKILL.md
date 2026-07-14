---
name: debugging-method
description: Use when anything is broken - code bugs, failing tests, system faults, "it worked yesterday", or any troubleshooting (software or otherwise). Provides the hypothesis-driven method that beats random tweaking.
---

# Debugging Method

Debugging is applied science: observe, hypothesize, test the hypothesis with the cheapest discriminating experiment, repeat. Random tweaking ("maybe if I change this…") destroys evidence and wastes hours.

## Reliable workflow

1. **Capture the failure.** Record expected vs actual behavior, inputs, environment, frequency, and full error/trace. Minimize to a reliable trigger when possible; for intermittent faults, preserve logs and identify conditions that change frequency.
2. **Read the actual error.** Preserve the full message and stack; locate the first relevant frame in code you control. Do not paraphrase away file, line, value, or exception details.
3. **State what changed.** Check code, dependency, data, environment, configuration, and time changes. Use diffs, deploy history, or bisection when needed.
4. **Form hypotheses — at least two.** Write a table: `hypothesis | predicted observation | cheapest discriminating test`. Rank by prior plausibility and evidence, not vividness.
5. **Discriminate cheaply.** Run the observation that most cleanly separates the leading hypotheses: inspect the value at a boundary, validate the actual input, compare a known-good environment, or disable one component. Change one variable at a time and preserve the result.
6. **Localize by bisection.** Inspect a midpoint: wrong means search upstream; right means search downstream. Repeat across code, configuration, data, or hardware boundaries.
7. **Fix the cause at the correct boundary.** Avoid exceptions, null checks, retries, or sleeps that merely suppress evidence. If containment is necessary, label it as containment and keep the root-cause path open.
8. **Verify and generalize.** Replay the trigger/trace, run broader tests, search for siblings, and add a regression test or monitor. For intermittent failures, collect enough observations to distinguish improvement from variance.

**Output:** Report the observed failure, root cause with evidence, exact fix or containment, regression coverage, commands/tests run, and any path still unverified.

## Heuristics that pay rent

- **Check the dumb things first**: is it plugged in / saved / deployed / the right environment / the right database / the file you think you're editing? Print `"AM I EVEN RUNNING"` — a shocking fraction of "impossible" bugs are the wrong code running.
- Start with the newest and least-tested code, configuration, data, or dependency change. Libraries, runtimes, and infrastructure do fail; keep them as hypotheses and use evidence to rank them.
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
