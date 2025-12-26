## `_QUAD_SIGNS` and `apply_quadrant_sign_convention(q: int, t: float, l: float) -> tuple[float, float]`

These define and apply a **quadrant-based sign convention** to a pair of coefficients:

- `t` = transverse coefficient
- `l` = longitudinal coefficient

The idea is:

1. Start with base magnitudes `(t, l)` for a given angle.
2. Use quadrant `q` (1–4) to decide which signs should be applied.
3. Return the signed pair `(t_signed, l_signed)`.

---

### Code (for reference)

```py
_QUAD_SIGNS: dict[int, tuple[int, int]] = {
    1: (+1, +1),
    2: (+1, -1),
    3: (-1, -1),
    4: (-1, +1),
}

def apply_quadrant_sign_convention(q: int, t: float, l: float) -> tuple[float, float]:
    """Apply quadrant signs to (t, l)."""
    ts, ls = _QUAD_SIGNS.get(int(q), _QUAD_SIGNS[1])
    return ts * float(t), ls * float(l)
```

---

## `_QUAD_SIGNS`

```py
_QUAD_SIGNS: dict[int, tuple[int, int]] = {
    1: (+1, +1),
    2: (+1, -1),
    3: (-1, -1),
    4: (-1, +1),
}
```

### Meaning

Each quadrant maps to a pair `(ts, ls)` where:

- `ts` is the sign multiplier for **transverse** (`t`)
- `ls` is the sign multiplier for **longitudinal** (`l`)

| Quadrant `q` | `ts` | `ls` | Meaning                     |
|-------------:|-----:|-----:|-----------------------------|
| 1            | +1   | +1   | `( +t, +l )`                |
| 2            | +1   | -1   | `( +t, -l )`                |
| 3            | -1   | -1   | `( -t, -l )`                |
| 4            | -1   | +1   | `( -t, +l )`                |

This pattern is consistent with a typical 2D sign convention where each quadrant flips one or both components.

---

## `apply_quadrant_sign_convention(...)`

```py
def apply_quadrant_sign_convention(q: int, t: float, l: float) -> tuple[float, float]:
    """Apply quadrant signs to (t, l)."""
    ts, ls = _QUAD_SIGNS.get(int(q), _QUAD_SIGNS[1])
    return ts * float(t), ls * float(l)
```

### Step-by-step behavior

#### 1) Normalize quadrant and pick sign multipliers

```py
ts, ls = _QUAD_SIGNS.get(int(q), _QUAD_SIGNS[1])
```

- `int(q)`:
  - Ensures `q` is treated as an integer (works even if `q="2"`).
- `_QUAD_SIGNS.get(key, default)`:
  - If `q` is one of `1..4`, returns `(ts, ls)` for that quadrant.
  - Otherwise returns the default `_QUAD_SIGNS[1]` → `(+1, +1)`.

So invalid/missing quadrants behave like Q1.

Examples:

- `q=3` → `ts, ls = (-1, -1)`
- `q="2"` → `int("2") = 2` → `ts, ls = (+1, -1)`
- `q=99` → not found → default to Q1 → `ts, ls = (+1, +1)`

---

#### 2) Apply signs to the coefficients

```py
return ts * float(t), ls * float(l)
```

- Coerces `t` and `l` to floats (works if they are numeric strings like `"0.3"`).
- Multiplies by the quadrant sign multipliers.
- Returns a tuple `(t_signed, l_signed)`.

---

## Examples

Let base coefficients be:

```py
t = 0.20
l = 1.10
```

### Quadrant 1 (no sign flips)

```py
apply_quadrant_sign_convention(1, 0.20, 1.10)
# (+1 * 0.20, +1 * 1.10) -> (0.20, 1.10)
```

### Quadrant 2 (flip longitudinal)

```py
apply_quadrant_sign_convention(2, 0.20, 1.10)
# (+1 * 0.20, -1 * 1.10) -> (0.20, -1.10)
```

### Quadrant 3 (flip both)

```py
apply_quadrant_sign_convention(3, 0.20, 1.10)
# (-1 * 0.20, -1 * 1.10) -> (-0.20, -1.10)
```

### Quadrant 4 (flip transverse)

```py
apply_quadrant_sign_convention(4, 0.20, 1.10)
# (-1 * 0.20, +1 * 1.10) -> (-0.20, 1.10)
```

### Quadrant missing/invalid (defaults to Q1)

```py
apply_quadrant_sign_convention(99, 0.20, 1.10)
# defaults to Q1 -> (0.20, 1.10)

apply_quadrant_sign_convention("2", "0.20", "1.10")
# q="2" -> quadrant 2
# t,l strings -> float conversion works
# -> (0.20, -1.10)
```

---

## Notes / gotchas

- Defaulting invalid quadrants to Q1 is intentional “fail-soft” behavior:
  - avoids crashing if quadrant parsing fails upstream
  - produces a predictable sign outcome
- If you prefer strict validation, you could raise on invalid `q` instead of defaulting.
- If `t` or `l` cannot be converted to float (e.g., `"abc"`), `float(...)` will raise a `ValueError`.
