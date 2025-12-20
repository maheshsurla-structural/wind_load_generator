## `normalize_and_validate_cases_df(df_in: pd.DataFrame, *, df_name: str = "cases_df") -> pd.DataFrame`

Normalize and validate a “cases” DataFrame to ensure it has the expected schema and clean, usable values.

### Expected input schema

Required columns (case-sensitive):

- `Case`
- `Angle`
- `Value`

### Guarantees on output

Returns a **copy** of the input DataFrame where:

- `Angle` is converted to **integer** (`int`) and is guaranteed to be:
  - numeric
  - integer-like (e.g., `15` or `15.0` are allowed, `15.2` is rejected)
- `Case` and `Value` are:
  - converted to strings
  - trimmed (`strip()`)
  - guaranteed **non-empty** after trimming

If any validation fails, the function raises a `ValueError` with the failing row indices.

---

### Implementation

```py
def normalize_and_validate_cases_df(
    df_in: pd.DataFrame,
    *,
    df_name: str = "cases_df",
) -> pd.DataFrame:
    """
    Expected columns: Case, Angle, Value
    - Angle numeric + integer-like -> int
    - Case/Value stripped and non-empty
    """
    needed = {"Case", "Angle", "Value"}
    missing = needed - set(df_in.columns)
    if missing:
        raise ValueError(f"{df_name} is missing columns: {missing}")

    df = df_in.copy()

    df["Angle"] = pd.to_numeric(df["Angle"], errors="coerce")
    bad = df["Angle"].isna()
    if bad.any():
        raise ValueError(f"{df_name} has non-numeric Angle at rows: {df.index[bad].tolist()}")

    non_int = (df["Angle"] % 1 != 0)
    if non_int.any():
        raise ValueError(f"{df_name} has non-integer Angle at rows: {df.index[non_int].tolist()}")

    df["Angle"] = df["Angle"].astype(int)

    df["Case"] = df["Case"].astype(str).str.strip()
    df["Value"] = df["Value"].astype(str).str.strip()

    empty_case = df["Case"] == ""
    if empty_case.any():
        raise ValueError(f"{df_name} has empty Case at rows: {df.index[empty_case].tolist()}")

    empty_val = df["Value"] == ""
    if empty_val.any():
        raise ValueError(f"{df_name} has empty Value at rows: {df.index[empty_val].tolist()}")

    return df
```

---

## Step-by-step behavior

### 1) Validate required columns exist

```py
needed = {"Case", "Angle", "Value"}
missing = needed - set(df_in.columns)
if missing:
    raise ValueError(...)
```

- Ensures `df_in` contains the required columns.
- Raises immediately if any are missing.

**Example (missing column):**

Input columns: `["Case", "Angle"]`

Raises:

- `cases_df is missing columns: {'Value'}`

---

### 2) Work on a copy (avoid mutating input)

```py
df = df_in.copy()
```

- All transformations happen on a copy so callers don’t get surprising in-place changes.

---

### 3) Convert `Angle` to numeric (coerce invalid values to NaN)

```py
df["Angle"] = pd.to_numeric(df["Angle"], errors="coerce")
bad = df["Angle"].isna()
if bad.any():
    raise ValueError(...)
```

- `pd.to_numeric(..., errors="coerce")` converts numeric-like strings (e.g., `"15"`, `"45.0"`) to numbers.
- Non-numeric values become `NaN`.
- Any `NaN` triggers a `ValueError` that reports the row indices.

**Example (non-numeric angle):**

| idx | Angle |
|---:|:------|
| 0  | 15    |
| 1  | "abc" |

Raises:

- `cases_df has non-numeric Angle at rows: [1]`

---

### 4) Enforce that `Angle` is integer-like

```py
non_int = (df["Angle"] % 1 != 0)
if non_int.any():
    raise ValueError(...)
```

- Rejects values with fractional parts.
- Example:
  - `15.0 % 1 == 0` ✅ allowed
  - `15.2 % 1 == 0.2` ❌ rejected

**Example (non-integer angle):**

| idx | Angle |
|---:|:------|
| 0  | 15    |
| 1  | 22.5  |

Raises:

- `cases_df has non-integer Angle at rows: [1]`

---

### 5) Convert `Angle` to integer dtype

```py
df["Angle"] = df["Angle"].astype(int)
```

- Safe because all values are numeric and integer-like at this point.
- Converts `15.0` → `15`.

---

### 6) Normalize `Case` and `Value` to trimmed strings

```py
df["Case"] = df["Case"].astype(str).str.strip()
df["Value"] = df["Value"].astype(str).str.strip()
```

- Ensures both columns are strings.
- Removes leading/trailing whitespace.

Examples:

- `" LC1 "` → `"LC1"`
- `"  "` → `""` (becomes empty, which will fail next)

---

### 7) Reject empty `Case` after trimming

```py
empty_case = df["Case"] == ""
if empty_case.any():
    raise ValueError(...)
```

**Example:**

| idx | Case   |
|---:|:--------|
| 0  | "LC1"   |
| 1  | "   "   |

Raises:

- `cases_df has empty Case at rows: [1]`

---

### 8) Reject empty `Value` after trimming

```py
empty_val = df["Value"] == ""
if empty_val.any():
    raise ValueError(...)
```

**Example:**

| idx | Value |
|---:|:------|
| 0  | "A"   |
| 1  | " "   |

Raises:

- `cases_df has empty Value at rows: [1]`

---

## Successful end-to-end example

**Input:**

```py
df_in = pd.DataFrame(
    {
        "Case": [" LC1 ", "LC2", "LC3"],
        "Angle": ["15", 30.0, "45.0"],
        "Value": [" A ", "B", " C"],
    }
)
```

**Output:**

```py
df = normalize_and_validate_cases_df(df_in)

# df:
#   Case  Angle Value
# 0  LC1     15     A
# 1  LC2     30     B
# 2  LC3     45     C
```

- `Angle` is `int`
- `Case` and `Value` are trimmed and non-empty
- input `df_in` is unchanged
