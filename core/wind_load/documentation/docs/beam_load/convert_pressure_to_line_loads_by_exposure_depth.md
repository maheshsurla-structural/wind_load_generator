# `convert_pressure_to_line_loads_by_exposure_depth` — Detailed Notes (Updated to match current function)

## Purpose

This function builds a **beam-load plan DataFrame** from:

- a **uniform pressure** `pressure` in **ksf** (kips/ft²), and
- a per-element **exposure depth** map `depth_by_eid` in **ft**

It converts pressure to a **uniform line load** per element in **k/ft** using:

```text
q (k/ft) = pressure (ksf) * depth (ft)
```

It returns a **pandas DataFrame** where each row describes the load to apply to one element, plus metadata like:
- load case
- load direction
- load group
- group name
- eccentricity

---

## Function code (current version)

```py
def convert_pressure_to_line_loads_by_exposure_depth(
    *,
    group_name: str,
    load_case_name: str,
    pressure: float,
    udl_direction: str,
    depth_by_eid: Dict[int, float],
    load_group_name: str | None = None,
    eccentricity: float = 0.0,
) -> pd.DataFrame:
    rows: list[dict] = []
    lc = str(load_case_name).strip()
    lg = str(load_group_name or lc).strip()

    for eid, depth in (depth_by_eid or {}).items():
        q = float(pressure) * float(depth)  # ksf * ft = k/ft
        if abs(q) < EPS:
            continue
        rows.append(
            {
                "element_id": int(eid),
                "line_load": float(q),
                "load_case": lc,
                "load_direction": str(udl_direction).strip(),
                "load_group": lg,
                "group_name": str(group_name).strip(),
                "eccentricity": float(eccentricity),
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
The `*` means you **must** call the function using **keyword arguments**.

✅ Valid:
```py
plan = convert_pressure_to_line_loads_by_exposure_depth(
    group_name="WALL_A",
    load_case_name="WIND+X",
    pressure=0.02,
    udl_direction="GY",
    depth_by_eid={101: 3.5, 102: 2.0},
)
```

❌ Invalid (positional):
```py
plan = convert_pressure_to_line_loads_by_exposure_depth(
    "WALL_A", "WIND+X", 0.02, "GY", {101: 3.5}
)
```

---

### `group_name: str`
Metadata label describing the group these elements belong to (stored in each output row).

Examples: `"GIRDER"`, `"WALL_A"`, `"PIER_LINE_1"`

---

### `load_case_name: str`
The load case name stored in output rows.

Example: `"WL_Q1"`, `"WIND+X_Q2"`

---

### `pressure: float`
Uniform pressure in **ksf** (kips/ft²).

Example: `0.02` ksf = 20 psf (since 1 ksf = 1000 psf).

---

### `udl_direction: str`
Direction label used by your beam-load system (metadata).

Examples: `"LX"`, `"LY"`, `"GX"`, `"GY"` (depends on your convention).

---

### `depth_by_eid: Dict[int, float]`
Mapping:

```py
{element_id: exposure_depth_ft}
```

Example:
```py
{
  101: 3.5,  # element 101 has 3.5 ft exposure
  102: 2.0,
  103: 0.0,  # will be skipped because q becomes ~0
}
```

---

### `load_group_name: str | None = None`
Optional group label for loads.
- If provided → used as `load_group`
- If not provided → defaults to `load_case_name` (after stripping)

---

### `eccentricity: float = 0.0`
Stored in each output row (often used as a load offset in the MIDAS beam-load definition).

This function **does not apply** eccentricity physically — it **records** the value for later use by the “apply-to-MIDAS” layer.

---

## Output (DataFrame columns)

Each row represents one element receiving a non-zero line load:

- `element_id` (int)
- `line_load` (float) — in **k/ft**
- `load_case` (str)
- `load_direction` (str)
- `load_group` (str)
- `group_name` (str)
- `eccentricity` (float)

---

## What changed vs the older version (important updates)

1) **Normalization of load case & load group happens once**
```py
lc = str(load_case_name).strip()
lg = str(load_group_name or lc).strip()
```
So the function:
- strips whitespace from `load_case_name`
- uses `load_case_name` as the fallback for `load_group_name`
- strips whitespace from that too

2) **Direction & group name are stripped**
```py
"load_direction": str(udl_direction).strip(),
"group_name": str(group_name).strip(),
```

3) **`eccentricity` is included in output**
```py
"eccentricity": float(eccentricity),
```

---

## Line-by-line explanation (current behavior)

### 1) Prepare row storage and normalize strings

```py
rows: list[dict] = []
lc = str(load_case_name).strip()
lg = str(load_group_name or lc).strip()
```

- `rows` collects one dict per element.
- `lc` becomes a clean load case name:
  - `"  WIND+X "` → `"WIND+X"`
- `lg` becomes a clean load group name:
  - if `load_group_name` is `None` → uses `lc`
  - otherwise uses the provided name
  - both are `.strip()`-ed

---

### 2) Loop over element depths safely

```py
for eid, depth in (depth_by_eid or {}).items():
```

- If `depth_by_eid` is `None`, `(depth_by_eid or {})` becomes `{}` and the loop runs zero times.
- If it’s an empty dict, loop also runs zero times.

---

### 3) Compute line load for each element

```py
q = float(pressure) * float(depth)  # ksf * ft = k/ft
```

Example:
- pressure = `0.02` ksf
- depth = `3.5` ft
- q = `0.02 * 3.5 = 0.07` k/ft

Unit check:
- ksf = k/ft²
- multiply by ft → k/ft ✅

---

### 4) Skip near-zero loads

```py
if abs(q) < EPS:
    continue
```

- `EPS` is a small tolerance (like `1e-9`)
- avoids adding “noise” rows for tiny floating point values

---

### 5) Add one row for this element

```py
rows.append(
    {
        "element_id": int(eid),
        "line_load": float(q),
        "load_case": lc,
        "load_direction": str(udl_direction).strip(),
        "load_group": lg,
        "group_name": str(group_name).strip(),
        "eccentricity": float(eccentricity),
    }
)
```

This ensures consistent typing:
- element id always int
- line load always float
- strings stripped
- eccentricity always float

---

### 6) Convert rows to DataFrame, sort, reset index

```py
df = pd.DataFrame(rows)
if not df.empty:
    df.sort_values("element_id", inplace=True)
    df.reset_index(drop=True, inplace=True)
return df
```

- Sorting makes output deterministic (useful for debugging and stable diffs)
- resetting index gives clean `0..N-1` row numbers

---

## Worked examples

### Example 1 — Basic conversion

Inputs:
```py
group_name = "WALL_A"
load_case_name = "  WIND+X  "
pressure = 0.02  # ksf
udl_direction = "  GY  "
depth_by_eid = {101: 3.5, 102: 2.0, 103: 0.0}
load_group_name = None
eccentricity = 0.25
```

Per-element:
- 101: q = 0.02 * 3.5 = 0.07 k/ft
- 102: q = 0.02 * 2.0 = 0.04 k/ft
- 103: q = 0.02 * 0.0 = 0.0 → skipped

Output DataFrame (conceptually):

```text
   element_id  line_load load_case load_direction load_group group_name  eccentricity
0         101      0.07   WIND+X           GY      WIND+X     WALL_A          0.25
1         102      0.04   WIND+X           GY      WIND+X     WALL_A          0.25
```

Notes:
- `load_case` stored as `"WIND+X"` (stripped)
- `load_direction` stored as `"GY"` (stripped)
- `load_group` stored as `"WIND+X"` because `load_group_name` was None
- `group_name` stored as `"WALL_A"` (stripped)
- `eccentricity` stored as `0.25`

---

### Example 2 — Explicit load group name

```py
plan = convert_pressure_to_line_loads_by_exposure_depth(
    group_name="PIER",
    load_case_name="WIND-Z",
    pressure=-0.015,
    udl_direction="GZ",
    depth_by_eid={2001: 4.0, 2002: 4.0},
    load_group_name="WIND_SERVICE",
    eccentricity=0.0,
)
```

Per-element:
- q = -0.015 * 4.0 = -0.06 k/ft

Output will have:
- `load_group = "WIND_SERVICE"`
- `line_load = -0.06` for both elements

---

### Example 3 — `depth_by_eid` is None or empty

```py
convert_pressure_to_line_loads_by_exposure_depth(
    group_name="G1",
    load_case_name="W1",
    pressure=0.02,
    udl_direction="GY",
    depth_by_eid=None,   # or {}
)
```

Result: empty DataFrame (no rows).

---

## Edge cases / behavior notes

- If `eid` is not int-like (e.g. `"A12"`), `int(eid)` will raise a `ValueError` when building the row.
- Negative `pressure` is allowed (common for suction); it produces negative `line_load`.
- Eccentricity is **recorded**, not applied inside this function.

---

## Quick summary

- Normalize `load_case_name` and `load_group_name` once (`strip()`)
- Loop `depth_by_eid`
- Compute `line_load = pressure * depth`
- Skip near-zero values using `EPS`
- Create a plan DataFrame with deterministic sorting and an `eccentricity` column
