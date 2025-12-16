# `convert_pressure_to_line_loads_by_exposure_depth` — Detailed Notes (Full Explanation)

## Purpose
This function builds a **beam-load “plan”** (a table) from:
- a **uniform pressure** (e.g., wind pressure) in **ksf** (kips/ft²), and
- a per-element **exposure depth** in **ft**

It converts pressure to a **uniform line load** per element in **k/ft** using:

`q (k/ft) = pressure (ksf) * depth (ft)`

It returns a **pandas DataFrame** where each row describes the load to apply to one element, plus metadata like load case and direction.

---

## Function code (reference)

```python
def convert_pressure_to_line_loads_by_exposure_depth(
    *,
    group_name: str,
    load_case_name: str,
    pressure: float,
    udl_direction: str,
    depth_by_eid: Dict[int, float],
    load_group_name: str | None = None,
) -> pd.DataFrame:
    rows: list[dict] = []

    for eid, depth in (depth_by_eid or {}).items():
        q = float(pressure) * float(depth)  # ksf * ft = k/ft
        if abs(q) < EPS:
            continue
        rows.append(
            {
                "element_id": int(eid),
                "line_load": float(q),
                "load_case": str(load_case_name),
                "load_direction": str(udl_direction),
                "load_group": str(load_group_name or load_case_name),
                "group_name": str(group_name),
            }
        )

    df = pd.DataFrame(rows)
    if not df.empty:
        df.sort_values("element_id", inplace=True)
        df.reset_index(drop=True, inplace=True)
    return df
```

---

## Parameters (what each input means)

### Keyword-only arguments (`*`)
The `*` means you **must** call the function using **named (keyword) arguments**, not positional ones.

Valid call (keyword args):
```python
plan = convert_pressure_to_line_loads_by_exposure_depth(
    group_name="WALL_A",
    load_case_name="WIND+X",
    pressure=0.02,
    udl_direction="GY",
    depth_by_eid={101: 3.5, 102: 0.0},
)
```

Invalid call (positional args) — will error:
```python
plan = convert_pressure_to_line_loads_by_exposure_depth(
    "WALL_A", "WIND+X", 0.02, "GY", {101: 3.5}
)
```

### `group_name: str`
A label describing the element group you’re building loads for (used as metadata in the output).

Example: `"WALL_A"`, `"ROOF_EDGE"`, `"FRAME_LINE_1"`

### `load_case_name: str`
The load case name to tag each row with.

Example: `"WIND+X"`, `"WIND-Y"`

### `pressure: float`
Uniform pressure in **ksf**.

Example: `0.02` ksf (which equals 20 psf because 1 ksf = 1000 psf)

### `udl_direction: str`
Direction string for the beam line load (metadata field).

Example: `"GX"`, `"GY"`, `"GZ"` (depends on your convention)

### `depth_by_eid: Dict[int, float]`
Dictionary mapping **element id → exposure depth** (ft).

Example:
```python
{
  101: 3.5,  # element 101 has 3.5 ft exposure depth
  102: 2.0,  # element 102 has 2.0 ft exposure depth
  103: 0.0,  # element 103 has no exposure depth (will be skipped)
}
```

### `load_group_name: str | None = None`
Optional grouping label. If not provided, it defaults to `load_case_name`.

- If `load_group_name="WIND_GROUP_1"` → output column `load_group` = `"WIND_GROUP_1"`
- If `load_group_name=None` → output column `load_group` = `load_case_name`

---

## Outputs (DataFrame columns)

Each row in the returned DataFrame includes:

- `element_id` (int): the beam element id
- `line_load` (float): computed **k/ft**
- `load_case` (str): from `load_case_name`
- `load_direction` (str): from `udl_direction`
- `load_group` (str): `load_group_name` if provided else `load_case_name`
- `group_name` (str): from `group_name`

---

## Line-by-line explanation (what each line does)

### 1) Create an empty list to collect rows
```python
rows: list[dict] = []
```
This list will hold one dictionary per element that gets a non-zero load.

---

### 2) Loop over the element-depth map safely
```python
for eid, depth in (depth_by_eid or {}).items():
```

Why `(depth_by_eid or {})`?

- If `depth_by_eid` is a normal dict → use it
- If `depth_by_eid` is `None` (or empty) → use `{}` so the loop won’t crash

Examples:
- `depth_by_eid=None` → becomes `{}` → loop runs 0 times → returns empty DataFrame
- `depth_by_eid={}` → loop runs 0 times → returns empty DataFrame

---

### 3) Compute line load for this element
```python
q = float(pressure) * float(depth)  # ksf * ft = k/ft
```

- Converts `pressure` and `depth` to floats (defensive conversion)
- Computes the line load

Example:
- `pressure = 0.02` ksf
- `depth = 3.5` ft
- `q = 0.02 * 3.5 = 0.07` k/ft

Unit check:
- ksf = k/ft²
- multiply by ft → k/ft ✅

---

### 4) Skip loads that are effectively zero
```python
if abs(q) < EPS:
    continue
```

- `EPS` is a small tolerance constant (example: `1e-9`)
- This avoids adding rows for:
  - exact zeros, or
  - tiny floating-point noise values

Examples (assume `EPS = 1e-9`):
- `q = 0.0` → `abs(q) < EPS` → skip
- `q = 1e-12` → skip
- `q = 1e-6` → keep

---

### 5) Add a row dict for this element
```python
rows.append(
    {
        "element_id": int(eid),
        "line_load": float(q),
        "load_case": str(load_case_name),
        "load_direction": str(udl_direction),
        "load_group": str(load_group_name or load_case_name),
        "group_name": str(group_name),
    }
)
```

What each field does:

- `"element_id": int(eid)`
  - Ensures the element id is an integer

- `"line_load": float(q)`
  - Ensures the computed line load is a float

- `"load_case": str(load_case_name)`
  - Ensures load case is stored as a string

- `"load_direction": str(udl_direction)`
  - Ensures direction is stored as a string

- `"load_group": str(load_group_name or load_case_name)`
  - If `load_group_name` is provided (truthy), use it
  - Otherwise use `load_case_name`

  Examples:
  - `load_group_name="WIND_GRP"` → `"load_group"="WIND_GRP"`
  - `load_group_name=None` → `"load_group"=load_case_name`

- `"group_name": str(group_name)`
  - Ensures group name is stored as a string

---

### 6) Convert the row list into a DataFrame
```python
df = pd.DataFrame(rows)
```

If `rows` is empty, `df` is an empty DataFrame with no rows.

---

### 7) If not empty: sort and reset index
```python
if not df.empty:
    df.sort_values("element_id", inplace=True)
    df.reset_index(drop=True, inplace=True)
```

- `df.sort_values("element_id", inplace=True)`
  - Sorts rows in ascending order of `element_id`
  - `inplace=True` modifies `df` directly

- `df.reset_index(drop=True, inplace=True)`
  - Replaces the index with 0..N-1
  - `drop=True` avoids keeping the old index as a column

Why do this?
- Sorting makes the plan deterministic and easier to read/debug
- Resetting index gives a clean index after sorting

---

### 8) Return the DataFrame
```python
return df
```

---

## Worked Example (complete)

Inputs:
```python
group_name = "WALL_A"
load_case_name = "WIND+X"
pressure = 0.02     # ksf
udl_direction = "GY"
depth_by_eid = {
    101: 3.5,   # ft
    102: 2.0,   # ft
    103: 0.0,   # ft -> should be skipped (q=0)
}
load_group_name = None
```

Per-element computations:
- Element 101: `q = 0.02 * 3.5 = 0.07 k/ft`
- Element 102: `q = 0.02 * 2.0 = 0.04 k/ft`
- Element 103: `q = 0.02 * 0.0 = 0.0 k/ft` → skipped

Output DataFrame (conceptually):
```text
   element_id  line_load load_case load_direction load_group group_name
0         101       0.07   WIND+X            GY     WIND+X     WALL_A
1         102       0.04   WIND+X            GY     WIND+X     WALL_A
```

Note:
- `load_group` becomes `"WIND+X"` because `load_group_name` was `None`.

---

## Edge cases to be aware of

### `depth_by_eid` is `None`
```python
depth_by_eid = None
```
Result:
- loop runs 0 times
- returns empty DataFrame

### All depths are zero
```python
depth_by_eid = {101: 0.0, 102: 0.0}
```
Result:
- all computed `q` values are zero
- all rows skipped due to `EPS`
- returns empty DataFrame

### Negative pressure or depth
If `pressure` is negative (suction) or depth is negative (usually not expected), `q` can be negative.
The code allows it and will include it unless it’s near zero.

---

## Quick summary
- Iterates over `depth_by_eid`
- Computes `line_load = pressure * depth`
- Skips near-zero loads using `EPS`
- Builds a DataFrame with consistent typing (int/float/str)
- Sorts by element id and resets index
- Returns the plan DataFrame
