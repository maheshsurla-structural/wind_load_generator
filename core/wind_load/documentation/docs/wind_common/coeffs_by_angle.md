## `coeffs_by_angle(...) -> Dict[int, Tuple[float, float]]`

Build a lookup table of aerodynamic coefficients keyed by **angle**:

- **Return type:** `{angle:int -> (T:float, L:float)}`
- **Where:**
  - `T` = transverse coefficient
  - `L` = longitudinal coefficient

This function is designed specifically for **Control Data** where the angle rows are fixed and non-editable.

```py
CONTROL_ANGLES: tuple[int, ...] = (0, 15, 30, 45, 60)
```

The function assumes:

- there are exactly **5 rows**
- row `i` corresponds to `CONTROL_ANGLES[i]`
- inputs must be numeric (or numeric-like) and complete

---

### Code (for reference)

```py
CONTROL_ANGLES: tuple[int, ...] = (0, 15, 30, 45, 60)


def coeffs_by_angle(
    *,
    angles: Sequence[Any],
    transverse: Sequence[Any],
    longitudinal: Sequence[Any],
    table_name: str = "coeffs",
    require_unique_angles: bool = True,
) -> Dict[int, Tuple[float, float]]:
    """
    Returns {angle:int -> (T:float, L:float)}.

    Designed for Control Data usage where angles are fixed and non-editable:
    CONTROL_ANGLES = (0, 15, 30, 45, 60)
    """
    if angles is None:
        raise ValueError(f"{table_name}: angles is None")

    # Fail-fast: control angles must match exactly (catches wrong table/order/wiring).
    try:
        angs = tuple(int(a) for a in angles)
    except (TypeError, ValueError):
        raise ValueError(f"{table_name}: angles must be integer-like; got {list(angles)!r}")

    if require_unique_angles and angs != CONTROL_ANGLES:
        raise ValueError(f"{table_name}: angles must be exactly {list(CONTROL_ANGLES)} (got {list(angs)})")

    n = len(CONTROL_ANGLES)
    if not (len(transverse) == len(longitudinal) == n):
        raise ValueError(
            f"{table_name}: expected {n} transverse/longitudinal values "
            f"(got {len(transverse)}, {len(longitudinal)})"
        )

    def _to_float(x: Any, kind: str, i: int) -> float:
        if isinstance(x, str) and not x.strip():
            raise ValueError(f"{table_name}: blank {kind} at row {i} (angle={CONTROL_ANGLES[i]})")
        try:
            return float(x)
        except (TypeError, ValueError):
            raise ValueError(
                f"{table_name}: non-numeric {kind} at row {i} (angle={CONTROL_ANGLES[i]}): {x!r}"
            )

    return {
        CONTROL_ANGLES[i]: (_to_float(transverse[i], "transverse", i), _to_float(longitudinal[i], "longitudinal", i))
        for i in range(n)
    }
```

---

## Purpose and design

This function is meant for cases where:

- the set of angles is **fixed** (`0, 15, 30, 45, 60`)
- the UI/table is wired to always provide those rows
- you want to fail immediately if the data is miswired, reordered, or incomplete

It is intentionally “fail-fast” to avoid subtle bugs where coefficient rows get attached to the wrong angles.

---

## Parameters

- `angles: Sequence[Any]`
  - The angles column from a control table (ideally `[0, 15, 30, 45, 60]`).
  - Values must be “integer-like” (convertible to `int`).

- `transverse: Sequence[Any]`
  - Transverse coefficients for each angle row.

- `longitudinal: Sequence[Any]`
  - Longitudinal coefficients for each angle row.

- `table_name: str = "coeffs"`
  - Used only for more informative error messages (helpful when multiple tables call this function).

- `require_unique_angles: bool = True`
  - When `True`, enforces that `angles` matches `CONTROL_ANGLES` **exactly** (same values *and* order).
  - This protects against wrong table wiring, reordered rows, or incorrect input.

---

## Step-by-step behavior (with examples)

### 1) Reject missing `angles`

```py
if angles is None:
    raise ValueError(f"{table_name}: angles is None")
```

If `angles` is `None`, the function cannot validate row mapping.

Example:

```py
coeffs_by_angle(angles=None, transverse=[...], longitudinal=[...])
# raises: "coeffs: angles is None"
```

---

### 2) Convert angles to integers (“integer-like” validation)

```py
try:
    angs = tuple(int(a) for a in angles)
except (TypeError, ValueError):
    raise ValueError(f"{table_name}: angles must be integer-like; got {list(angles)!r}")
```

This enforces that every value in `angles` can become an `int`.

Examples:

```py
angles = [0, 15, 30, 45, 60]          -> angs = (0, 15, 30, 45, 60)
angles = ["0", "15", "30", "45", "60"] -> angs = (0, 15, 30, 45, 60)
angles = ["0", "15deg", "30", ...]     -> raises (because int("15deg") fails)
```

Error example:

```py
angles = ["0", "15deg", "30", "45", "60"]
# raises: "coeffs: angles must be integer-like; got ['0', '15deg', '30', '45', '60']"
```

---

### 3) Fail-fast: require control angles to match exactly (values + order)

```py
if require_unique_angles and angs != CONTROL_ANGLES:
    raise ValueError(...)
```

This is the key guard for ordering correctness.

Because tuple equality is element-by-element:

- `(0, 15, 30, 45, 60)` ✅ matches
- `(0, 30, 15, 45, 60)` ❌ fails (15 and 30 swapped)
- `(0, 15, 30)` ❌ fails (length mismatch)
- `(0, 15, 30, 45, 75)` ❌ fails (wrong value)

Example (bad order):

```py
angles = [0, 30, 15, 45, 60]
# raises: "coeffs: angles must be exactly [0, 15, 30, 45, 60] (got [0, 30, 15, 45, 60])"
```

> Why this matters: the return mapping uses `CONTROL_ANGLES[i]` as keys (not `angles[i]`), so row order must match `CONTROL_ANGLES` to avoid mis-assignment.

---

### 4) Validate lengths of coefficient columns

```py
n = len(CONTROL_ANGLES)
if not (len(transverse) == len(longitudinal) == n):
    raise ValueError(...)
```

This enforces that you have exactly one transverse and one longitudinal value per control angle.

Example (missing one longitudinal value):

```py
transverse   = [0.1, 0.2, 0.3, 0.4, 0.5]
longitudinal = [1.0, 1.1, 1.2, 1.3]           # length 4
# raises: "coeffs: expected 5 transverse/longitudinal values (got 5, 4)"
```

---

### 5) Convert each coefficient to float with strict error messages

```py
def _to_float(x: Any, kind: str, i: int) -> float:
    if isinstance(x, str) and not x.strip():
        raise ValueError(...)
    try:
        return float(x)
    except (TypeError, ValueError):
        raise ValueError(...)
```

Two important validations happen here:

#### A) Reject blank strings explicitly

- `""` or `"   "` are treated as *missing values* and rejected with a clear message.
- This gives a better message than `float("")` would.

Example:

```py
transverse = ["", 0.2, 0.3, 0.4, 0.5]
# raises: "coeffs: blank transverse at row 0 (angle=0)"
```

#### B) Reject non-numeric values

Example:

```py
longitudinal = [1.0, "bad", 1.2, 1.3, 1.4]
# raises: "coeffs: non-numeric longitudinal at row 1 (angle=15): 'bad'"
```

---

### 6) Build and return `{angle -> (T, L)}`

```py
return {
    CONTROL_ANGLES[i]: (_to_float(transverse[i], "transverse", i), _to_float(longitudinal[i], "longitudinal", i))
    for i in range(n)
}
```

For each row index `i`:

- key = `CONTROL_ANGLES[i]`
- value = `(float(transverse[i]), float(longitudinal[i]))`

---

## Successful example

Input:

```py
angles = [0, 15, 30, 45, 60]
transverse =   [0.10, 0.20, 0.30, 0.40, 0.50]
longitudinal = [1.00, 1.10, 1.20, 1.30, 1.40]
```

Output:

```py
{
  0:  (0.10, 1.00),
  15: (0.20, 1.10),
  30: (0.30, 1.20),
  45: (0.40, 1.30),
  60: (0.50, 1.40),
}
```

---

## Common failure scenarios and messages

### Wrong angles (reordered)

```py
angles = [0, 30, 15, 45, 60]
```

Raises:

- `"coeffs: angles must be exactly [0, 15, 30, 45, 60] (got [0, 30, 15, 45, 60])"`

### Wrong lengths

```py
transverse = [0.1, 0.2, 0.3, 0.4, 0.5]
longitudinal = [1.0, 1.1, 1.2, 1.3]
```

Raises:

- `"coeffs: expected 5 transverse/longitudinal values (got 5, 4)"`

### Blank cell

```py
transverse = [" ", 0.2, 0.3, 0.4, 0.5]
```

Raises:

- `"coeffs: blank transverse at row 0 (angle=0)"`

### Non-numeric cell

```py
longitudinal = [1.0, "abc", 1.2, 1.3, 1.4]
```

Raises:

- `"coeffs: non-numeric longitudinal at row 1 (angle=15): 'abc'"`

---

## Notes

- `require_unique_angles=True` is essential in the current implementation because the mapping keys are `CONTROL_ANGLES[i]`, not `angs[i]`.
- If you want to support arbitrary angles, the return keys would need to be `angs[i]` instead — that’s a different design.
