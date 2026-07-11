---
name: geometry-essentials
description: Use for geometry questions - areas, perimeters, volumes, angles, triangles, circles, the Pythagorean theorem, similar shapes, and coordinate geometry. Provides the formula table and the scaling laws people get wrong.
category: math
hint: areas, volumes, angles, triangles
---
# Geometry Essentials

Always draw the figure and label every given length/angle before computing. Most geometry errors are setup errors.

## Area & perimeter

| Shape | Area | Perimeter/Circumference |
|---|---|---|
| Rectangle | l·w | 2(l+w) |
| Triangle | ½·base·height (height ⊥ base) | sum of sides |
| Parallelogram | base·height | 2(a+b) |
| Trapezoid | ½(a+b)·h (a,b parallel sides) | sum |
| Circle | πr² | 2πr = πd |
| Sector (angle θ°) | (θ/360)·πr² | arc = (θ/360)·2πr |

## Volume & surface area

| Solid | Volume | Surface |
|---|---|---|
| Box | l·w·h | 2(lw+lh+wh) |
| Cylinder | πr²h | 2πr² + 2πrh |
| Sphere | (4/3)πr³ | 4πr² |
| Cone | (1/3)πr²h | πr² + πr·slant |
| Any pyramid/cone | (1/3)·base area·height | |
| Any prism | base area · height | |

## The scaling laws (heavily tested, heavily botched)

Scale every length by k → **areas scale by k², volumes by k³.** Double a pizza's diameter → 4× the pizza. A 16" pizza > two 10" pizzas (256 vs 200 in units of π/4). Halve a statue → 1/8 the material. Similar triangles with side ratio 2:3 have area ratio 4:9.

## Angles

- Straight line: 180°. Around a point: 360°. Vertical (opposite) angles are equal.
- Parallel lines + transversal: alternate angles equal, corresponding equal, co-interior sum to 180°.
- Triangle angles sum to 180°; exterior angle = sum of the two remote interior angles.
- Polygon with n sides: interior angles sum to (n−2)·180°. Regular polygon interior angle = that / n. Exterior angles always sum to 360°.
- Isosceles: base angles equal. Equilateral: all 60°.

## Triangles

- **Pythagoras** (right triangles only): a² + b² = c², c the hypotenuse. Common integer triples: 3-4-5, 5-12-13, 8-15-17, 7-24-25 — and their multiples (6-8-10).
- Triangle inequality: each side < sum of the other two. (2, 3, 7 is impossible.)
- Special right triangles: 45-45-90 sides 1:1:√2; 30-60-90 sides 1:√3:2 (short side opposite 30°).
- Similar triangles (equal angles): sides in proportion — set up ratios of CORRESPONDING sides (match the angles they're opposite).
- Trig in right triangles: sin = opp/hyp, cos = adj/hyp, tan = opp/adj (SOH-CAH-TOA). sin30=0.5, cos60=0.5, sin45=cos45≈0.707, tan45=1.

## Circles

- Angle inscribed in a semicircle = 90° (Thales). Inscribed angle = half the central angle on the same arc.
- Tangent ⊥ radius at the point of contact. Two tangents from an external point are equal.

## Coordinate geometry

- Distance: √((x₂−x₁)² + (y₂−y₁)²). Midpoint: averages of coordinates.
- Slope m = Δy/Δx. Parallel: equal slopes. Perpendicular: slopes multiply to −1.
- Line: y = mx + b (b = y-intercept). Circle: (x−a)² + (y−b)² = r².

## Self-check

- Height perpendicular to the base I used? (A slanted side is NOT the height.)
- Units squared for area, cubed for volume; consistent units throughout.
- Answer physically plausible? Compare against a bounding box (a shape's area ≤ its bounding rectangle).
- Used Pythagoras only on a RIGHT triangle? Hypotenuse is the longest side / opposite the right angle?
