---
name: ui-ux-design
description: Use when designing or critiquing any user interface - web pages, apps, dashboards, forms, landing pages - or answering "why does this look bad/feel clunky?" and "how should this screen work?". Provides visual hierarchy rules, spacing/type/color systems, and UX laws.
---

# UI/UX Design

## Reliable workflow

1. Define the primary user, context, top task, success metric, device/input modes, content constraints, and accessibility needs.
2. Map the end-to-end flow and every state: first use, loading, empty, partial, success, validation error, system failure, offline/timeout, permission denied, and destructive recovery.
3. Create a low-fidelity hierarchy before styling. Put the primary action and decisive information in the expected scan path; remove or defer lower-priority choices.
4. Apply a small token system for spacing, type, color, radius, and elevation. Reuse established product patterns before inventing new interactions.
5. Verify keyboard order, focus visibility, semantics, labels, zoom/reflow, contrast, target size, reduced motion, and screen-reader announcements as applicable.
6. Test with representative content, long translations, small and large screens, slow networks, and at least one user who has not seen the design. Observe behavior before asking for opinions.
7. Hand off states, behavior, responsive rules, tokens, content, and acceptance criteria—not only a happy-path screenshot.

When critiquing, tie each finding to user impact and propose the smallest testable correction. Visual fashion is not evidence of usability.

UI answers "does it look right?"; UX answers "does it work right for the person using it?". Both reduce to one principle: **reduce the user's cognitive load.** Every rule below serves that.

## Visual hierarchy — the 80% of "looking professional"

The eye should know where to go first, second, and third. Create hierarchy with size, weight, color/contrast, spacing, and position. Give each task context a clear primary action or focal point; complex dashboards may support several actions, but their relative priority should remain explicit.

Diagnosis: squint at the screen (or blur it). If everything blends into equal gray mush, there's no hierarchy. If the loudest element isn't the most important one, hierarchy is wrong.

## Spacing — where amateur designs actually fail

- Use a **spacing scale**, not ad-hoc pixels: 4/8/12/16/24/32/48/64. Every margin/padding comes from the scale.
- **Whitespace is a feature.** Cramped is the default amateur failure; when in doubt, double the spacing, especially padding inside containers and space between sections.
- **Proximity communicates grouping**: related things close, unrelated things far. Space BETWEEN groups must exceed space WITHIN groups — a label sits closer to its own field than to the previous field.
- Align to a grid; every element's edge lines up with something. Mixed alignments (some centered, some left) read as sloppy — pick left-aligned for text-heavy UI.

## Typography

- One or two typefaces max. A whole UI can be one family with varied size/weight.
- Use a deliberate type scale, for example 12/14/16/20/24/32/48. Around 16 CSS px, body line-height near 1.4–1.6, and line length around 45–75 characters are useful starting points, then validate for the typeface, platform, language, and zoom behavior.
- Hierarchy via weight and size, not many colors. Real text hierarchy: heading bold+large, body regular, secondary text smaller and/or muted gray (not lighter-than-readable).
- Don't center paragraphs; don't use pure black on pure white (slightly soften one: #111 on #fff or off-white).

## Color

- System: 1 primary (brand/action), 1–2 accents, a neutral gray ramp (~8 steps) doing most of the work, plus semantic colors (green success, red danger/error, yellow warning). Most of a good UI is neutrals; color is spent where it means something.
- **Contrast is law**: body text ≥ 4.5:1 against background (WCAG AA), large text ≥ 3:1. Light gray text on white at 2:1 is unreadable design-blogging fashion — don't.
- Never encode meaning in color alone (8% of men are colorblind): pair color with icon/label/position.
- Dark mode is not inverted colors: dark gray surfaces (#121212-ish, not pure black), desaturated accents, elevation shown by lighter surfaces.

## UX laws (name-checkable, apply constantly)

- **Fitts's law**: bigger + closer = easier to hit. Aim for comfortably large touch targets—often around 44×44 CSS px—and meet the applicable accessibility standard; keep destructive actions away from frequent ones.
- **Hick's law**: more choices = slower decisions. Trim menus; progressive disclosure (advanced options behind "More").
- **Jakob's law**: users expect your site to work like every other site. Logo top-left links home; cart top-right; search looks like search. Novelty in navigation is a tax on users.
- **Miller's limit**: don't make people hold >~4–7 items in memory; show state, don't make them remember it.
- **Feedback within 100ms**: every action gets an immediate visible response (pressed state, spinner past ~400ms, skeleton screens for loads, optimistic UI where safe). Silence after a click = perceived breakage.
- **Forgiveness**: confirm destructive actions (or better, allow undo — undo beats confirm), preserve user input on errors, never clear a form because validation failed.

## Forms (where UX is won/lost)

Ask for the minimum. One column. Labels ABOVE fields (not placeholder-as-label — it vanishes on focus). Inline validation on blur, not only on submit; error messages say what's wrong AND how to fix ("Password needs 8+ characters" not "Invalid input"). Group related fields; mark optional rather than required if most are required. The submit button states the action ("Create account", not "Submit").

## Process & critique method

1. Who is the user and what's the ONE thing this screen must let them do?
2. Wireframe the hierarchy before styling anything (structure → spacing → type → color, in that order).
3. Critique pass: squint test (hierarchy) → spacing-scale audit → contrast check → "can a first-time user tell what to do in 5 seconds?" → keyboard/tab through everything (focus states visible? works without a mouse?).
4. Copy is design: labels, empty states ("No projects yet — create your first"), and error text deserve the same care as pixels.
