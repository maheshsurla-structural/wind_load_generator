## `build_pressure_plan_from_components(...) -> pd.DataFrame`

Build a **combined beam-load plan** from a `components_df` where the component columns are **pressures** (typically `ksf`), not line loads.

This function converts each pressure into an **element-specific line load** (`k/ft`) using the element’s **exposure depth** (in `ft`), then builds a plan DataFrame that can later be applied to MIDAS beam loads.

### Key idea

For each element:

\[
\text{line\_load (k/ft)} = \text{pressure (ksf)} \times \text{exposure\_depth (ft)}
\]

- Pressure is constant per row (per load case/component)
- Exposure depth can vary per element (based on section properties and axis)

---

### Implementation

```py
def build_pressure_plan_from_components(
    *,
    group_name: str,
    components_df: pd.DataFrame,
    component_map: Mapping[str, Tuple[str, str]],
    # {pressure_col: (udl_direction, axis)} where axis is "y" or "z"
    element_ids: list[int],
    extra_exposure_y_default: float = 0.0,
    extra_exposure_y_by_id: Dict[int, float] | None = None,
    load_case_col: str = "load_case",
    load_group_col: str = "load_group",
) -> pd.DataFrame:
    """
    Build a combined plan from a components_df where component columns are pressures (ksf).
    Converts pressure -> line load per element via exposure depth.
    """
    if components_df is None or components_df.empty:
        return pd.DataFrame()
    if not element_ids:
        return pd.DataFrame()

    # build the needed depth maps once
    depth_maps: Dict[str, Dict[int, float]] = {}
    for index, axis in component_map.values():
        axis = str(axis).lower()
        if axis not in depth_maps:
            depth_maps[axis] = _depth_map_for_axis(
                element_ids=element_ids,
                axis=axis,
                extra_exposure_y_default=extra_exposure_y_default,
                extra_exposure_y_by_id=extra_exposure_y_by_id,
            )

    plans: list[pd.DataFrame] = []

    for index, row in components_df.iterrows():
        lc = str(row.get(load_case_col, "")).strip()
        if not lc:
            continue
        lg = str(row.get(load_group_col) or lc)

        for p_col, (direction, axis) in component_map.items():
            p = float(row.get(p_col, 0.0))
            if abs(p) <= EPS:
                continue

            axis = str(axis).lower()
            depth_by_eid = depth_maps.get(axis) or {}
            if not depth_by_eid:
                continue

            plan = convert_pressure_to_line_loads_by_exposure_depth(
                group_name=group_name,
                load_case_name=lc,
                pressure=p,
                udl_direction=direction,
                depth_by_eid=depth_by_eid,
                load_group_name=lg,
            )
            if plan is not None and not plan.empty:
                plans.append(plan)

    return combine_plans(plans)
```

---

## Parameters

- `group_name: str`
  - Group label used for metadata in the created plans.

- `components_df: pd.DataFrame`
  - Each row corresponds to a load case (and optional load group).
  - Contains one or more **pressure** columns (ksf), whose names are keys in `component_map`.

- `component_map: Mapping[str, Tuple[str, str]]`
  - Describes how each pressure column should be interpreted/applied:
    - key = pressure column name in `components_df`
    - value = `(udl_direction, axis)`
  - Example:

    ```py
    {
      "p_transverse": ("LY", "y"),
      "p_vertical":   ("LZ", "z"),
    }
    ```

- `element_ids: list[int]`
  - Element IDs to generate loads for. Must be non-empty.

- `extra_exposure_y_default`, `extra_exposure_y_by_id`
  - Passed down to `_depth_map_for_axis(...)` when building exposure depths for axis `"y"`.
  - Used to “add extra exposed depth” (e.g., railings, parapets) to Y exposure.

- `load_case_col: str = "load_case"`
  - Column name holding the load case string.

- `load_group_col: str = "load_group"`
  - Column name holding the load group string.

---

## Output

A single combined plan DataFrame created by concatenating and sorting many sub-plans.

- Each sub-plan is produced by `convert_pressure_to_line_loads_by_exposure_depth(...)`.
- Final output is produced by `combine_plans(plans)`.

---

## Step-by-step behavior

### 1) Guard clauses

```py
if components_df is None or components_df.empty:
    return pd.DataFrame()
if not element_ids:
    return pd.DataFrame()
```

- If there is nothing to process, return an empty DataFrame.

---

### 2) Pre-compute depth maps per axis (once)

```py
depth_maps: Dict[str, Dict[int, float]] = {}
for index, axis in component_map.values():
    axis = str(axis).lower()
    if axis not in depth_maps:
        depth_maps[axis] = _depth_map_for_axis(...)
```

`component_map` can reference axis `"y"` and/or `"z"`.

This loop ensures:
- `_depth_map_for_axis(...)` is called at most once per axis
- you end up with:

```py
depth_maps = {
  "y": {eid -> exposure_y_depth},
  "z": {eid -> exposure_z_depth},
}
```

This is an efficiency win: you don’t want to recompute exposure maps for every row.

> Note: the variable name `index` here is misleading; it’s actually the `direction` value from the tuple.
> It doesn’t break functionality because it’s unused.

---

### 3) Iterate each load case row in `components_df`

```py
for index, row in components_df.iterrows():
```

Per row:
- read `load_case` (`lc`)
- read `load_group` (`lg`, defaults to `lc`)

```py
lc = str(row.get(load_case_col, "")).strip()
if not lc:
    continue
lg = str(row.get(load_group_col) or lc)
```

Rows with blank load case are skipped.

---

### 4) For each pressure column, convert pressure → per-element line loads

```py
for p_col, (direction, axis) in component_map.items():
    p = float(row.get(p_col, 0.0))
    if abs(p) <= EPS:
        continue
```

- Read pressure from the row (default to `0.0` if missing).
- Skip near-zero pressures using `EPS`.

Then choose the correct depth map:

```py
axis = str(axis).lower()
depth_by_eid = depth_maps.get(axis) or {}
if not depth_by_eid:
    continue
```

If you have no depth map (e.g., exposure computation failed), skip.

---

### 5) Build a plan DataFrame for that pressure component

```py
plan = convert_pressure_to_line_loads_by_exposure_depth(
    group_name=group_name,
    load_case_name=lc,
    pressure=p,
    udl_direction=direction,
    depth_by_eid=depth_by_eid,
    load_group_name=lg,
)
```

This is the key conversion step.

Conceptually, inside that converter the logic is typically:

```py
for eid, depth in depth_by_eid.items():
    line_load = pressure * depth
    add row (eid, lc, direction, line_load, lg, group_name, ...)
```

So each element can receive a different `line_load` because depth varies per element.

---

### 6) Collect plans and combine them

```py
if plan is not None and not plan.empty:
    plans.append(plan)

return combine_plans(plans)
```

- Gather all non-empty sub-plans.
- Merge them into a single DataFrame with deterministic sorting.

---

## Worked examples

### Example A — single pressure column in Y axis

#### Inputs

```py
component_map = {
  "p_y": ("LY", "y"),   # pressure column p_y applies as LY using exposure_y
}

element_ids = [101, 102]

components_df =
  load_case  load_group    p_y
0 WL_Q1_0    WL_Q1         0.50
```

Assume `_depth_map_for_axis(..., axis="y")` returns:

```py
depth_by_eid = {101: 4.0, 102: 6.0}  # ft
```

#### Conversion (per element)

- element 101: `line_load = 0.50 * 4.0 = 2.0 k/ft`
- element 102: `line_load = 0.50 * 6.0 = 3.0 k/ft`

#### Output (conceptual)

| load_case | element_id | load_direction | line_load | load_group |
|----------|-----------:|----------------|----------:|-----------|
| WL_Q1_0  | 101        | LY             | 2.0       | WL_Q1     |
| WL_Q1_0  | 102        | LY             | 3.0       | WL_Q1     |

---

### Example B — two pressure columns, using Y and Z axes

```py
component_map = {
  "p_side": ("LY", "y"),
  "p_up":   ("LZ", "z"),
}

components_df =
  load_case  p_side  p_up
0 WL_Q1_0     0.50   0.20
```

Assume:
- `_depth_map_for_axis(axis="y")` → `{101: 4.0, 102: 6.0}`
- `_depth_map_for_axis(axis="z")` → `{101: 3.0, 102: 3.0}`

Then sub-plans created:
- for `p_side` in LY:
  - 101: `0.50*4.0=2.0`
  - 102: `0.50*6.0=3.0`
- for `p_up` in LZ:
  - 101: `0.20*3.0=0.6`
  - 102: `0.20*3.0=0.6`

Final combined output will contain rows for both directions/components.

---

### Example C — pressure column missing in df (treated as 0.0)

If a row doesn’t have a column named `p_y`, then:

```py
p = float(row.get("p_y", 0.0))  # -> 0.0
```

So it will be skipped due to:

```py
if abs(p) <= EPS:
    continue
```

---

## Notes / gotchas (based on your actual code)

- `component_map.values()` tuples are `(direction, axis)`, but the loop uses:

  ```py
  for index, axis in component_map.values():
  ```

  Here `index` is actually the **direction**; it is unused, so behavior is fine.
  (Renaming would improve readability, but not required for correctness.)

- Only `"z"` explicitly selects Z exposure; anything else uses Y exposure inside `_depth_map_for_axis` logic.
- If exposure depth maps cannot be built (no section mapping / missing properties), those pressure components are skipped.
- Final output sorting is handled by `combine_plans`, which sorts by `load_case` then `element_id`.
