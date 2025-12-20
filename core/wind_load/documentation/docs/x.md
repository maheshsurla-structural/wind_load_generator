## 1) `build_wl_case_components_from_control_data(...)`

### Purpose
Builds a “components table” by combining:
- Control Data coefficients by angle
- WL case names by angle
- Quadrant sign rules extracted from case names

### Returns
A DataFrame with:

- `load_case` (string)  
- `load_group` (string) — same as `load_case` by rule  
- `angle` (int)  
- `transverse` (float, sign-adjusted)  
- `longitudinal` (float, sign-adjusted)

---

### 1) Early return if WL cases empty

```python
if wl_cases_df is None or wl_cases_df.empty:
    return pd.DataFrame(columns=[...])
```

What it does:
- Produces a correctly-shaped empty DataFrame when there is nothing to build.

---

### 2) Validate WL case table

```python
wl_cases_df = _normalize_and_validate_wl_cases_df(wl_cases_df)
```

What it does:
- Ensures angles/names are clean before doing any mapping.

---

### 3) Validate Control Data arrays align

```python
if not (len(angles) == len(transverse) == len(longitudinal)):
    raise ValueError("angles / transverse / longitudinal must have same length")
```

What it does:
- Ensures a 1-to-1 mapping exists between:
  - `angles[i]`, `transverse[i]`, `longitudinal[i]`

Why it matters:
- Prevents silent coefficient misalignment.

---

### 4) Build angle -> (base_t, base_l) map

```python
angle_to_coeffs: dict[int, tuple[float, float]] = {}
for ang, t, l in zip(angles, transverse, longitudinal):
    angle_to_coeffs[int(ang)] = (float(t), float(l))
```

What it does:
- Creates a lookup like `{15: (0.12, 0.08), ...}`.
- These coefficients are treated as **base Q1**.

Why it matters:
- WL case rows contain `Angle`, so this map attaches coefficients to each case row.

---

### 5) For each WL case row, build output rows

```python
for _, row in wl_cases_df.iterrows():
    ang = row["Angle"]
    lcname = str(row["Value"])

    coeffs = angle_to_coeffs.get(ang)
    if coeffs is None:
        continue
```

What it does:
- Extracts the angle and load case name.
- Skips WL rows whose angle does not exist in Control Data.

Why it matters:
- Prevents generating loads for angles you don’t have coefficients for.

---

### 6) Apply quadrant sign logic

```python
base_t, base_l = coeffs
q = _parse_quadrant_from_load_case_name(lcname)
t, l = _apply_quadrant_sign_convention(q, base_t, base_l)
```

What it does:
- Finds Q1..Q4 from the case name.
- Applies sign multipliers to the base coefficients.

Why it matters:
- This is the core “quadrant behavior” of LIVE wind loads.

---

### 7) Emit standardized row format

```python
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

What it does:
- Stores each case in a consistent normalized schema.

---

### 8) Sort output for stability

```python
out.sort_values(["angle", "load_case"], inplace=True)
out.reset_index(drop=True, inplace=True)
```

What it does:
- Keeps results predictable (important for debugging and repeatability).

---