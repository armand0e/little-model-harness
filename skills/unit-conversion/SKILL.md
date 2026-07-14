---
name: unit-conversion
description: Use whenever quantities carry units - conversions (metric/imperial, time, temperature, currency-style rates), checking a formula's plausibility, or any physics/chemistry/cooking/travel calculation. Dimensional analysis catches wrong setups automatically.
---

# Units & Dimensional Analysis

## Reliable workflow

1. Write the starting quantity and target unit explicitly. Identify whether the quantity is a value, difference, rate, area, volume, or compound unit.
2. Use authoritative or exact conversion factors when precision matters; mark approximations and currency/time-dependent rates with their date or source.
3. Multiply by factor-label fractions so every unwanted unit cancels on paper. Square or cube the entire length factor for area or volume.
4. Calculate without premature rounding, then round to the precision justified by the inputs.
5. Verify by reversing the conversion and checking order of magnitude, dimensions, and physical plausibility.

Do not convert between different physical dimensions without an additional physical relationship. Mass and volume, for example, require density; energy and power require time.

**Output:** Show the original value, complete factor-label chain, canceled units, unrounded result, rounded result, and reverse/magnitude check.

## The factor-label method (always works)

Write the quantity, then multiply by conversion fractions equal to 1, arranged so unwanted units cancel diagonally:

65 mph → m/s: 65 mile/h × (1609 m / 1 mile) × (1 h / 3600 s) = 65×1609/3600 ≈ **29 m/s**.

If the units don't cancel to the target, the setup is wrong — flip a fraction. This mechanically prevents the multiply-vs-divide mistake.

## Conversion table

**Length**: 1 in = 2.54 cm (exact). 1 ft = 30.48 cm. 1 yd = 0.9144 m. 1 mile = 1.609 km = 5280 ft. 1 km ≈ 0.621 mi. 1 m ≈ 3.28 ft ≈ 39.4 in. 1 nautical mile = 1.852 km.

**Mass**: 1 kg = 2.205 lb. 1 lb = 453.6 g = 16 oz. 1 oz ≈ 28.35 g. 1 (metric) tonne = 1000 kg ≈ 2205 lb; 1 US ton = 2000 lb.

**Volume**: 1 L = 1000 mL = 1000 cm³. 1 US gal = 3.785 L = 4 qt = 8 pt = 16 cups = 128 fl oz. 1 cup = 237 mL ≈ 240 mL; 1 tbsp = 15 mL; 1 tsp = 5 mL. 1 m³ = 1000 L. (UK/imperial gallon = 4.546 L — differs from US!)

**Speed**: 1 m/s = 3.6 km/h. 60 mph ≈ 97 km/h ≈ 27 m/s. 1 knot = 1.852 km/h.

**Temperature**: °F = °C×9/5 + 32. °C = (°F−32)×5/9. K = °C + 273.15. Anchors: −40° is the same in both; 0°C=32°F (freezing); 20°C=68°F (room); 37°C=98.6°F (body); 100°C=212°F (boiling). Quick approx: °F ≈ 2×°C + 30. NOTE: temperature DIFFERENCES convert by the factor only (a rise of 10°C = a rise of 18°F — no +32).

**Energy/power**: 1 kWh = 3.6 MJ. 1 food Calorie (kcal) = 4184 J; daily diet ~2000 kcal ≈ 8.4 MJ. 1 hp ≈ 746 W. 1 BTU ≈ 1055 J.

**Pressure**: 1 atm = 101.325 kPa = 1.013 bar ≈ 14.7 psi ≈ 760 mmHg.

**Time**: 1 yr ≈ 365.25 days ≈ 8766 h ≈ 3.156×10⁷ s. 1 week = 168 h. 1 day = 1440 min = 86,400 s.

**Metric prefixes**: n(10⁻⁹) µ(10⁻⁶) m(10⁻³) c(10⁻²) k(10³) M(10⁶) G(10⁹) T(10¹²). Data: KB/MB/GB/TB usually 10³ steps; KiB/MiB/GiB are 1024 steps.

**Area/volume conversions square/cube the factor**: 1 m² = 10⁴ cm² (not 100). 1 m³ = 10⁶ cm³. 1 km² = 100 hectares = 247 acres; 1 acre ≈ 4047 m² (~a football field without end zones). 1 hectare = 10⁴ m².

## Dimensional sanity-checking formulas

Every equation must balance dimensionally. distance = speed × time: [m] = [m/s]·[s] ✓. If a derived formula gives [m²/s] where a length is expected, the formula is wrong — no need to check the algebra to know it. You cannot add quantities with different dimensions (5 m + 3 kg is meaningless; 5 m + 30 cm requires conversion first).

## Self-check

- Did units cancel all the way to the target unit?
- Area/volume factors squared/cubed?
- Temperature difference vs temperature value handled correctly?
- Magnitude plausible? (A human walking 400 km/h, a 2-gram car → unit slip, usually ×1000 off.)
- Same unit system throughout the whole calculation — convert at the START, not mid-formula.
