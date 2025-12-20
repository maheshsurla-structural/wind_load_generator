# Notes: `core/wind_load/live_wind_loads.py`

## Purpose
This module builds **LIVE wind (WL)** beam line-loads for MIDAS by combining:

- **Control Data coefficients** (`wind_live.angles`, `wind_live.transverse`, `wind_live.longitudinal`)
- **WL case rows** (`wl_cases_df` with columns `Case`, `Angle`, `Value`)

It produces two main intermediate artifacts:

1. **Components table** (per load case: transverse/longitudinal values with quadrant sign rules applied)
2. **Beam-load plan** (per structural group: element-wise line load records ready to send to MIDAS)

It also provides:
- A **per-group apply wrapper** (build plan + debug + apply to MIDAS)
- A **multi-group builder** (build plans for many deck groups; optionally dump debug)

---

## Key concepts used in this module

### 1) WL case naming drives quadrant sign logic
The string stored in `wl_cases_df["Value"]` is expected to be the **MIDAS load case name**, and it often includes a quadrant marker:

- `...Q1`, `...Q2`, `...Q3`, `...Q4` (or `_Q1`, `_Q2`, `_Q3`, `_Q4`)

The quadrant is parsed from the name and used to flip signs of transverse/longitudinal base coefficients.

### 2) “Base” coefficients are treated as Quadrant 1 (Q1)
Control Data (`wind_live.transverse`, `wind_live.longitudinal`) is treated as the **Q1 base**.
Quadrant markers in the WL case name change signs using `_QUAD_SIGNS`.

### 3) Component-to-direction mapping
The module assumes:

- `transverse` acts in MIDAS local **Y** direction (`LY`)
- `longitudinal` acts in MIDAS local **X** direction (`LX`)

This mapping is centralized in `_COMPONENTS`.

---

## Imports and dependencies

```python
from typing import Sequence, Iterable, Mapping
import re
import pandas as pd
```

- `Sequence`: used for the Control Data arrays (`angles`, `transverse`, `longitudinal`)
- `Iterable`: used for iterating through `deck_groups`
- `Mapping`: used for `group_members` (group -> element_ids)
- `re`: parsing quadrant markers from load case names
- `pandas`: DataFrames are the primary in/out format

```python
from core.wind_load.beam_load import (
    build_uniform_load_beam_load_plan_for_group,
    apply_beam_load_plan_to_midas,
)
from core.wind_load.debug_utils import summarize_plan
from core.wind_load.group_cache import get_group_element_ids
```

- `build_uniform_load_beam_load_plan_for_group(...)`  
  Builds a DataFrame describing line loads on a list of element IDs for one case & direction.

- `apply_beam_load_plan_to_midas(plan_df)`  
  Sends the plan into MIDAS.

- `summarize_plan(...)`  
  Debug helper to print/log what’s going to be applied.

- `get_group_element_ids(group_name)`  
  Retrieves element IDs for a structural group (cached).

---

## Helpers

### 1) Quadrant regex

```python
_QUADRANT_RE = re.compile(r"(?:_Q|Q)([1-4])\b", re.I)
```

What it does:
- Finds `Q1..Q4` in a string (case-insensitive).
- Supports both patterns:
  - `_Q3`
  - `Q3`

Why it matters:
- Quadrant sign rules depend on extracting the quadrant from the load case name (`Value`).

---

### 2) Quadrant sign map

```python
_QUAD_SIGNS = {
    1: (+1, +1),
    2: (+1, -1),
    3: (-1, -1),
    4: (-1, +1),
}
```

What it does:
- Defines how transverse and longitudinal values change sign per quadrant.

Meaning:
- Q1: (+t, +l)
- Q2: (+t, -l)
- Q3: (-t, -l)
- Q4: (-t, +l)

Why it matters:
- Control Data arrays are treated as “base Q1”. This mapping generates Q2–Q4 signs.

---

### 3) Component-to-MIDAS direction mapping

```python
_COMPONENTS = (
    ("transverse", "LY"),
    ("longitudinal", "LX"),
)
```

What it does:
- Declares how each component column maps to a MIDAS local direction.
- Later, when building plans:
  - `row["transverse"]` becomes a UDL in `LY`
  - `row["longitudinal"]` becomes a UDL in `LX`

Why it matters:
- Centralizes the mapping and avoids duplicating “transverse -> LY” logic.

---

## `_parse_quadrant_from_load_case_name(name: str) -> int`

```python
m = _QUADRANT_RE.search(name or "")
return int(m.group(1)) if m else 1
```

What it does:
- Searches for a quadrant marker `Q1..Q4` (or `_Q1.._Q4`) in `name`.
- Returns the detected quadrant number.
- Defaults to `1` if no quadrant marker is present.

Why it matters:
- Ensures load case names without explicit quadrant behave like Q1.

---

## `_apply_quadrant_sign_convention(q: int, t: float, l: float) -> tuple[float, float]`

```python
ts, ls = _QUAD_SIGNS.get(int(q), _QUAD_SIGNS[1])
return ts * t, ls * l
```

What it does:
- Looks up sign multipliers for `q`.
- If `q` is unexpected, falls back to Q1.
- Returns sign-adjusted `(transverse, longitudinal)`.

Why it matters:
- Keeps all sign logic in one place.
- Ensures consistent behavior across the module.

---

## `_normalize_and_validate_wl_cases_df(wl_cases_df: pd.DataFrame) -> pd.DataFrame`

### Purpose
Validates and normalizes the WL “cases table” coming from GUI/user input.

### 1) Required columns check

```python
needed = {"Case", "Angle", "Value"}
missing = needed - set(wl_cases_df.columns)
if missing:
    raise ValueError(f"wl_cases_df is missing columns: {missing}")
```

What it does:
- Ensures the DataFrame has the expected schema.

Why it matters:
- Prevents later crashes and produces clearer error messages.

---

### 2) Work on a copy

```python
df = wl_cases_df.copy()
```

What it does:
- Avoids modifying the caller’s DataFrame.

---

### 3) Coerce `Angle` to numeric + validate

```python
df["Angle"] = pd.to_numeric(df["Angle"], errors="coerce")
bad_angle = df["Angle"].isna()
if bad_angle.any():
    raise ValueError(
        f"wl_cases_df has non-numeric Angle at rows: {df.index[bad_angle].tolist()}"
    )
```

What it does:
- Converts numeric-looking strings to numbers.
- Invalid angle values become NaN and are rejected.

Why it matters:
- Ensures downstream code can safely treat Angle as numeric.

---

### 4) Enforce integer-like `Angle`, then cast to `int`

```python
non_int = (df["Angle"] % 1 != 0)
if non_int.any():
    raise ValueError(
        f"wl_cases_df has non-integer Angle at rows: {df.index[non_int].tolist()}"
    )
df["Angle"] = df["Angle"].astype(int)
```

What it does:
- Rejects angles like `15.5`.
- Converts angles like `15.0` into `15`.

Why it matters:
- Downstream logic expects exact integer angles (e.g., 0, 15, 30, 45).

---

### 5) Validate + normalize `Value`

```python
s = df["Value"]
empty = s.isna() | (s.astype(str).str.strip() == "")
if empty.any():
    raise ValueError(
        f"wl_cases_df has empty Value at rows: {df.index[empty].tolist()}"
    )

df["Value"] = s.astype(str).str.strip()
```

What it does:
- Rejects missing or blank load case names.
- Normalizes `Value` into a stripped string.

Why it matters:
- `Value` becomes the load case name used downstream.
- Quadrant extraction depends on `Value`.

---



## 2) `build_wl_beam_load_plan_for_group(...)`

### Purpose
Takes a components table and builds a **combined beam-load plan** DataFrame for a single structural group.

It does **not** apply the plan to MIDAS.

---

### 1) Guard: no components

```python
if components_df is None or components_df.empty:
    print(...)
    return pd.DataFrame()
```

What it does:
- Avoids doing work when there is nothing to apply.

---

### 2) Resolve element IDs

```python
if element_ids is None:
    element_ids = get_group_element_ids(group_name)
else:
    element_ids = [int(e) for e in element_ids]
```

What it does:
- If not provided, fetches group members from cache.
- If provided, normalizes IDs to integers.

Why it matters:
- The plan must target explicit element IDs.

---

### 3) Guard: group has no elements

```python
if not element_ids:
    print(...)
    return pd.DataFrame()
```

What it does:
- Avoids generating an empty/invalid plan.

---

### 4) Build per-case, per-direction plans

```python
for _, row in components_df.iterrows():
    lcname = str(row["load_case"])
    lgname = str(row["load_group"] or lcname)

    for col, direction in _COMPONENTS:
        val = float(row[col])
        if abs(val) <= 1e-9:
            continue

        plans.append(
            build_uniform_load_beam_load_plan_for_group(
                group_name=group_name,
                load_case_name=lcname,
                line_load=val,
                udl_direction=direction,
                load_group_name=lgname,
                element_ids=element_ids,
                eccentricity=eccentricity,
            )
        )
```

What it does:
- For each load case, it generates up to two “sub-plans”:
  - transverse -> `LY`
  - longitudinal -> `LX`
- Skips near-zero values (`1e-9` tolerance) to avoid clutter.
- Each sub-plan is built using the shared plan-builder.

Why it matters:
- Ensures both components are applied separately in the correct local directions.

---

### 5) Combine all sub-plans

```python
combined_plan = pd.concat(plans, ignore_index=True)
combined_plan.sort_values(["load_case", "element_id"], inplace=True)
combined_plan.reset_index(drop=True, inplace=True)
```

What it does:
- Produces one unified plan DataFrame.
- Sorts for deterministic ordering.

---

## 3) `apply_wl_beam_loads_to_group(group_name, components_df)`

### Purpose
Wrapper that:
- builds the plan
- optionally summarizes/debugs it
- applies it to MIDAS

---

### 1) Build plan

```python
combined_plan = build_wl_beam_load_plan_for_group(group_name, components_df)
```

---

### 2) Guard: nothing to apply

```python
if combined_plan is None or combined_plan.empty:
    print(...)
    return
```

---

### 3) Debug summary

```python
summarize_plan(
    combined_plan,
    label=f"WL_{group_name}",
    dump_csv_per_case=False,
    write_log=True,
)
```

What it does:
- Prints or writes a summary to help diagnose what will be applied.
- Controlled with flags:
  - `dump_csv_per_case`: optionally write per-case CSVs
  - `write_log`: write a log entry

---

### 4) Apply to MIDAS

```python
apply_beam_load_plan_to_midas(combined_plan)
```

What it does:
- Sends the plan to MIDAS.

---

## 4) `build_wl_beam_load_plans_for_deck_groups(...)`

### Purpose
Builds WL plans for multiple deck groups and returns them, without applying to MIDAS.

It also reports whether WL was applied to at least one group.

Returns:
- `plans`: list of DataFrames (one per group)
- `wl_applied_any`: bool flag

---

### 1) Default empty dicts (avoid `None` checks)

```python
elements_in_model = elements_in_model or {}
nodes_in_model = nodes_in_model or {}
group_members = group_members or {}
```

What it does:
- Guarantees mappings exist, even if caller passes `None`.
- `elements_in_model` / `nodes_in_model` are accepted for compatibility but not used here.

---

### 2) Guard: missing angles or missing WL cases

```python
angles = getattr(wind_live, "angles", None)
if wl_cases_df is None or wl_cases_df.empty or angles is None or len(angles) == 0:
    return [], False
```

What it does:
- Ensures required inputs exist.
- Without angles or WL case rows, there is nothing to build.

---

### 3) Build components once (shared by all groups)

```python
components_df = build_wl_case_components_from_control_data(
    angles=angles,
    transverse=wind_live.transverse,
    longitudinal=wind_live.longitudinal,
    wl_cases_df=wl_cases_df,
)
```

What it does:
- Computes the “case → (t,l)” table one time.
- Reused for every group, which is faster and consistent.

---

### 4) Loop deck groups and build plans

```python
for group_name in deck_groups:
    group_name = str(group_name).strip()
    if not group_name:
        continue
```

What it does:
- Normalizes group names and skips blanks.

---

### 5) Use provided group members when available

```python
cached_ids = group_members.get(group_name)
element_ids_for_plan = cached_ids if cached_ids else None
```

What it does:
- If the caller already knows element IDs for a group, reuse them.
- Otherwise, the per-group builder will fetch from cache.

Why it matters:
- Allows the caller to optimize by providing precomputed group membership.

---

### 6) Build plan for this group

```python
plan_wl = build_wl_beam_load_plan_for_group(
    group_name=group_name,
    components_df=components_df,
    element_ids=element_ids_for_plan,
    elements_in_model=elements_in_model,
    nodes_in_model=nodes_in_model,
)
```

What it does:
- Produces the per-group plan DataFrame.

---

### 7) Optional debug sink dump

```python
if plan_wl is not None and not plan_wl.empty:
    if dbg is not None and getattr(dbg, "enabled", False):
        dbg.dump_plan(plan_wl, label=f"WL_{group_name}", split_per_case=True)
```

What it does:
- If debug is enabled, dumps plan outputs for inspection.
- `split_per_case=True` typically produces one file per load case.

---

### 8) Collect results + applied flag

```python
plans.append(plan_wl)
wl_applied_any = True
```

What it does:
- Stores the plan in the output list.
- Tracks that at least one group received WL loads.

---

## Data flow summary

1. Validate WL case rows (`Case`, `Angle`, `Value`)
2. Map Control Data coefficients to angles
3. For each WL case name:
   - parse quadrant (Q1..Q4)
   - flip signs using quadrant map
4. Create components table: `(load_case, angle, transverse, longitudinal)`
5. For each group:
   - resolve element IDs
   - create UDL plans in `LY` and `LX`
6. Optionally summarize/dump debug and apply to MIDAS
