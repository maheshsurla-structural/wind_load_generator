# Notes: `_validate_wl_cases_df(wl_cases_df)`

## Purpose
`_validate_wl_cases_df()` is a **validator + normalizer** for a user/GUI-provided pandas DataFrame that describes wind-load “case rows”.

It does two things:
- **Validation (fail fast):** errors early if the table is not usable
- **Normalization:** converts columns into consistent types so downstream code can assume a stable format

---

## Expected input schema
The input DataFrame **must** contain these columns:

- `Case`
  - A grouping label (e.g., `"Strength III"`, `"Service I"`, etc.)
  - Typically used for grouping/filtering, not for math

- `Angle`
  - Must be numeric or numeric-looking (e.g., `0`, `90`, `"180"`)
  - Represents direction/heading

- `Value`
  - Must be a **non-empty identifier string**
  - In your workflow this is usually a **case key / case name**, often including quadrant info like `Q1..Q4`
  - This is **not** the pressure magnitude; it’s an identifier used downstream for naming/lookup/sign logic

Example:
| Case         | Angle | Value     |
|--------------|------:|-----------|
| Strength III | 0     | WIND_Q1   |
| Strength III | 90    | WIND_Q2   |
| Strength III | 180   | WIND_Q3   |
| Strength III | 270   | WIND_Q4   |

---

## What the function guarantees on success
If the function returns `df` successfully:
- `df` contains **all required columns**: `Case`, `Angle`, `Value`
- `df["Angle"]` is **numeric** for all rows
- `df["Value"]` is a **trimmed string** for all rows and is **not blank**
- The returned `df` is a **copy**, so the original input is not mutated

---

## Step-by-step behavior (mapped to code)

### 1) Required columns check
```python
needed = {"Case", "Angle", "Value"}
missing = needed - set(wl_cases_df.columns)
if missing:
    raise ValueError(f"wl_cases_df is missing columns: {missing}")
```

What it does:
- Ensures the DataFrame has the minimum required schema.
- If any required columns are absent, raises immediately.

Why it matters:
- Prevents later crashes like `KeyError: 'Angle'` or `KeyError: 'Value'`.
- Errors are clearer at the point of validation.

---

### 2) Work on a copy (avoid side effects)
```python
df = wl_cases_df.copy()
```

What it does:
- Protects the caller from unexpected modifications.

Why it matters:
- Makes the validator safe to call in multiple places.

---

### 3) Coerce `Angle` to numeric and reject invalid rows
```python
df["Angle"] = pd.to_numeric(df["Angle"], errors="coerce")
bad_angle = df["Angle"].isna()
if bad_angle.any():
    raise ValueError(
        f"wl_cases_df has non-numeric Angle at rows: {df.index[bad_angle].tolist()}"
    )
```

What it does:
- Converts `Angle` to numeric using `pd.to_numeric`.
- With `errors="coerce"`, bad values become `NaN` instead of throwing immediately.
- If any `NaN` exists, raises an error listing the failing **index values**.

Examples:
- `"90"` -> `90`
- `180` -> `180`
- `"90deg"` -> `NaN` (invalid)
- `None` -> `NaN` (invalid)

Important:
- It reports **DataFrame index values**, not necessarily 0..N row numbers.

---

### 4) Normalize `Value` into a trimmed string and reject blanks
```python
df["Value"] = df["Value"].astype(str).str.strip()
empty = df["Value"].eq("") | df["Value"].isna()
if empty.any():
    raise ValueError(
        f"wl_cases_df has empty Value at rows: {df.index[empty].tolist()}"
    )
```

What it does:
- Converts `Value` to string, then trims whitespace.
- Rejects values that become blank after stripping.

Examples:
- `"  WIND_Q1  "` -> `"WIND_Q1"`
- `"   "` -> `""` (rejected)

Important gotcha:
- `astype(str)` converts missing values like `None` / `NaN` into strings (`"None"` / `"nan"`).
- That means true missing values can accidentally pass the `isna()` check after conversion.
- This validator reliably catches whitespace-only strings, but may not reliably catch `None` after `astype(str)`.

---

## How `Value` relates to quadrants in your workflow
In your quadrant-sign logic, `Value` is commonly the string that contains a quadrant marker:
- `...Q1`, `...Q2`, `...Q3`, `...Q4`

Downstream behavior often looks like:
- parse `Value` to extract quadrant number (`1..4`)
- use quadrant to pick sign multipliers (e.g., transverse/longitudinal sign flips)

So yes — **in your current design, `Value` is the key field that often drives quadrant selection**, not the numeric “load magnitude”.

---

## Optional improvement (only if you want `None` / `NaN` to be rejected reliably)
If you want to correctly fail `None` / `NaN` in `Value`, validate missing *before* converting to string:

```python
# Validate missing/blank before casting to string
raw = df["Value"]
missing_value = raw.isna()
if missing_value.any():
    raise ValueError(f"wl_cases_df has missing Value at rows: {df.index[missing_value].tolist()}")

# Now normalize to string + strip
df["Value"] = raw.astype(str).str.strip()

# Reject blank after strip
blank_value = df["Value"].eq("")
if blank_value.any():
    raise ValueError(f"wl_cases_df has blank Value at rows: {df.index[blank_value].tolist()}")
```
