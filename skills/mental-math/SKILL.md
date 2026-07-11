---
name: mental-math
description: Use for any arithmetic - multiplication, division, squares, quick estimation, divisibility - especially multi-digit calculations where errors creep in. Provides decomposition tricks and verification via digit checks.
category: math
hint: reliable arithmetic tricks and verification
---
# Mental Math — Reliable Arithmetic

Rule zero: **never do a multi-digit operation in one leap.** Decompose, write intermediates, verify.

## Addition / subtraction

- Left to right by place value: 487+256 → 400+200=600, 80+50=130, 7+6=13 → 600+130+13 = 743.
- Complements: 1000−487 = 513 (each digit to 9, last to 10).
- Subtract by adding up: 823−467 → 467+33=500, +323=823 → 33+323 = 356.

## Multiplication

- **Distribute**: 23×47 = 23×40 + 23×7 = 920+161 = 1081.
- **Round and correct**: 49×36 = 50×36 − 36 = 1800−36 = 1764.
- **Factor**: 24×35 = 24×5×7 = 120×7 = 840. ×5 = ×10÷2. ×25 = ×100÷4. ×11: 43×11 → 4_(4+3)_3 = 473 (carry when the middle sum ≥10).
- **Difference of squares**: (a−b)(a+b)=a²−b². 38×42 = 40²−2² = 1596. 97×103 = 10000−9 = 9991.
- **Squares near a base**: 47² = (47−3)(47+3)+3² = 44×50+9 = 2209. Numbers ending in 5: 65² = 6×7 then 25 → 4225.

## Division & fractions

- Simplify before dividing: 168/24 = 7 (cancel 24 = 8×3: 168÷8=21, 21÷3=7).
- Divide by 5 → multiply by 2, shift decimal: 340/5 = 68.
- Decimal anchors: 1/8=0.125, 1/6≈0.1667, 1/3≈0.3333, 3/8=0.375, 5/8=0.625, 7/8=0.875, 1/7≈0.1429, 1/9=0.111….
- Fraction addition needs a common denominator: 1/3 + 1/4 = 7/12, never 2/7. (Adding tops and bottoms is the classic error.)

## Divisibility tests

- 2: last digit even. 4: last two digits divisible by 4. 8: last three by 8.
- 3: digit sum divisible by 3. 9: digit sum divisible by 9.
- 5: ends in 0/5. 6: passes both 2 and 3. 11: alternating digit sum (±) divisible by 11.
- 7: double the last digit, subtract from the rest, repeat (343 → 34−6=28 ✓).

## Powers & roots to know

2ⁿ: 2,4,8,16,32,64,128,256,512,1024 (2¹⁰≈10³ — the key to big-number estimates). Squares to 25²=625 memorized; cubes to 10³. √2≈1.414, √3≈1.732, √5≈2.236, √10≈3.162. π≈3.14159, e≈2.71828.

## Estimation before exact

Always compute a rough answer first (round everything to 1 significant figure), then the exact one. 487×213 ≈ 500×200 = 100,000; exact 103,731 — consistent ✓. If exact and estimate disagree by more than ~2×, redo the exact.

## Verification

- **Casting out nines**: digit-sum every operand mod 9; the operation on the sums must match the digit sum of the result. 47×62=2914? 47→2, 62→8, 2×8=16→7; 2914→2+9+1+4=16→7 ✓. Catches most digit errors.
- **Last-digit check**: last digit of a product = product of last digits mod 10. 23×47 must end in 1 (3×7=21).
- **Parity**: odd×odd is odd; sum of two odds is even.
- **Magnitude**: count digits. A 2-digit × 3-digit number has 4 or 5 digits — no exceptions.
