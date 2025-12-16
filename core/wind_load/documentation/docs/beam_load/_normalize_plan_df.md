# `_normalize_plan_df` — Detailed Notes (Full Explanation)

## Purpose
This function takes a “beam load plan” DataFrame and **cleans/standardizes** it so downstream code can rely on consistent types and fields.

It ensures:
- Required columns exist
- Text fields are strings and trimmed
- Numeric fields are converted to numbers
- Invalid rows are removed
- `eccentricity` exists and is numeric (default 0.0)
- Optional aggregation of duplicate rows (summing `line_load`)
- Final DataFrame is stably sorted for deterministic output

---

## Function code (reference)

```python
def _normalize_plan_df(plan_df: pd.DataFrame, aggregate_duplicates: bool) -> pd.DataFrame:
    required = {"element_id", "line_load", "load_case", "load_direction", "load_group"}
    missing = required - set(plan_df.columns)
    if missing:
        raise ValueError(f"plan_df missing required columns: {sorted(missing)}")

    df = plan_df.copy()
    df["load_case"] = df["load_case"].astype(str).str.strip()
    df["load_direction"] = df["load_direction"].astype(str).str.strip()
    df["load_group"] = df["load_group"].astype(str).str.strip()

    if "eccentricity" not in df.columns:
        df["eccentricity"] = 0.0
    df["eccentricity"] = pd.to_numeric(df["eccentricity"], errors="coerce").fillna(0.0)

    df["element_id"] = pd.to_numeric(df["element_id"], errors="coerce")
    df["line_load"] = pd.to_numeric(df["line_load"], errors="coerce")
    df = df.dropna(subset=["element_id", "line_load"])
    df["element_id"] = df["element_id"].astype(int)

    if aggregate_duplicates:
        key_cols = ["element_id", "load_case", "load_direction", "load_group", "eccentricity"]
        df = df.groupby(key_cols, as_index=False, sort=False)["line_load"].sum()

    df = df.sort_values(["load_case", "load_direction", "element_id"], kind="stable").reset_index(drop=True)
    return df
```

---

## Inputs

### `plan_df: pd.DataFrame`
A DataFrame describing beam loads. It must contain at least these columns:

Required columns:
- `element_id`
- `line_load`
- `load_case`
- `load_direction`
- `load_group`

Optional columns:
- `eccentricity` (if missing, this function creates it with default 0.0)

### `aggregate_duplicates: bool`
Controls whether duplicate entries should be merged (summed).

- `True`  → group by key columns and **sum `line_load`**
- `False` → keep all rows (after cleaning)

---

## Output
Returns a cleaned DataFrame with:
- guaranteed required columns
- cleaned string fields
- numeric `element_id`, `line_load`, `eccentricity`
- optional aggregation
- stable sorting

---

## Step-by-step explanation (line by line)

### 1) Define required columns and validate input
```python
required = {"element_id", "line_load", "load_case", "load_direction", "load_group"}
missing = required - set(plan_df.columns)
if missing:
    raise ValueError(f"plan_df missing required columns: {sorted(missing)}")
```

- Builds a set of required column names.
- Computes which required columns are missing.
- If anything is missing, raises an error immediately (fail fast).

Example:
- If `plan_df` lacks `load_group`, you get:
  `ValueError: plan_df missing required columns: ['load_group']`

---

### 2) Work on a copy (avoid mutating caller’s DataFrame)
```python
df = plan_df.copy()
```

This ensures normalization doesn’t modify the original DataFrame passed in.

---

### 3) Normalize text fields: force string + strip whitespace
```python
df["load_case"] = df["load_case"].astype(str).str.strip()
df["load_direction"] = df["load_direction"].astype(str).str.strip()
df["load_group"] = df["load_group"].astype(str).str.strip()
```

Why:
- Downstream logic often compares strings or groups by them.
- Converting to string ensures consistent type even if the input had numbers or None.
- `.str.strip()` removes leading/trailing whitespace that can cause “false duplicates”.

Example:
- `" WIND+X "` becomes `"WIND+X"`
- `None` becomes `"None"` (important: this is how `astype(str)` behaves)

---

### 4) Ensure `eccentricity` exists and is numeric
```python
if "eccentricity" not in df.columns:
    df["eccentricity"] = 0.0
df["eccentricity"] = pd.to_numeric(df["eccentricity"], errors="coerce").fillna(0.0)
```

Two parts:

#### A) If missing, add the column
- If user’s plan doesn’t include eccentricity, the function adds it as `0.0` for all rows.

#### B) Convert to numeric robustly
- `pd.to_numeric(..., errors="coerce")` converts values to numbers:
  - valid numeric strings like `"0.25"` → `0.25`
  - invalid strings like `"abc"` → `NaN` (because coerced)
- `.fillna(0.0)` replaces NaN with `0.0`

Example:
- `"0.3"` → 0.3
- `"abc"` → NaN → 0.0
- None → NaN → 0.0

---

### 5) Convert `element_id` and `line_load` to numeric
```python
df["element_id"] = pd.to_numeric(df["element_id"], errors="coerce")
df["line_load"] = pd.to_numeric(df["line_load"], errors="coerce")
```

- Converts both columns to numeric types.
- Invalid values become NaN.

Example:
- `element_id="101"` → 101
- `element_id="A1"` → NaN
- `line_load="0.05"` → 0.05
- `line_load="bad"` → NaN

---

### 6) Drop rows with invalid element_id or line_load
```python
df = df.dropna(subset=["element_id", "line_load"])
```

If either `element_id` or `line_load` is NaN, the row is removed.

Why:
- You can’t apply a load without a valid element id or load magnitude.

---

### 7) Force element_id to integer
```python
df["element_id"] = df["element_id"].astype(int)
```

After dropping NaNs, this should be safe.

Note:
- If `element_id` values are floats like `101.0`, they become `101`.
- If `element_id` values are non-integer floats like `101.7`, `astype(int)` truncates to `101`.
  - In practice you typically expect element IDs to be integer-like.

---

### 8) Optionally aggregate duplicates (sum line loads)
```python
if aggregate_duplicates:
    key_cols = ["element_id", "load_case", "load_direction", "load_group", "eccentricity"]
    df = df.groupby(key_cols, as_index=False, sort=False)["line_load"].sum()
```

If `aggregate_duplicates=True`, rows are grouped by:

- `element_id`
- `load_case`
- `load_direction`
- `load_group`
- `eccentricity`

and within each identical group, `line_load` values are summed.

Why:
- If multiple plan builders add loads for the same element/case/direction/group/eccentricity,
  you might want a single combined row before writing to MIDAS.

Example (before):
```text
element_id  load_case  load_direction  load_group  eccentricity  line_load
101         WIND+X     GY              WIND+X      0.0           0.05
101         WIND+X     GY              WIND+X      0.0           0.02
```

After aggregation:
```text
element_id  load_case  load_direction  load_group  eccentricity  line_load
101         WIND+X     GY              WIND+X      0.0           0.07
```

Notes:
- `sort=False` keeps group order more aligned with original input (though final sort happens later anyway).
- `as_index=False` returns a flat DataFrame instead of a multi-index.

---

### 9) Stable sort and reset index
```python
df = df.sort_values(["load_case", "load_direction", "element_id"], kind="stable").reset_index(drop=True)
```

- Sorts rows by:
  1. `load_case`
  2. `load_direction`
  3. `element_id`

- `kind="stable"` ensures sorting is stable:
  - If two rows compare equal in the sort keys, their **relative order** is preserved.

- `.reset_index(drop=True)` gives a clean `0..N-1` index.

Why:
- Deterministic output is easier to debug and test.
- Makes downstream writing to MIDAS predictable.

---

### 10) Return the normalized DataFrame
```python
return df
```

---

## Worked examples

### Example 1: Cleaning strings + numeric conversion + dropping invalid rows

Input `plan_df` (conceptual):
```text
element_id  line_load  load_case    load_direction  load_group   eccentricity
"101"       "0.05"     " WIND+X "   " GY "          " WIND+X "   "0.25"
"A1"        "0.02"     "WIND+X"     "GY"            "WIND+X"     "0.0"
102         "bad"      "WIND+X"     "GY"            "WIND+X"     None
```

After conversion:
- Row with `element_id="A1"` → element_id becomes NaN → dropped
- Row with `line_load="bad"` → line_load becomes NaN → dropped
- Remaining row:
  - `element_id=101`
  - `line_load=0.05`
  - strings stripped

Output:
```text
element_id  line_load  load_case  load_direction  load_group  eccentricity
101         0.05       WIND+X     GY              WIND+X      0.25
```

---

### Example 2: Aggregating duplicates

Input:
```text
element_id  line_load  load_case  load_direction  load_group  eccentricity
101         0.05       WIND+X     GY              WIND+X      0.0
101         0.02       WIND+X     GY              WIND+X      0.0
101         0.01       WIND+X     GX              WIND+X      0.0
```

With `aggregate_duplicates=True`, the two identical-key rows are summed:

Output:
```text
element_id  line_load  load_case  load_direction  load_group  eccentricity
101         0.07       WIND+X     GY              WIND+X      0.0
101         0.01       WIND+X     GX              WIND+X      0.0
```

Then final sort orders by load_case, direction, element_id.

---

## Edge cases / behavior notes

### Missing required columns
Immediate `ValueError` with list of missing columns.

### `eccentricity` missing
Automatically created and filled with 0.0.

### Non-numeric `eccentricity`
Coerced to NaN then replaced with 0.0.

### Non-integer element IDs
- If values look like `101.0` → becomes `101`
- If values look like `101.7` → becomes `101` after `astype(int)` (truncation)
  - Typically element IDs should be integer-like; if not, you may want stricter validation.

### `astype(str)` converts None to "None"
This is sometimes fine, sometimes not—depends on your downstream logic.
If you want `None` to remain missing instead of becoming "None", you’d handle that differently.

---

## Quick summary
- Validates required columns exist
- Normalizes strings (case/group/direction) by converting to str and stripping spaces
- Ensures `eccentricity` exists and is numeric (default 0.0)
- Converts `element_id` and `line_load` to numeric; drops invalid rows
- Optional duplicate aggregation by summing line_load
- Stable sorts result and resets index
- Returns cleaned plan DataFrame
