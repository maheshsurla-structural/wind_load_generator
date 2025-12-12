# Notes: `core/wind_load/structural_wind_loads.py`

## Purpose
This module builds **STRUCTURAL wind (WS)** beam line-load plans for MIDAS.

It combines three inputs:

- **Wind pressures** (per `Group` + `Load Case`) from `wind_pressures_df` (usually `wind_db.wind_pressures`)
- **Skew coefficients** (`skew.angles`, `skew.transverse`, `skew.longitudinal`) that scale pressure by angle
- **WS case rows** (`ws_cases_df` with `Case`, `Angle`, `Value`) that define MIDAS load case naming (often includes `Q1..Q4`)

It produces two main intermediate artifacts:

1. **WS components table**: per load case & angle, computes *signed pressures*:
   - `p_transverse = Pz * t_coeff`
   - `p_longitudinal = Pz * l_coeff`

2. **WS beam-load plan**: per structural group, converts pressures into **line loads per element** using section exposure depths (height/depth mapping).

It also provides:

- a **per-group apply wrapper** (build plan + debug + apply to MIDAS)
- a **multi-group deck builder** (build plans for many deck groups; optionally dump debug)

---

## Key concepts used in this module

### 1) WS uses pressure *and* coefficients
Unlike live wind (WL), structural wind starts from a **base pressure**:

- `Pz (ksf)` from `wind_pressures_df` using `(Group, Load Case)`

Then it applies skew coefficients:

- `T(θ)` transverse coefficient
- `L(θ)` longitudinal coefficient

Final signed pressures:

- `p_transverse = Pz * T(θ)`
- `p_longitudinal = Pz * L(θ)`

---

### 2) Quadrant naming drives sign logic (same as WL)
`ws_cases_df["Value"]` is the final MIDAS load case name and often contains `Q1..Q4`.

The module reuses the same helper logic as WL:

- `_extract_quadrant_from_name(lcname)`
- `_apply_quadrant_signs(q, base_t, base_l)`

So the sign of transverse/longitudinal pressures changes by quadrant.

---

### 3) Pressure → line load uses exposure depths (section-based)
WS plans convert a **uniform pressure (ksf)** to a **line load** by multiplying by an element “depth” (exposure).

Depths are derived from section properties and exposure configuration:

- `compute_section_exposures(...)` returns a table of exposure dimensions by section
- each element is mapped to a section (`_get_element_to_section_map`)
- each element gets a depth value via its section’s exposure

Then per element:

- `line_load = pressure * depth(element)`

This conversion is performed by:

- `build_uniform_pressure_beam_load_plan_from_depths(...)`

---

## Imports and dependencies

```python
from typing import Sequence, Dict, Iterable, Mapping, Tuple, List
import pandas as pd
```

- `Sequence`: used for coefficient arrays (`angles`, `transverse`, `longitudinal`)
- `Dict/Mapping`: used for maps like `group_members` and `depth_by_eid`
- `Iterable`: used for iterating `deck_groups`
- `Tuple/List`: return types
- `pandas`: tables and plan outputs

```python
from core.wind_load.beam_load import (
    apply_beam_load_plan_to_midas,
    build_uniform_pressure_beam_load_plan_from_depths,
    _get_element_to_section_map,
    get_section_properties_cached,
)
```

- `build_uniform_pressure_beam_load_plan_from_depths(...)`  
  Builds a per-element line-load plan using a **pressure** and **depth_by_eid** mapping.

- `_get_element_to_section_map(element_ids)`  
  Maps each element to its section ID.

- `get_section_properties_cached()`  
  Returns section properties used to compute exposures.

- `apply_beam_load_plan_to_midas(plan_df)`  
  Applies the generated plan to MIDAS.

```python
from core.wind_load.group_cache import get_group_element_ids
from core.wind_load.compute_section_exposures import compute_section_exposures
```

- `get_group_element_ids(group_name)`  
  Gets element IDs for a group.

- `compute_section_exposures(...)`  
  Computes exposure depths (e.g., `exposure_y`, `exposure_z`) per section.

```python
from core.wind_load.live_wind_loads import (
    _extract_quadrant_from_name,
    _apply_quadrant_signs,
)
```

- Reuses quadrant parsing and sign application logic from live wind.

```python
from core.wind_load.debug_utils import summarize_plan
from wind_database import wind_db
```

- `summarize_plan(...)`: debug helper
- `wind_db.wind_pressures`: default source of pressure table

---

## 1) `build_structural_wind_components_table(...)`

### Purpose
Builds a WS “components table” containing *signed transverse/longitudinal pressures* for each WS load case row.

Inputs:
- `group_name`: used to pick `Pz` from wind pressure table
- `angles/transverse/longitudinal`: skew coefficient arrays (base coefficients, treated as Q1)
- `ws_cases_df`: table defining `(Case, Angle, Value)`:
  - `Case`: base load case category like `"Strength III"`
  - `Angle`: skew angle
  - `Value`: final MIDAS load case name (often includes `Q1..Q4`)
- `wind_pressures_df`: pressure table with `Group`, `Load Case`, `Pz (ksf)` (defaults to `wind_db.wind_pressures`)

Returns a DataFrame with:

- `load_case` (final MIDAS load case name)
- `load_group` (same as load_case)
- `angle`
- `base_case` (original category from ws_cases_df["Case"])
- `Pz` (ksf)
- `p_transverse` (ksf, signed)
- `p_longitudinal` (ksf, signed)

---

### 1) Default pressure source

```python
if wind_pressures_df is None:
    wind_pressures_df = wind_db.wind_pressures
```

What it does:
- Uses the shared database table when no explicit pressure DataFrame is passed.

---

### 2) Early exit if inputs empty

```python
if wind_pressures_df.empty or ws_cases_df is None or ws_cases_df.empty:
    return pd.DataFrame(columns=[...])
```

What it does:
- Returns an empty but correctly-shaped DataFrame if there is nothing to compute.

---

### 3) Validate required columns (WS and pressures)

```python
needed_ws = {"Case", "Angle", "Value"}
if missing := needed_ws - set(ws_cases_df.columns):
    raise ValueError(...)

needed_p = {"Group", "Load Case", "Pz (ksf)"}
if missing := needed_p - set(wind_pressures_df.columns):
    raise ValueError(...)
```

What it does:
- Ensures both tables have minimal required schema.

Why it matters:
- Avoids obscure failures later during filtering or numeric conversion.

---

### 4) Validate coefficient arrays align

```python
if not (len(angles) == len(transverse) == len(longitudinal)):
    raise ValueError("angles / transverse / longitudinal must have same length")
```

What it does:
- Ensures each angle has exactly one transverse and one longitudinal coefficient.

---

### 5) Build angle → (t_coeff, l_coeff) map (base Q1)

```python
angle_to_coeffs: dict[int, tuple[float, float]] = {}
for ang, t, l in zip(angles, transverse, longitudinal):
    angle_to_coeffs[int(ang)] = (float(t), float(l))
```

What it does:
- Creates a lookup for coefficients by angle.

Why it matters:
- WS case rows provide an angle; this map attaches the right coefficient pair.

---

### 6) Iterate WS case rows and compute pressures

```python
for _, ws_row in ws_cases_df.iterrows():
    ang = int(ws_row["Angle"])
    lcname = str(ws_row["Value"] or "").strip()
    base_case = str(ws_row["Case"] or "").strip()
    if not lcname or not base_case:
        continue
```

What it does:
- Reads:
  - `Angle` as int
  - `Value` as final load case name (lcname)
  - `Case` as base case category (base_case)
- Skips rows that are missing required text.

---

### 7) Skip angles not configured in coefficients

```python
coeffs = angle_to_coeffs.get(ang)
if coeffs is None:
    continue
```

What it does:
- Only generates WS loads for angles present in the skew coefficient arrays.

---

### 8) Fetch `Pz` for (group_name, base_case)

```python
mask = (
    (wind_pressures_df["Group"] == group_name)
    & (wind_pressures_df["Load Case"] == base_case)
)
sub = wind_pressures_df[mask]
if sub.empty:
    continue

Pz = float(sub.iloc[0]["Pz (ksf)"])
```

What it does:
- Filters pressure table to the row matching this group and base load case.
- Uses the first matching row to get `Pz (ksf)`.

Why it matters:
- Structural wind depends on pressure magnitude; without `Pz` there is no load.

Note:
- If multiple rows match, this takes the first. If duplicates are possible, you may want to enforce uniqueness elsewhere.

---

### 9) Apply quadrant sign logic (same as WL)

```python
q = _extract_quadrant_from_name(lcname)
t_coeff, l_coeff = _apply_quadrant_signs(q, base_t, base_l)
```

What it does:
- Parses quadrant marker from final load case name.
- Applies sign flips to base coefficients.

---

### 10) Compute signed pressures

```python
p_trans = Pz * t_coeff
p_long = Pz * l_coeff
```

What it does:
- Converts coefficient multipliers into actual pressures (ksf).

---

### 11) Emit standardized row

```python
rows.append({
    "load_case": lcname,
    "load_group": lcname,
    "angle": ang,
    "base_case": base_case,
    "Pz": Pz,
    "p_transverse": p_trans,
    "p_longitudinal": p_long,
})
```

What it does:
- Produces the components table used by the plan builder.

---

### 12) Sort output for stable results

```python
out.sort_values(["angle", "load_case"], inplace=True)
out.reset_index(drop=True, inplace=True)
```

---

## 2) `build_structural_wind_beam_load_plan_for_group(...)`

### Purpose
Builds the **combined WS beam-load plan** for a group using:

- signed pressures (`p_transverse`, `p_longitudinal`) from components table
- per-element depth mapping (`depth_by_eid`) derived from section exposures

It returns the plan DataFrame; it does not apply it.

---

### 1) Guard: no components

```python
if components_df is None or components_df.empty:
    print(...)
    return pd.DataFrame()
```

---

### 2) Resolve element IDs

```python
if element_ids is None:
    element_ids = get_group_element_ids(group_name)
else:
    element_ids = [int(e) for e in element_ids]
```

What it does:
- Uses cached group membership unless the caller provides explicit IDs.

---

### 3) Guard: group has no elements

```python
if not element_ids:
    print(...)
    return pd.DataFrame()
```

---

### 4) Map elements to sections

```python
elem_to_sect = _get_element_to_section_map(element_ids)
if not elem_to_sect:
    print(...)
    return pd.DataFrame()
```

What it does:
- Creates mapping `element_id -> section_id`.

Why it matters:
- Exposures are computed per section, not per element.

---

### 5) Compute section exposure depths (once)

```python
section_props_raw = get_section_properties_cached()
exposures_df = compute_section_exposures(
    section_props_raw,
    extra_exposure_y_default=extra_exposure_y_default,
    extra_exposure_y_by_id=extra_exposure_y_by_id,
    as_dataframe=True,
)
```

What it does:
- Loads section properties and computes exposure dimensions (e.g., `exposure_y`, `exposure_z`) per section.

Why it matters:
- Exposure determines the “depth” used to convert pressure to line load.

---

### 6) Normalize exposure index type

```python
try:
    exposures_df.index = exposures_df.index.astype(int)
except ValueError:
    pass
```

What it does:
- Attempts to make section IDs numeric for reliable lookup.

---

### 7) Choose depth column based on exposure axis

```python
depth_col = "exposure_z" if exposure_axis.lower() == "z" else "exposure_y"
```

What it does:
- If `exposure_axis="z"` uses vertical depth (`exposure_z`)
- Otherwise uses `exposure_y`

Why it matters:
- Lets you decide which dimension scales the pressure to line load.

---

### 8) Build per-element depth mapping

```python
depth_by_eid: Dict[int, float] = {}
for eid, sect_id in elem_to_sect.items():
    if sect_id in exposures_df.index:
        depth_by_eid[int(eid)] = float(exposures_df.loc[sect_id, depth_col])
```

What it does:
- Assigns each element a depth from its section’s exposure.

---

### 9) Guard: no depths found

```python
if not depth_by_eid:
    print(...)
    return pd.DataFrame()
```

---

### 10) Build per-case pressure plans

```python
for _, row in components_df.iterrows():
    lcname = str(row["load_case"])
    lgname = str(row["load_group"] or lcname)

    p_trans = float(row["p_transverse"])
    p_long = float(row["p_longitudinal"])
```

What it does:
- Reads load case and the two signed pressures.

---

### 11) Transverse pressure → LY plan

```python
if abs(p_trans) > 1e-9:
    plan_t = build_uniform_pressure_beam_load_plan_from_depths(
        group_name=group_name,
        load_case_name=lcname,
        pressure=p_trans,
        udl_direction="LY",
        depth_by_eid=depth_by_eid,
        load_group_name=lgname,
    )
    if not plan_t.empty:
        plans.append(plan_t)
```

What it does:
- Converts pressure into element-wise line loads in `LY`.

Why it matters:
- This is the structural equivalent of transverse WL, but derived from pressure*depth.

---

### 12) Longitudinal pressure → LX plan

```python
if abs(p_long) > 1e-9:
    plan_l = build_uniform_pressure_beam_load_plan_from_depths(
        group_name=group_name,
        load_case_name=lcname,
        pressure=p_long,
        udl_direction="LX",
        depth_by_eid=depth_by_eid,
        load_group_name=lgname,
    )
    if not plan_l.empty:
        plans.append(plan_l)
```

What it does:
- Converts pressure into element-wise line loads in `LX`.

---

### 13) Combine sub-plans

```python
combined_plan = pd.concat(plans, ignore_index=True)
combined_plan.sort_values(["load_case", "element_id"], inplace=True)
combined_plan.reset_index(drop=True, inplace=True)
```

What it does:
- Produces one unified plan DataFrame for the group.
- Sorts for deterministic output.

---

## 3) `apply_structural_wind_loads_to_group(...)`

### Purpose
Backwards-compatible wrapper that:
- builds the WS plan
- summarizes/debugs it
- applies it to MIDAS

---

### 1) Build plan

```python
combined_plan = build_structural_wind_beam_load_plan_for_group(...)
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
    label=f"WS_{group_name}",
    dump_csv_per_case=False,
    write_log=True,
)
```

What it does:
- Produces readable debug output (optionally per-case CSV if enabled).

---

### 4) Apply to MIDAS

```python
apply_beam_load_plan_to_midas(combined_plan)
```

---

## 4) `build_structural_wind_plans_for_deck_groups(...)`

### Purpose
Builds STRUCTURAL wind (WS) plans for **deck groups only** and returns:

- `plans`: list of plan DataFrames (one per group)
- `ws_deck_any`: boolean indicating at least one group produced a plan

---

### 1) Default empty dicts

```python
elements_in_model = elements_in_model or {}
nodes_in_model = nodes_in_model or {}
group_members = group_members or {}
```

What it does:
- Avoids repeated `None` checks later.
- `elements_in_model` / `nodes_in_model` are accepted for compatibility.

---

### 2) Guard: no WS cases table

```python
if ws_cases_df is None or ws_cases_df.empty:
    return [], False
```

---

### 3) Minimal schema validation

```python
needed = {"Case", "Angle", "Value"}
if missing := needed - set(ws_cases_df.columns):
    raise ValueError(...)
```

What it does:
- Ensures the WS case rows have required columns before looping.

---

### 4) Loop groups, build components + plans

```python
for group_name in deck_groups:
    group_name = str(group_name).strip()
    if not group_name:
        continue
```

What it does:
- Normalizes group names and skips blank entries.

---

### 5) Reuse provided element IDs when available

```python
cached_ids = group_members.get(group_name)
element_ids_for_plan = cached_ids if cached_ids else None
```

What it does:
- If the caller already has group membership, use it.
- Otherwise, builder will fetch it from cache.

---

### 6) Build WS components for this group

```python
ws_components = build_structural_wind_components_table(
    group_name=group_name,
    angles=skew.angles,
    transverse=skew.transverse,
    longitudinal=skew.longitudinal,
    ws_cases_df=ws_cases_df,
    wind_pressures_df=wind_pressures_df,
)
```

What it does:
- Computes signed pressures for this group using its `Pz` values.

Why it matters:
- `Pz` depends on group name, so components are group-specific.

---

### 7) Guard: no components

```python
if ws_components is None or ws_components.empty:
    print(...)
    continue
```

---

### 8) Build the WS plan for this group

```python
plan_ws = build_structural_wind_beam_load_plan_for_group(
    group_name=group_name,
    components_df=ws_components,
    exposure_axis="y",
    element_ids=element_ids_for_plan,
    elements_in_model=elements_in_model,
    nodes_in_model=nodes_in_model,
)
```

What it does:
- Converts pressures to line loads using exposure depths and produces the plan.

Note:
- This function call forces `exposure_axis="y"` for deck groups.

---

### 9) Optional debug dump

```python
if plan_ws is not None and not plan_ws.empty:
    if dbg is not None and getattr(dbg, "enabled", False):
        dbg.dump_plan(plan_ws, label=f"WS_DECK_{group_name}", split_per_case=True)
```

What it does:
- Writes plan outputs if debug is enabled, typically split per load case.

---

### 10) Collect outputs + applied flag

```python
plans.append(plan_ws)
ws_deck_any = True
```

---

## Data flow summary

1. Read WS case rows: `(Case, Angle, Value)`
2. Look up `Pz (ksf)` for `(Group, Load Case)`
3. Look up skew coefficients for `Angle`
4. Apply quadrant sign rules based on `Value` (load case name)
5. Compute signed pressures:
   - `p_transverse = Pz * t_coeff`
   - `p_longitudinal = Pz * l_coeff`
6. Resolve elements -> sections -> exposures -> `depth_by_eid`
7. Convert pressures into line loads:
   - `line_load = pressure * depth_by_eid[element_id]`
8. Build combined plan and optionally apply/dump debug
