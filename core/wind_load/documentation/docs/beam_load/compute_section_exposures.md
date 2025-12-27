# `compute_section_exposures` — Detailed Notes (Updated to match current function)

## Purpose

`compute_section_exposures` computes **local exposure depths** for each MIDAS section property record (i.e., section IDs used by elements).

It assumes each row in `section_properties` follows a MIDAS “section properties” layout where key offsets are stored at fixed indices:

- `COL_ID = 1` → **property/section id** (used as index)
- `COL_LEFT = 11`, `COL_RIGHT = 12` → used to compute **exposure_z**
- `COL_TOP = 13`, `COL_BOTTOM = 14` → used to compute **exposure_y**
- plus an optional **extra exposure in Y**:
  - a default extra (`extra_exposure_y_default`)
  - and optional per-section overrides (`extra_exposure_y_by_id`)

### Output options

- `as_dataframe=True` (default) → returns a **DataFrame** indexed by `property_id` with columns:
  - `exposure_y`
  - `exposure_z`

- `as_dataframe=False` → returns a **dict**:
  - `{property_id: (exposure_y, exposure_z)}`

---

## The function (current version)

```py
def compute_section_exposures(
    section_properties: Iterable,
    *,
    extra_exposure_y_default: float = 0.0,
    extra_exposure_y_by_id: Optional[Dict[int, float]] = None,
    as_dataframe: bool = True,
) -> pd.DataFrame | Dict[Any, Tuple[float, float]]:
    """
    Compute local exposure depths for all section properties.

    Assumes a MIDAS section property row layout with:
      - property id at COL_ID
      - left/right/top/bottom offsets at COL_LEFT/COL_RIGHT/COL_TOP/COL_BOTTOM

    Returns:
      DataFrame indexed by property_id with columns: exposure_y, exposure_z
      or dict[property_id] = (exposure_y, exposure_z)
    """
    COL_ID, COL_LEFT, COL_RIGHT, COL_TOP, COL_BOTTOM = 1, 11, 12, 13, 14

    pids: list[Any] = []
    left: list[float] = []
    right: list[float] = []
    top: list[float] = []
    bottom: list[float] = []

    for row in section_properties or []:
        if not row or len(row) <= COL_BOTTOM:
            continue
        try:
            pid = row[COL_ID]
            pids.append(pid)
            left.append(float(row[COL_LEFT]))
            right.append(float(row[COL_RIGHT]))
            top.append(float(row[COL_TOP]))
            bottom.append(float(row[COL_BOTTOM]))
        except (TypeError, ValueError):
            continue

    if not pids:
        return pd.DataFrame(columns=["exposure_y", "exposure_z"]) if as_dataframe else {}

    pids_arr = np.asarray(pids, dtype=object)
    left_arr = np.asarray(left, dtype=float)
    right_arr = np.asarray(right, dtype=float)
    top_arr = np.asarray(top, dtype=float)
    bottom_arr = np.asarray(bottom, dtype=float)

    if extra_exposure_y_by_id:
        extra_y = np.fromiter(
            (extra_exposure_y_by_id.get(int(pid), extra_exposure_y_default) for pid in pids_arr),
            dtype=float,
            count=pids_arr.size,
        )
    else:
        extra_y = np.full(pids_arr.size, extra_exposure_y_default, dtype=float)

    exposure_y = top_arr + bottom_arr + extra_y
    exposure_z = left_arr + right_arr

    if as_dataframe:
        df = pd.DataFrame({"exposure_y": exposure_y, "exposure_z": exposure_z}, index=pids_arr)
        df.index.name = "property_id"
        # Normalize index for reliable .loc lookups where sect_id is int
        try:
            df.index = df.index.astype(int)
        except Exception:
            pass
        return df

    return {pids_arr[i]: (float(exposure_y[i]), float(exposure_z[i])) for i in range(pids_arr.size)}
```

---

## Inputs (parameters)

### `section_properties: Iterable`
An iterable of “rows” (typically lists/tuples) from MIDAS section-property data.

Each row must be long enough to read indices up to `14` and contain numeric values at:

- `row[11]`, `row[12]`, `row[13]`, `row[14]`

### `extra_exposure_y_default: float = 0.0`
Adds a constant extra exposure to **every** section’s **Y exposure** unless overridden by `extra_exposure_y_by_id`.

### `extra_exposure_y_by_id: Optional[Dict[int, float]] = None`
Overrides of extra Y exposure **per property id**.

Important detail in the current function:
- it does `int(pid)` when reading this dict:

```py
extra_exposure_y_by_id.get(int(pid), extra_exposure_y_default)
```

So your override keys should be **integers**, and `pid` must be int-like for overrides to work.

### `as_dataframe: bool = True`
- `True` → DataFrame output
- `False` → dict output

---

## What it computes

For each section/property id (`pid`):

### Exposure in Y

```text
exposure_y = top + bottom + extra_y
```

### Exposure in Z

```text
exposure_z = left + right
```

Where `extra_y` is:

- if overrides provided:
  - `extra_exposure_y_by_id.get(int(pid), extra_exposure_y_default)`
- else:
  - `extra_exposure_y_default` for all

---

## Step-by-step explanation (current behavior)

### 1) Define the “column indices” (hard-coded MIDAS layout)

```py
COL_ID, COL_LEFT, COL_RIGHT, COL_TOP, COL_BOTTOM = 1, 11, 12, 13, 14
```

This is the contract: your MIDAS section row must match these positions.

---

### 2) Parse rows into parallel lists

```py
for row in section_properties or []:
    if not row or len(row) <= COL_BOTTOM:
        continue
    try:
        pid = row[COL_ID]
        pids.append(pid)
        left.append(float(row[COL_LEFT]))
        right.append(float(row[COL_RIGHT]))
        top.append(float(row[COL_TOP]))
        bottom.append(float(row[COL_BOTTOM]))
    except (TypeError, ValueError):
        continue
```

What this does:

- `section_properties or []` prevents errors if `section_properties` is `None`.
- Skips rows that are:
  - missing
  - too short (cannot access index 14)
  - contain non-numeric offset values (cannot convert to float)

Only valid rows contribute to the exposure results.

---

### 3) If nothing valid was parsed, return empty output

```py
if not pids:
    return pd.DataFrame(columns=["exposure_y", "exposure_z"]) if as_dataframe else {}
```

---

### 4) Convert lists to NumPy arrays for vectorized math

```py
pids_arr = np.asarray(pids, dtype=object)
left_arr = np.asarray(left, dtype=float)
right_arr = np.asarray(right, dtype=float)
top_arr = np.asarray(top, dtype=float)
bottom_arr = np.asarray(bottom, dtype=float)
```

- `pids_arr` is `dtype=object` to allow mixed ID types safely.
- numeric arrays are `float` for fast computation.

---

### 5) Build `extra_y` (override-aware)

#### A) Overrides provided

```py
extra_y = np.fromiter(
    (extra_exposure_y_by_id.get(int(pid), extra_exposure_y_default) for pid in pids_arr),
    dtype=float,
    count=pids_arr.size,
)
```

Notes:
- each `pid` is converted with `int(pid)` before lookup
- if `pid` cannot be converted to int, this generator will raise (so practically `pid` should be int-like)

#### B) No overrides provided

```py
extra_y = np.full(pids_arr.size, extra_exposure_y_default, dtype=float)
```

---

### 6) Compute exposures (vectorized)

```py
exposure_y = top_arr + bottom_arr + extra_y
exposure_z = left_arr + right_arr
```

---

### 7) DataFrame output (default)

```py
df = pd.DataFrame({"exposure_y": exposure_y, "exposure_z": exposure_z}, index=pids_arr)
df.index.name = "property_id"
try:
    df.index = df.index.astype(int)
except Exception:
    pass
return df
```

Important “updated” detail:
- it tries to convert index to `int`, so later code can do:

```py
exposures_df.loc[sect_id, "exposure_y"]
```

where `sect_id` is an integer.

If conversion fails (e.g., IDs are non-numeric strings), it silently keeps the original index type.

---

### 8) Dict output (if `as_dataframe=False`)

```py
return {pids_arr[i]: (float(exposure_y[i]), float(exposure_z[i])) for i in range(pids_arr.size)}
```

Values are forced to Python floats (not NumPy scalars).

---

## Worked examples (realistic + detailed)

### Helper: create “MIDAS-like” rows

The function expects rows long enough to include index 14.
A quick way to build rows for examples:

```py
def mk_row(pid, left, right, top, bottom):
    r = [None] * 15
    r[1] = pid
    r[11] = left
    r[12] = right
    r[13] = top
    r[14] = bottom
    return r
```

---

### Example 1 — basic computation (no overrides)

```py
section_properties = [
    mk_row(101, left=1.2, right=0.8, top=2.0, bottom=1.0),
    mk_row(102, left=1.0, right=1.0, top=1.5, bottom=1.5),
]

df = compute_section_exposures(section_properties, as_dataframe=True)
```

Per property:

- `pid=101`
  - exposure_y = 2.0 + 1.0 + 0.0 = 3.0
  - exposure_z = 1.2 + 0.8 = 2.0

- `pid=102`
  - exposure_y = 1.5 + 1.5 + 0.0 = 3.0
  - exposure_z = 1.0 + 1.0 = 2.0

Result:

```text
             exposure_y  exposure_z
property_id
101                 3.0         2.0
102                 3.0         2.0
```

---

### Example 2 — default extra exposure applied to all sections

```py
df = compute_section_exposures(
    section_properties,
    extra_exposure_y_default=0.25,
    as_dataframe=True,
)
```

- pid=101: exposure_y = 2.0 + 1.0 + 0.25 = 3.25
- pid=102: exposure_y = 1.5 + 1.5 + 0.25 = 3.25

exposure_z unchanged.

---

### Example 3 — per-section overrides

```py
df = compute_section_exposures(
    section_properties,
    extra_exposure_y_default=0.2,
    extra_exposure_y_by_id={101: 0.5},  # override only for 101
    as_dataframe=True,
)
```

Important: keys are ints and lookup uses `int(pid)`.

- pid=101:
  - extra_y = 0.5 (override)
  - exposure_y = 2.0 + 1.0 + 0.5 = 3.5
- pid=102:
  - extra_y = 0.2 (default)
  - exposure_y = 1.5 + 1.5 + 0.2 = 3.2

---

### Example 4 — dict output

```py
out = compute_section_exposures(section_properties, as_dataframe=False)
```

Output:

```py
{
  101: (3.0, 2.0),
  102: (3.0, 2.0),
}
```

---

### Example 5 — row skipped due to bad data

```py
section_properties = [
    mk_row(101, 1.0, 1.0, 2.0, 1.0),
    mk_row(102, "N/A", 1.0, 2.0, 1.0),  # left is not float-convertible
]
```

Row for 102 is skipped due to `ValueError` inside `float("N/A")`.

Output contains only pid 101.

---

## Edge cases / updated behavior notes

- **Rows too short** (no index 14) are skipped.
- **Non-numeric offsets** cause that entire row to be skipped.
- **Overrides dict uses `int(pid)`**:
  - if `pid` is `"101"` it still works (int("101") = 101)
  - if `pid` is `"S101"` it will fail if overrides are enabled (int("S101") raises)
- DataFrame output tries to cast the **index to int** for reliable `.loc[sect_id]` usage.
  - if the cast fails, it silently keeps the original index.

---

## Quick summary

- Extracts section offsets from fixed indices (MIDAS layout).
- Computes:
  - `exposure_y = top + bottom + extra_y`
  - `exposure_z = left + right`
- Supports:
  - global Y extras (`extra_exposure_y_default`)
  - per-property Y extras (`extra_exposure_y_by_id`, keyed by int section IDs)
- Returns:
  - DataFrame (default) with an int index when possible
  - or a dict mapping `{property_id: (exposure_y, exposure_z)}`
