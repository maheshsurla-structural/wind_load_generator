## `build_wl_case_components_from_control_data(...) -> pd.DataFrame`

Build a normalized “components” table for **live wind load (WL) cases** by combining:

- the user/control-table mapping of **Angle → Load Case Name** (`wl_cases_df`)
- base coefficient tables (`angles`, `transverse`, `longitudinal`)
- a sign convention derived from the load case name (quadrant parsing + sign application)

### Output columns

Returns a DataFrame with columns:

- `load_case` (str) — the load case name (from `wl_cases_df["Value"]`)
- `load_group` (str) — currently the same as `load_case`
- `angle` (int)
- `transverse` (float) — signed transverse coefficient
- `longitudinal` (float) — signed longitudinal coefficient

---

### Implementation

```py
def build_wl_case_components_from_control_data(
    *,
    angles: Sequence[int],
    transverse: Sequence[float],
    longitudinal: Sequence[float],
    wl_cases_df: pd.DataFrame,
) -> pd.DataFrame:
    if wl_cases_df is None or wl_cases_df.empty:
        return pd.DataFrame(
            columns=["load_case", "load_group", "angle", "transverse", "longitudinal"]
        )

    wl_cases_df = normalize_and_validate_cases_df(wl_cases_df, df_name="wl_cases_df")

    angle_to_coeffs = coeffs_by_angle(
        angles=angles,
        transverse=transverse,
        longitudinal=longitudinal,
        table_name="wind_live",
    )

    rows: list[dict] = []
    for _, row in wl_cases_df.iterrows():
        ang = int(row["Angle"])
        lcname = str(row["Value"])

        base = angle_to_coeffs.get(ang)
        if base is None:
            continue

        base_t, base_l = base
        q = parse_quadrant_from_load_case_name(lcname)
        t, l = apply_quadrant_sign_convention(q, base_t, base_l)

        rows.append(
            {
                "load_case": lcname,
                "load_group": lcname,
                "angle": ang,
                "transverse": t,
                "longitudinal": l,
            }
        )

    out = pd.DataFrame(rows)
    if not out.empty:
        out.sort_values(["angle", "load_case"], inplace=True)
        out.reset_index(drop=True, inplace=True)
    return out
```

---

## What this function does (high level)

1. If `wl_cases_df` is missing/empty → return an empty DataFrame with the correct columns.
2. Normalize and validate `wl_cases_df` using `normalize_and_validate_cases_df`:
   - requires columns: `Case`, `Angle`, `Value`
   - coerces `Angle` to int
   - trims and validates non-empty `Case` and `Value`
3. Build a base lookup `angle_to_coeffs` using `coeffs_by_angle`:
   - `{angle -> (base_transverse, base_longitudinal)}`
4. For each row in `wl_cases_df`:
   - read angle (`Angle`) and load case name (`Value`)
   - fetch base coefficients for that angle
   - parse quadrant from the load case name
   - apply sign convention based on quadrant
   - emit a row in the output table
5. Sort the final table by `angle` and `load_case`.

---

## Inputs

### `angles`, `transverse`, `longitudinal`

These form the base coefficient table, typically aligned with control angles:

```py
angles       = [0, 15, 30, 45, 60]
transverse   = [T0, T15, T30, T45, T60]
longitudinal = [L0, L15, L30, L45, L60]
```

`coeffs_by_angle(...)` converts these into:

```py
angle_to_coeffs = {
  0:  (T0,  L0),
  15: (T15, L15),
  30: (T30, L30),
  45: (T45, L45),
  60: (T60, L60),
}
```

### `wl_cases_df`

A control-table DataFrame mapping angles to load case names.

Required columns:

- `Case` (string-like, non-empty)
- `Angle` (numeric, integer-like)
- `Value` (string-like, non-empty) — **used as the load case name**

Even though the column is called `Value`, in this function it is explicitly treated as the load case name:

```py
lcname = str(row["Value"])
```

---

## Step-by-step behavior (line-by-line)

### 1) Early return for missing/empty input

```py
if wl_cases_df is None or wl_cases_df.empty:
    return pd.DataFrame(columns=[...])
```

- Avoids downstream errors and ensures callers always get a consistent schema.
- Returns an empty DataFrame with expected columns.

**Example:**

```py
build_wl_case_components_from_control_data(
    angles=[0,15,30,45,60],
    transverse=[...],
    longitudinal=[...],
    wl_cases_df=pd.DataFrame(),
)
```

Returns an empty DataFrame with columns:

`["load_case", "load_group", "angle", "transverse", "longitudinal"]`

---

### 2) Normalize + validate `wl_cases_df`

```py
wl_cases_df = normalize_and_validate_cases_df(wl_cases_df, df_name="wl_cases_df")
```

Guarantees after this point:

- `wl_cases_df["Angle"]` is `int`
- `wl_cases_df["Case"]` and `wl_cases_df["Value"]` are trimmed, non-empty strings

If validation fails, a `ValueError` is raised with row indices.

---

### 3) Build base coefficient lookup

```py
angle_to_coeffs = coeffs_by_angle(
    angles=angles,
    transverse=transverse,
    longitudinal=longitudinal,
    table_name="wind_live",
)
```

Produces:

```py
Dict[int, Tuple[float, float]]  # angle -> (base_t, base_l)
```

This mapping provides the **base magnitudes** before quadrant sign changes.

---

### 4) Iterate control rows and build output rows

```py
for _, row in wl_cases_df.iterrows():
    ang = int(row["Angle"])
    lcname = str(row["Value"])
```

- `ang` is the angle for this load case
- `lcname` is the load case name string (from `Value`)

---

### 5) Skip angles that have no base coefficients

```py
base = angle_to_coeffs.get(ang)
if base is None:
    continue
```

If `wl_cases_df` contains an angle not present in the coefficient table, that row is ignored.

**Example:**
- If `wl_cases_df` contains `Angle = 75`
- But `angle_to_coeffs` only has 0,15,30,45,60
- Then that row is skipped.

---

### 6) Apply quadrant sign convention

```py
base_t, base_l = base
q = parse_quadrant_from_load_case_name(lcname)
t, l = apply_quadrant_sign_convention(q, base_t, base_l)
```

- `parse_quadrant_from_load_case_name(lcname)` extracts a quadrant identifier from the load case name.
  - Example conventions might be: `Q1`, `Q2`, `Q3`, `Q4` embedded in the name.
  - (Exact parsing depends on your implementation.)
- `apply_quadrant_sign_convention(q, base_t, base_l)` flips signs of `(base_t, base_l)` according to quadrant.

> This is what makes the coefficients “directional” per load case name while the base table holds just the magnitudes per angle.

---

### 7) Emit a component row

```py
rows.append(
    {
        "load_case": lcname,
        "load_group": lcname,
        "angle": ang,
        "transverse": t,
        "longitudinal": l,
    }
)
```

- `load_group` is currently identical to `load_case`
- Each input row produces one output row (unless skipped due to missing coefficients)

---

### 8) Assemble DataFrame and sort

```py
out = pd.DataFrame(rows)
if not out.empty:
    out.sort_values(["angle", "load_case"], inplace=True)
    out.reset_index(drop=True, inplace=True)
return out
```

- Produces the final components DataFrame.
- Sorts deterministically for stable downstream behavior and nicer debugging.
- Resets index to 0..n-1.

---

## End-to-end example (conceptual)

### Base coefficients (magnitudes)

```py
angles       = [0, 15, 30, 45, 60]
transverse   = [0.10, 0.20, 0.30, 0.40, 0.50]
longitudinal = [1.00, 1.10, 1.20, 1.30, 1.40]
```

### Control mapping table (`wl_cases_df`)

```py
wl_cases_df = pd.DataFrame(
    {
        "Case":  ["WL", "WL", "WL", "WL"],
        "Angle": [0, 15, 0, 15],
        "Value": ["WL_Q1_0", "WL_Q1_15", "WL_Q3_0", "WL_Q3_15"],
    }
)
```

### Conceptual quadrant behavior (example)

Assume your sign convention is:

- Q1 → `( +T, +L )`
- Q3 → `( -T, -L )`

Then output would be:

| load_case  | load_group | angle | transverse | longitudinal |
|-----------|------------|------:|-----------:|-------------:|
| WL_Q1_0   | WL_Q1_0    | 0     | 0.10       | 1.00         |
| WL_Q3_0   | WL_Q3_0    | 0     | -0.10      | -1.00        |
| WL_Q1_15  | WL_Q1_15   | 15    | 0.20       | 1.10         |
| WL_Q3_15  | WL_Q3_15   | 15    | -0.20      | -1.10        |

> The exact signs depend on your actual implementations of
> `parse_quadrant_from_load_case_name()` and `apply_quadrant_sign_convention()`.

---

## Notes / gotchas

- `wl_cases_df["Value"]` is treated as the **load case name** (even though the column is named `Value`).
- Any row whose `Angle` is not found in the base coefficient table is silently skipped (`continue`).
- Performance: `iterrows()` is fine for small control tables (usually a few rows). If this ever grows large, a vectorized approach might be considered.
