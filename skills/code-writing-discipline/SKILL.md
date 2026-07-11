---
name: code-writing-discipline
description: Use whenever writing or editing code - the working discipline for producing correct, reviewable changes: read before writing, minimal diffs, edge-case habits, testing, and honest reporting of what was and wasn't verified.
category: software
hint: habits for writing correct clean code
---
# Code Writing Discipline

How to produce code the way a careful senior engineer does. This is about the PROCESS of a change; see software-design-taste for structure and naming.

## Before writing

- **Read the surrounding code first.** The function you're changing, its callers, the module's existing helpers and idioms. Half of all bad patches solve a problem the codebase already has a utility for, or violate a convention every other file follows.
- Reproduce/confirm the current behavior if fixing a bug (see debugging-method). Never fix a bug you haven't seen happen.
- Find the right LOCATION for the change: the cause, not the symptom site; the shared helper, not all five call sites.

## While writing

- **Minimal diff for the goal.** Don't reformat untouched lines, rename unrelated variables, reorder imports, or "improve" adjacent code in the same change — it buries the real change and inflates review risk. Note improvements for a separate change.
- Handle the edges as you go, in this order of neglect: empty input, single element, `None`/null, duplicates, unicode/whitespace in strings, zero/negative numbers, boundary indices, concurrent/repeated calls. For each, decide: handle, or explicitly reject with a clear error. Never silently misbehave.
- Errors: fail loudly on impossible states; catch narrowly (specific exception types), never bare-except-pass. Error messages must say what failed AND with what value: `f"config key {key!r} missing in {path}"` — your 3 a.m. future self is the audience.
- No magic literals: name the constant (`MAX_RETRIES = 3`). No commented-out code — delete it; git remembers.
- Resource hygiene: files/connections/locks in `with`/try-finally. Anything acquired gets released on ALL paths.
- Naming/comments/structure: per software-design-taste — comments say WHY only.

## After writing — verification is part of writing

- **Run it.** Code that has never executed doesn't work; syntax-plausible is not correct. Run the specific case you changed, plus the edges you claimed to handle.
- Trace by hand on one small input if you can't execute — actually simulate the loop with n=2, don't skim-approve your own logic.
- Run the existing tests. A change that breaks other tests isn't done, it's damage.
- Write a test for the new behavior: the smallest test that would FAIL without your change. Test behavior through the public interface, not implementation internals. One assertion-idea per test; name the test after the behavior (`test_expired_token_is_rejected`).
- Re-read the final diff top to bottom as a reviewer would — this catches leftover debug prints, TODOs, and the file you forgot to save.

## Reporting the change

State: what was wrong, what you changed, and HOW YOU VERIFIED it ("ran X, saw Y; tests pass" — with the actual output if it matters). If something is unverified, say so explicitly ("compiles and unit tests pass; I could not test the S3 path locally"). Never claim "it works" about untested paths — the phrase for that is "it should work, but I haven't verified Z."

## Language-agnostic bug magnets (double-check these lines)

- Integer division truncation (`5/2` in some languages is 2), float equality (`0.1+0.2 != 0.3` — compare with tolerance).
- Mutable default arguments (Python), closure-over-loop-variable, aliasing (two names, one list — copy or not?).
- Off-by-one at every boundary; `<` vs `<=`; `len(x)` vs `len(x)-1`; slice end exclusivity.
- Timezone-naive datetimes; string comparison of numbers ("10" < "9"); locale-dependent parsing.
- Order of operations in compound conditions; `and`/`or` short-circuit relied on or violated; negated De Morgan slips (`not (a and b)` ≠ `not a and not b`).
- Empty-collection behavior of aggregations (`max([])` raises; `sum([])` is 0).
