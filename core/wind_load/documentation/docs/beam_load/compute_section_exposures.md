# `compute_section_exposures` — Detailed Notes (Full Explanation)

## Purpose
This function computes **local exposure depths** for each **section property** (MIDAS “SECT” style row data).

It assumes each section property row contains offsets at fixed column indices:

- `COL_ID` (property id)
- `COL_LEFT`, `COL_RIGHT`  → used to compute **exposure_z**
- `COL_TOP`, `COL_BOTTOM`  → used to compute **exposure_y**
- plus an optional **extra exposure in Y** (default or per-property override)

### Output options
- If `as_dataframe=True` (default): returns a **DataFrame** indexed by `property_id` with columns:
  - `exposure_y`
  - `exposure_z`
- If `as_dataframe=False`: returns a **dict**:
  - `{property_id: (exposure_y, exposure_z)}`

---

## Function code (reference)

```python
def compute_section_exposures(
    section_properties,
    extra_exposure_y_default: float = 0.0,
    extra_exposure_y_by_id: dict | None = None,
    as_dataframe: bool = True,
) -> pd.DataFrame | dict:
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
            (extra_exposure_y_by_id.get(pid, extra_exposure_y_default) for pid in pids_arr),
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
        return df

    return {pids_arr[i]: (float(exposure_y[i]), float(exposure_z[i])) for i in range(pids_arr.size)}
```

---

## Inputs (parameters)

### `section_properties`
A sequence of “rows” (usually lists) representing MIDAS section property data.  
Each row must have at least up to index `COL_BOTTOM` (14), because we read:

- `row[1]`  → property id
- `row[11]` → left offset
- `row[12]` → right offset
- `row[13]` → top offset
- `row[14]` → bottom offset

> Important: These are **hard-coded positions** that match your assumed MIDAS layout.

### `extra_exposure_y_default: float = 0.0`
A constant extra Y exposure added to **every** property unless overridden by `extra_exposure_y_by_id`.

### `extra_exposure_y_by_id: dict | None = None`
Optional overrides: `{property_id: extra_y}`.  
If provided, each property id can get a custom extra exposure in Y.

### `as_dataframe: bool = True`
Controls output format:
- `True` → DataFrame
- `False` → dict

---

## High-level computation (what it calculates)

For each property id (`pid`), compute:

### Exposure in Y
```text
exposure_y = top + bottom + extra_y
```

### Exposure in Z
```text
exposure_z = left + right
```

Where:
- `extra_y` is either:
  - `extra_exposure_y_by_id.get(pid, extra_exposure_y_default)` (per-id override), or
  - `extra_exposure_y_default` for all

---

## Line-by-line explanation

### 1) Column index definitions
```python
COL_ID, COL_LEFT, COL_RIGHT, COL_TOP, COL_BOTTOM = 1, 11, 12, 13, 14
```

This tells the function where to find required fields in each `row` list.

Example row conceptually:
- `row[1]` = property id
- `row[11]` = left
- `row[12]` = right
- `row[13]` = top
- `row[14]` = bottom

---

### 2) Create lists to collect parsed values
```python
pids: list[Any] = []
left: list[float] = []
right: list[float] = []
top: list[float] = []
bottom: list[float] = []
```

These are “parallel arrays” (all same length), one entry per valid section property row.

---

### 3) Iterate over the section property rows safely
```python
for row in section_properties or []:
```

If `section_properties` is `None`, `(section_properties or [])` becomes `[]`, so the loop does not crash.

---

### 4) Validate the row shape before indexing
```python
if not row or len(row) <= COL_BOTTOM:
    continue
```

- If `row` is empty/None → skip
- If row does not have index 14 (COL_BOTTOM) → skip
  - because trying to access `row[14]` would cause an IndexError

---

### 5) Parse values with robust casting
```python
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
- Reads `pid` (no float cast, kept as-is)
- Converts left/right/top/bottom to float and appends

If any value can’t be converted to float (e.g., `"N/A"`), it skips the entire row.

---

### 6) If nothing valid was parsed, return an empty structure
```python
if not pids:
    return pd.DataFrame(columns=["exposure_y", "exposure_z"]) if as_dataframe else {}
```

- If all rows were invalid / missing data → return empty DataFrame or empty dict.

---

### 7) Convert lists to NumPy arrays (vectorized computation)
```python
pids_arr = np.asarray(pids, dtype=object)
left_arr = np.asarray(left, dtype=float)
right_arr = np.asarray(right, dtype=float)
top_arr = np.asarray(top, dtype=float)
bottom_arr = np.asarray(bottom, dtype=float)
```

Why convert to arrays?
- Enables fast, clean vectorized operations like:
  - `top_arr + bottom_arr + extra_y`

Also note:
- `pids_arr` uses `dtype=object` so property IDs can be ints/strings safely.

---

### 8) Build the `extra_y` array (per-id overrides OR constant default)
```python
if extra_exposure_y_by_id:
    extra_y = np.fromiter(
        (extra_exposure_y_by_id.get(pid, extra_exposure_y_default) for pid in pids_arr),
        dtype=float,
        count=pids_arr.size,
    )
else:
    extra_y = np.full(pids_arr.size, extra_exposure_y_default, dtype=float)
```

#### Case A: overrides provided (`extra_exposure_y_by_id` is truthy)
- For each `pid`, use:
  - `extra_exposure_y_by_id.get(pid, extra_exposure_y_default)`
- So each property id can have different extra Y exposure.

`np.fromiter(...)` builds a NumPy array efficiently from a generator.

#### Case B: no overrides
- Uses `np.full(...)` to make an array like:
  - `[extra_exposure_y_default, extra_exposure_y_default, ...]`

---

### 9) Compute exposures (vectorized)
```python
exposure_y = top_arr + bottom_arr + extra_y
exposure_z = left_arr + right_arr
```

This computes all properties at once (array math).

---

### 10) If requested, return as DataFrame
```python
if as_dataframe:
    df = pd.DataFrame({"exposure_y": exposure_y, "exposure_z": exposure_z}, index=pids_arr)
    df.index.name = "property_id"
    return df
```

- Creates a DataFrame with two columns:
  - `exposure_y`
  - `exposure_z`
- Index is the property IDs (`pids_arr`)
- Names the index `"property_id"` (helps readability/debugging)

---

### 11) Otherwise return as dict
```python
return {pids_arr[i]: (float(exposure_y[i]), float(exposure_z[i])) for i in range(pids_arr.size)}
```

Builds a dict like:
```python
{
  pid1: (exposure_y1, exposure_z1),
  pid2: (exposure_y2, exposure_z2),
  ...
}
```

`float(...)` ensures values are plain Python floats (not NumPy float types).

---

## Worked example (with sample input rows)

### Sample `section_properties`
Below, each row is a list where we only care about indices:
- 1, 11, 12, 13, 14

```python
section_properties = [
    # indices:    0    1     ...  11    12    13    14
    ["x",       10,   "...", 1.0,  1.5,  2.0,  0.5],  # <-- not enough length (example of invalid)
]
```

A realistic shaped row must be long enough to include index 14. Example:

```python
rowA = [None] * 15
rowA[1]  = 101     # pid
rowA[11] = 1.2     # left
rowA[12] = 0.8     # right
rowA[13] = 2.0     # top
rowA[14] = 1.0     # bottom

rowB = [None] * 15
rowB[1]  = 102
rowB[11] = 1.0
rowB[12] = 1.0
rowB[13] = 1.5
rowB[14] = 1.5

section_properties = [rowA, rowB]
```

### Example 1: No overrides, default extra Y = 0.0
Inputs:
```python
extra_exposure_y_default = 0.0
extra_exposure_y_by_id = None
```

Calculations:
- For pid 101:
  - exposure_y = top + bottom + extra = 2.0 + 1.0 + 0.0 = 3.0
  - exposure_z = left + right = 1.2 + 0.8 = 2.0
- For pid 102:
  - exposure_y = 1.5 + 1.5 + 0.0 = 3.0
  - exposure_z = 1.0 + 1.0 = 2.0

DataFrame result:
```text
             exposure_y  exposure_z
property_id
101                 3.0         2.0
102                 3.0         2.0
```

---

### Example 2: Overrides provided
Inputs:
```python
extra_exposure_y_default = 0.2
extra_exposure_y_by_id = {101: 0.5}  # override for pid 101 only
```

Now:
- For pid 101:
  - extra_y = 0.5 (override)
  - exposure_y = 2.0 + 1.0 + 0.5 = 3.5
- For pid 102:
  - extra_y = 0.2 (default, because no override)
  - exposure_y = 1.5 + 1.5 + 0.2 = 3.2

exposure_z unchanged.

DataFrame result:
```text
             exposure_y  exposure_z
property_id
101                 3.5         2.0
102                 3.2         2.0
```

---

## Edge cases / behavior notes

### If `section_properties` is `None` or empty
- Loop runs zero times
- Returns empty DataFrame (or empty dict)

### If some rows are malformed
Rows are skipped when:
- row is empty/None
- row is too short to access index 14
- left/right/top/bottom cannot be converted to float

### Property IDs can be non-integer
Because `pid = row[COL_ID]` is kept as-is and stored in an object array,
it can be `101`, `"S101"`, etc.  
(Overrides dict keys must match the exact pid type/value.)

---

## Quick summary
- Reads section offsets (left/right/top/bottom) from fixed column indices
- Optionally adds extra Y exposure (default or per property override)
- Computes:
  - `exposure_y = top + bottom + extra_y`
  - `exposure_z = left + right`
- Returns results as DataFrame (default) or dict
