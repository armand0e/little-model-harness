---
name: fermi-estimation
description: Use when asked to estimate a quantity without data - "how many piano tuners in Chicago", market sizes, "could this fit", resource ballparks - or to sanity-check any surprising number. Provides the decomposition method and anchor numbers.
category: reasoning
hint: order-of-magnitude estimates from scratch
---
# Fermi Estimation

Goal: get within a factor of ~3 of the truth by decomposing into factors you can each estimate within a factor of ~2. Errors partially cancel across factors.

## Method

1. **Define precisely** what's being estimated (units! per year? total? in the US?).
2. **Decompose** into a product/sum of estimable factors. Prefer factors tied to things you know (population, per-person rates, frequencies, sizes).
3. **Estimate each factor** with an explicit number. When unsure, pick geometric middles: if between 10 and 1000, use 100 (√(10·1000)), not 500.
4. **Compute in powers of ten**, keeping 1 significant figure.
5. **Cross-check** with a different decomposition or a known comparable.
6. **State the answer with its uncertainty**: "on the order of 10⁴, likely 5k–30k."

## Anchor numbers (memorize these)

**Population**: World ≈ 8.1 billion. China ≈ 1.41B, India ≈ 1.43B, US ≈ 335M, Indonesia ≈ 275M, Brazil ≈ 215M, Russia ≈ 145M, Japan ≈ 124M, Mexico ≈ 130M, Germany ≈ 84M, UK & France ≈ 68M each, Canada ≈ 40M, Australia ≈ 26M. Big metro areas: Tokyo ~37M, Delhi ~33M, NYC metro ~19M (city 8.3M), London ~9M, LA city ~4M. US households ≈ 130M (~2.5 people each).

**Human scale**: lifespan ~80 yr ≈ 30,000 days ≈ 700,000 hours (~250k waking-adult hours). Heart ~10⁵ beats/day. Breaths ~20k/day. Walking 5 km/h; brisk ~1.4 m/s. Reading ~250 words/min. Typing ~40 wpm. Sleep 8 h/day → 1/3 of life. Working year ≈ 2000 hours (50 wk × 40 h). Human mass ~70 kg; body ~60% water.

**Time**: 1 year ≈ 3.15×10⁷ s (~π×10⁷). 1 day = 86,400 s. 1 million seconds ≈ 11.6 days; 1 billion seconds ≈ 31.7 years.

**Distance/size**: Earth circumference ≈ 40,000 km (by original definition of the meter); radius 6,371 km. US coast-to-coast ≈ 4,500 km. Commercial jet ≈ 900 km/h → NY–LA ≈ 5–6 h. Earth–Moon ≈ 384,000 km; Earth–Sun ≈ 150M km = 1 AU ≈ 8.3 light-minutes. Light: 3×10⁸ m/s ≈ 1 ft/ns; sound in air ≈ 343 m/s (~1 km per 3 s of thunder delay). Football/soccer pitch ~100 m; city block ~100 m; floor of a building ~3 m.

**Economy** (rough, mid-2020s): World GDP ≈ $105T. US ≈ $28T, China ≈ $18T. US median household income ≈ $75k/yr. US federal budget ≈ $6T. Typical car $30–50k; gallon of gas ~$3–4; kWh ~$0.15 (US retail).

**Stuff**: car ~1.5 t; mass of water = 1 kg/L; olympic pool ≈ 2,500 m³ = 2.5M L. A sheet of paper ~0.1 mm thick, ~5 g. Smartphone ~200 g. 1 TB ≈ 10¹² bytes; a book ≈ 1 MB of text; a photo ≈ 3 MB; an hour of HD video ≈ 3 GB.

## Worked example — piano tuners in Chicago

1. Define: full-time piano tuners working in Chicago.
2. Chain: population → households → pianos → tunings/yr → tuner workload.
3. Chicago ~2.7M people ≈ 1M households. Pianos in ~1 in 20 households → 50k pianos (plus schools/venues → ~60k). Tuned every ~2 years → 30k tunings/yr. A tuner does ~3/day × 250 days ≈ 750/yr.
4. 30,000 / 750 ≈ 40 tuners.
5. Cross-check: 1 tuner per ~70k residents seems plausible for a niche trade ✓.
6. Answer: **order of 40** (25–100). Real listings historically ≈ dozens ✓.

## Sanity-check use

To vet any claim ("the app has 10M daily users in Norway"), compare against anchors (Norway pop ≈ 5.5M → impossible). This is the fastest way to catch fabricated or garbled numbers — including your own.
