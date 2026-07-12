---
name: ui-ux-design
description: Use when designing or critiquing any user interface - web pages, apps, dashboards, forms, landing pages - or answering "why does this look bad/feel clunky?" and "how should this screen work?". Provides visual hierarchy rules, spacing/type/color systems, and UX laws.
category: creative
hint: layout, hierarchy, flows users understand
---
# UI/UX Design

UI answers "does it look right?"; UX answers "does it work right for the person using it?". Both reduce to one principle: **reduce the user's cognitive load.** Every rule below serves that.

## Verification is part of design

Never finish UI work from source code alone. Run `visual_check` and personally inspect the attached desktop, tablet, and mobile screenshots. Capture important interaction states with `click_selector` and `state_label` (navigation open, modal open, validation errors, empty/loading states). Check for horizontal overflow, clipped text, broken imagery, weak contrast, inconsistent spacing, unclear hierarchy, and controls that disappear at narrow widths. Fix what you see and repeat the check until the screenshots support the claim that the interface is polished.

## Visual hierarchy — the 80% of "looking professional"

The eye must know where to go first, second, third. Create hierarchy with (in order of power): **size, weight, color/contrast, spacing, position**. One screen = one primary action; make it visually loudest, and demote everything else deliberately (secondary buttons get outline style; tertiary get plain text links).

Diagnosis: squint at the screen (or blur it). If everything blends into equal gray mush, there's no hierarchy. If the loudest element isn't the most important one, hierarchy is wrong.

## Spacing — where amateur designs actually fail

- Use a **spacing scale**, not ad-hoc pixels: 4/8/12/16/24/32/48/64. Every margin/padding comes from the scale.
- **Whitespace is a feature.** Cramped is the default amateur failure; when in doubt, double the spacing, especially padding inside containers and space between sections.
- **Proximity communicates grouping**: related things close, unrelated things far. Space BETWEEN groups must exceed space WITHIN groups — a label sits closer to its own field than to the previous field.
- Align to a grid; every element's edge lines up with something. Mixed alignments (some centered, some left) read as sloppy — pick left-aligned for text-heavy UI.

## Typography

- One or two typefaces max. A whole UI can be one family with varied size/weight.
- A **type scale**: e.g. 12/14/16/20/24/32/48. Body text 16px minimum; line height ~1.5 for body, ~1.2 for headings; line length 45–75 characters.
- Hierarchy via weight and size, not many colors. Real text hierarchy: heading bold+large, body regular, secondary text smaller and/or muted gray (not lighter-than-readable).
- Don't center paragraphs; don't use pure black on pure white (slightly soften one: #111 on #fff or off-white).

## Color

- System: 1 primary (brand/action), 1–2 accents, a neutral gray ramp (~8 steps) doing most of the work, plus semantic colors (green success, red danger/error, yellow warning). Most of a good UI is neutrals; color is spent where it means something.
- **Contrast is law**: body text ≥ 4.5:1 against background (WCAG AA), large text ≥ 3:1. Light gray text on white at 2:1 is unreadable design-blogging fashion — don't.
- Never encode meaning in color alone (8% of men are colorblind): pair color with icon/label/position.
- Dark mode is not inverted colors: dark gray surfaces (#121212-ish, not pure black), desaturated accents, elevation shown by lighter surfaces.

## UX laws (name-checkable, apply constantly)

- **Fitts's law**: bigger + closer = easier to hit. Primary buttons are large; touch targets ≥ 44×44px; destructive actions are NOT adjacent to frequent ones.
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
