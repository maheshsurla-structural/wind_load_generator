# Notes: `core/wind_load/substructure_wind_loads.py`

## Purpose
This module builds **SUBSTRUCTURE structural wind (WS)** beam-load plans for MIDAS.

It is similar to deck structural wind, but with key differences:

- Substructure wind direction is defined by an **angle θ** measured in the **group’s local (Y,Z) plane**
- Loads are decomposed into **local-Y** and **local-Z** pressure components:
  - `p_local_y = P * cos(θ)`
  - `p_local_z = P * sin(θ)`
- The angle θ may be **adjusted** by a **pier-frame orientation offset** so all substructure groups are consistent with the pier reference.
- Quadrant naming (`Q1..Q4`) in the final load case name is used to apply sign flips (same helpers as live wind).

The module produces:

1. **Components table**: per load case → signed pressures in local Y and Z  
2. **Beam-load plan**: per group → element-wise line loads in `LY` and `LZ` directions (pressure × exposure depth)
3. Wrappers:
   - apply one group
   - build for many substructure groups

---

## Key concepts used in this module

### 1) Pier-frame orientation normalization (angle offset)
Substructure groups may not share the same local axis orientation as the pier reference group.
To keep wind directions consistent, the code computes a delta angle:

- δ = angle(pier local Y → group local Y) about pier local X

Then it uses:

- `θ_eff = θ_design - δ`

So “0°” always means “along the group’s own local +Y”, but design angles stay referenced to the pier frame.

---

### 2) Substructure loads are in local Y and local Z (LY + LZ)
Unlike deck:
- Deck WS uses `LY` and `LX` (transverse/longitudinal)
- Substructure WS uses `LY` and `LZ` (in-plane Y/Z components for pier frames)

---

### 3) Pressure → line load uses exposure depths (per element)
For each element:

- `q_LY = p_local_y * exposure_y`
- `q_LZ = p_local_z * exposure_z`

Depths come from `compute_section_exposures()` per section, mapped to elements by `_get_element_to_section_map()`.

---

### 4) Quadrant naming drives sign logic (same as WL)
Final MIDAS case name (`Value`) may contain `Q1..Q4`.

The module reuses live wind helpers:

- `_extract_quadrant_from_name(lcname)`
- `_apply_quadrant_signs(q, base_y, base_z)`

Here it interprets:

- `T ≡ local Y`
- `L ≡ local Z`

so quadrant rules flip the two components consistently.

---

## Imports and dependencies

```python
from typing import Dict, Iterable, Mapping, Tuple, List
import math
import pandas as pd
import numpy as np
from functools import lru_cache
```

- `math`: trig (cos/sin), angle conversions
- `numpy`: vector math for signed angles
- `lru_cache`: caching computed local axes and offsets
- `pandas`: tables and plans

```python
from core.wind_load.group_cache import get_group_element_ids
from core.wind_load.compute_section_exposures import compute_section_exposures
from core.wind_load.beam_load import (
    build_uniform_pressure_beam_load_plan_from_depths,
    _get_element_to_section_map,
    apply_beam_load_plan_to_midas,
    get_section_properties_cached,
)
from core.wind_load.debug_utils import summarize_plan
from core.wind_load.live_wind_loads import (
    _extract_quadrant_from_name,
    _apply_quadrant_signs,
)
from wind_database import wind_db
```

- `get_group_element_ids`: group membership
- `compute_section_exposures`: returns exposure_y / exposure_z per section
- `_get_element_to_section_map`: element -> section ID
- `build_uniform_pressure_beam_load_plan_from_depths`: pressure × depth → element line loads
- `summarize_plan`: debug summary
- live wind quadrant helpers: reuse sign logic
- `wind_db`: pressure table + pier reference mapping

```python
from core.geometry.midas_element_local_axes import MidasElementLocalAxes
from core.geometry.element_local_axes import LocalAxes
```

- Used to compute representative **local axes** per group from MIDAS geometry.

---

## Pier-frame orientation helpers

### `_axes_helper` + `_get_axes_helper()`

```python
_axes_helper: MidasElementLocalAxes | None = None

def _get_axes_helper() -> MidasElementLocalAxes:
    global _axes_helper
    if _axes_helper is None:
        _axes_helper = MidasElementLocalAxes.from_midas()
    return _axes_helper
```

What it does:
- Creates a lazy singleton wrapper around `MidasElementLocalAxes.from_midas()`.
- Prevents repeated MIDAS API hits.

Why it matters:
- Local axes computation may require querying MIDAS and can be expensive.

---

### `_get_group_local_axes(group_name: str) -> LocalAxes` (cached)

```python
@lru_cache(maxsize=128)
def _get_group_local_axes(group_name: str) -> LocalAxes:
    helper = _get_axes_helper()
    element_ids = get_group_element_ids(group_name)
    if not element_ids:
        raise RuntimeError(...)
    elem_id = element_ids[0]
    return helper.compute_local_axes_for_element(elem_id)
```

What it does:
- Picks the **first element** in a group as a representative orientation reference.
- Computes its local axes and returns them.
- Uses LRU caching so repeated requests for the same group are fast.

Why it matters:
- Needed to compute angle offsets between pier reference and group orientation.

Important assumption:
- Group local axes are “consistent enough” that the first element’s axes represent the group.

---

### `_signed_angle_about_axis(...)`

```python
def _signed_angle_about_axis(v_from, v_to, axis, tol=1e-9) -> float:
    ...
```

Purpose:
Computes the signed angle (degrees) rotating `v_from → v_to` **about** a given axis using the right-hand rule.

How it works:
1. Normalizes the rotation axis
2. Projects both vectors onto the plane perpendicular to the axis
3. Computes:
   - `cos = dot(a, b)`
   - `sin = dot(axis, cross(a, b))`
4. Returns `atan2(sin, cos)` in degrees

Why it matters:
- Produces a direction-aware angle (positive/negative), not just magnitude.

---

### `_get_angle_offset_from_pier(group_name: str) -> float` (cached)

```python
@lru_cache(maxsize=256)
def _get_angle_offset_from_pier(group_name: str) -> float:
    pier_group = wind_db.get_pier_reference_for_group(group_name)
    if not pier_group or pier_group == group_name:
        return 0.0
    ...
    delta = _signed_angle_about_axis(
        pier_axes.ey,
        grp_axes.ey,
        pier_axes.ex,
    )
    return delta
```

What it does:
- Gets the pier reference group for `group_name` from the DB.
- If no reference exists, returns 0.0.
- Computes:
  - δ = signed angle from `pier ey` to `group ey` about `pier ex`

Why it matters:
- Lets you express wind directions defined “relative to the pier” and convert them into the group’s local (Y,Z) plane.

---

## 1) `build_substructure_wind_components_table(...)`

### Purpose
Builds a per-load-case components table for substructure wind in **local Y** and **local Z**.

Inputs:
- `group_name`: used to look up pressure `P` for this group
- `ws_cases_df`: `Case / Angle / Value`
- `wind_pressures_df`: pressure table (defaults to `wind_db.wind_pressures`)

Output columns:
- `load_case`, `load_group`
- `angle` (effective angle after pier offset)
- `design_angle` (original input angle)
- `base_case`
- `P` (ksf)
- `p_local_y`, `p_local_z` (ksf, signed)

---

### 1) Default pressure table source

```python
if wind_pressures_df is None:
    wind_pressures_df = wind_db.wind_pressures
```

---

### 2) Early return on missing inputs

```python
if wind_pressures_df is None or wind_pressures_df.empty or ws_cases_df is None or ws_cases_df.empty:
    return pd.DataFrame(columns=[...])
```

What it does:
- Returns an empty but correctly-shaped DataFrame when there is nothing to compute.

---

### 3) Validate required columns

```python
needed_ws = {"Case", "Angle", "Value"}
...
needed_p = {"Group", "Load Case", "Pz (ksf)"}
...
```

What it does:
- Ensures the WS case table and pressure table contain required columns.

---

### 4) Compute pier orientation delta once per group

```python
delta = _get_angle_offset_from_pier(group_name)
```

What it does:
- Computes δ between pier reference and this group’s orientation.
- Reused for all rows in this group.

---

### 5) Iterate WS rows and compute effective angle

```python
ang_design = float(ws_row["Angle"])
ang_eff = ang_design - delta
theta = math.radians(ang_eff)
```

What it does:
- Reads the *design* angle from the table.
- Converts it to an *effective* angle in the group’s own local frame by subtracting δ.
- Converts to radians for trig.

Why it matters:
- Keeps load directions consistent across differently oriented groups.

---

### 6) Look up pressure magnitude `P` for (group, base_case)

```python
mask = (
    (wind_pressures_df["Group"] == group_name)
    & (wind_pressures_df["Load Case"] == base_case)
)
sub = wind_pressures_df[mask]
...
P = float(sub.iloc[0]["Pz (ksf)"])
```

What it does:
- Uses `Pz (ksf)` as the horizontal pressure magnitude `P` for substructure.

Note:
- Like deck WS, it takes the first matching row if duplicates exist.

---

### 7) Decompose pressure into local Y and Z components

```python
base_y = P * math.cos(theta)
base_z = P * math.sin(theta)
```

Convention:
- θ measured from local +Y toward local +Z.

Meaning:
- θ = 0° → `(base_y, base_z) = (P, 0)`
- θ = 90° → `(0, P)`

---

### 8) Apply quadrant sign logic (T ≡ Y, L ≡ Z)

```python
q = _extract_quadrant_from_name(lcname)
y_signed, z_signed = _apply_quadrant_signs(q, base_y, base_z)
```

What it does:
- Parses quadrant from the final load case name.
- Applies sign flips to the Y and Z components.

---

### 9) Emit rows

```python
rows.append({
    "load_case": lcname,
    "load_group": lcname,
    "angle": ang_eff,
    "design_angle": ang_design,
    "base_case": base_case,
    "P": P,
    "p_local_y": y_signed,
    "p_local_z": z_signed,
})
```

---

### 10) Sort output

```python
out.sort_values(["angle", "load_case"], inplace=True)
out.reset_index(drop=True, inplace=True)
```

---

## 2) `build_substructure_wind_beam_load_plan_for_group(...)`

### Purpose
Builds the combined substructure WS beam-load plan for one group using:
- `p_local_y` applied in `LY`
- `p_local_z` applied in `LZ`

Pressure is converted to line load using exposure depths:
- `q = pressure * exposure_depth`

---

### 1) Guard: no components

```python
if components_df is None or components_df.empty:
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

---

### 3) Map element -> section

```python
elem_to_sect = _get_element_to_section_map(element_ids)
```

Why it matters:
- Exposures are defined per section; elements inherit section exposure.

---

### 4) Compute exposures (Y and Z)

```python
section_props_raw = get_section_properties_cached()
exposures_df = compute_section_exposures(..., as_dataframe=True)
```

What it does:
- Builds exposure dimensions per section including optional extra exposure in Y.

---

### 5) Build per-element depth maps

```python
depth_y_by_eid[eid] = exposures_df.loc[sect_id, "exposure_y"]
depth_z_by_eid[eid] = exposures_df.loc[sect_id, "exposure_z"]
```

What it does:
- Creates two depth lookups:
  - one for local Y
  - one for local Z

---

### 6) Build per-case plans

For each load case row:

- `p_local_y` → `LY` using `depth_y_by_eid`
- `p_local_z` → `LZ` using `depth_z_by_eid`

```python
plan_y = build_uniform_pressure_beam_load_plan_from_depths(..., udl_direction="LY", depth_by_eid=depth_y_by_eid)
plan_z = build_uniform_pressure_beam_load_plan_from_depths(..., udl_direction="LZ", depth_by_eid=depth_z_by_eid)
```

Why it matters:
- Substructure wind acts in Y/Z, so you apply `LY` and `LZ`.

---

### 7) Combine plans

```python
combined_plan = pd.concat(plans, ignore_index=True)
combined_plan.sort_values(["load_case", "element_id"], inplace=True)
combined_plan.reset_index(drop=True, inplace=True)
```

---

## 3) `apply_substructure_wind_loads_to_group(...)`

### Purpose
Backwards-compatible wrapper:
- build plan (LY + LZ)
- summarize/debug it
- apply to MIDAS

Steps:

1. `build_substructure_wind_beam_load_plan_for_group(...)`
2. `summarize_plan(...)`
3. `apply_beam_load_plan_to_midas(...)`

---

## 4) `build_substructure_wind_plans_for_groups(...)`

### Purpose
Builds WS plans for **multiple substructure groups** and returns:

- `plans`: list of plan DataFrames (one per group)
- `ws_sub_any`: boolean indicating at least one group produced loads

---

### 1) Validate WS case table schema

```python
needed = {"Case", "Angle", "Value"}
if missing := needed - set(ws_cases_df.columns):
    raise ValueError(...)
```

---

### 2) Loop substructure groups

For each group:

1. Optionally reuse provided element IDs from `group_members`
2. Build group-specific components table (pressure depends on group)
3. Build plan (LY + LZ)
4. Optionally debug dump using `dbg.dump_plan(...)`
5. Collect plan and set `ws_sub_any=True`

---

## Data flow summary

For each substructure group:

1. Compute pier offset δ (pier Y → group Y about pier X)
2. For each WS case row:
   - θ_eff = θ_design - δ
   - P from pressure table
   - base components:
     - `y = P*cos(θ_eff)`
     - `z = P*sin(θ_eff)`
   - apply quadrant sign flips (Q1..Q4)
3. Map elements → sections → exposures
4. Convert pressures to line loads:
   - `LY = p_local_y * exposure_y`
   - `LZ = p_local_z * exposure_z`
5. Combine into a MIDAS plan and optionally apply/dump debug
