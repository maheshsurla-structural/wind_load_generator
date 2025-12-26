## `build_line_load_plan_from_components(...) -> pd.DataFrame`

Build a **combined beam-load plan** from a `components_df` where each component column already represents a **line load** (typically in `k/ft`).

This function converts “component rows” into one or more **uniform distributed line-load** plans per group, then combines them into one final plan DataFrame.

### Key idea

- Each row in `components_df` typically represents one load case (and optionally one “load group”).
- Each component column (e.g., `transverse`, `longitudinal`) represents a line load value.
- `component_map` tells the function which component column should be applied in which MIDAS direction (e.g., `LY`, `LX`).
- For each `(row, component)` pair that is non-zero, it generates a uniform load plan across `element_ids`.
- Finally, it merges all these small plans into one plan via `combine_plans(plans)`.

---

### Implementation

```py
def build_line_load_plan_from_components(
    *,
    group_name: str,
    components_df: pd.DataFrame,
    component_map: Mapping[str, str],  # {component_col: "LX"/"LY"/...}
    element_ids: list[int],
    eccentricity: float = 0.0,
    load_case_col: str = "load_case",
    load_group_col: str = "load_group",
) -> pd.DataFrame:
    """
    Build a combined plan from a components_df where each component column is already k/ft (line load).
    """
    if components_df is None or components_df.empty:
        return pd.DataFrame()
    if not element_ids:
        return pd.DataFrame()

    plans: list[pd.DataFrame] = []

    for index, row in components_df.iterrows():
        lc = str(row.get(load_case_col, "")).strip()
        if not lc:
            continue
        lg = str(row.get(load_group_col) or lc)

        for col, direction in component_map.items():
            val = float(row.get(col, 0.0))
            if abs(val) <= EPS:
                continue

            plan = build_uniform_load_beam_load_plan_for_group(
                group_name=group_name,
                load_case_name=lc,
                line_load=val,
                udl_direction=direction,
                load_group_name=lg,
                element_ids=element_ids,
                eccentricity=eccentricity,
            )
            if plan is not None and not plan.empty:
                plans.append(plan)

    return combine_plans(plans)
```

---

## Parameters

- `group_name: str`
  - Structural group name for labeling/debugging and for plan builder calls.

- `components_df: pd.DataFrame`
  - Input table of per-load-case component line loads.
  - Each row should typically contain:
    - a load case name (`load_case` by default)
    - optional load group (`load_group` by default)
    - one or more component columns (e.g., `transverse`, `longitudinal`)
  - **Important:** component values are assumed to already be **line loads** (e.g., `k/ft`).

- `component_map: Mapping[str, str]`
  - Mapping of `{component_column_name -> load_direction}`.
  - Example:

    ```py
    {"transverse": "LY", "longitudinal": "LX"}
    ```

- `element_ids: list[int]`
  - Elements to which the uniform line loads will be applied.
  - If empty, returns an empty DataFrame.

- `eccentricity: float = 0.0`
  - Passed through to the uniform load plan builder.
  - Units depend on your model/unit system.

- `load_case_col: str = "load_case"`
  - Column name to read the load case from each row.

- `load_group_col: str = "load_group"`
  - Column name to read the load group from each row.

---

## Output

A single combined plan DataFrame produced by:

- creating many small plans (one per `(load_case, component)` pair)
- then merging them into one plan using `combine_plans(plans)`

If there are no valid loads, `combine_plans([])` should return an empty DataFrame (depending on your implementation).

---

## Step-by-step behavior

### 1) Guard clauses (fail fast)

```py
if components_df is None or components_df.empty:
    return pd.DataFrame()
if not element_ids:
    return pd.DataFrame()
```

- If there are no components or no elements, nothing can be built.

---

### 2) Iterate rows in `components_df`

```py
for index, row in components_df.iterrows():
```

- Processes each row (commonly each row corresponds to a load case).
- `iterrows()` yields:
  - `index` — the row index label
  - `row` — a pandas Series representing that row

---

### 3) Extract load case name (`lc`) and skip blank cases

```py
lc = str(row.get(load_case_col, "")).strip()
if not lc:
    continue
```

- Uses `.get()` so missing columns do not crash immediately.
- Converts to string and strips whitespace.
- If empty after stripping, skips the row.

**Example:**
- `row["load_case"] = "  WL_Q1_0  "` → `lc = "WL_Q1_0"`
- `row["load_case"] = ""` → skip

---

### 4) Determine load group (`lg`)

```py
lg = str(row.get(load_group_col) or lc)
```

- Tries to use the row’s load group.
- If missing or falsy, falls back to the load case name.
- Ensures a string.

So:
- if `load_group` is blank/None → `lg = lc`
- otherwise → `lg = row["load_group"]`

---

### 5) For each component column, create a plan if the value is non-zero

```py
for col, direction in component_map.items():
    val = float(row.get(col, 0.0))
    if abs(val) <= EPS:
        continue
```

- Iterates the component columns defined in `component_map`.
- Reads the component value from the row (defaults to `0.0` if missing).
- Converts to float.
- Skips near-zero values using a tolerance `EPS`.

**Why the EPS check matters**
- Avoids generating meaningless loads due to tiny floating point noise.
- Example: `1e-12` should usually be treated as zero.

---

### 6) Build a uniform line-load plan across all elements

```py
plan = build_uniform_load_beam_load_plan_for_group(
    group_name=group_name,
    load_case_name=lc,
    line_load=val,
    udl_direction=direction,
    load_group_name=lg,
    element_ids=element_ids,
    eccentricity=eccentricity,
)
```

This delegates to a lower-level function that creates a plan DataFrame representing:

- apply `line_load = val` in direction `direction`
- for every element in `element_ids`
- under load case `lc` and load group `lg`
- with eccentricity `eccentricity`

---

### 7) Only keep non-empty plans

```py
if plan is not None and not plan.empty:
    plans.append(plan)
```

- Defensive: builder might return `None` or empty.
- Only non-empty plans get added.

---

### 8) Combine all sub-plans into one final plan

```py
return combine_plans(plans)
```

- `plans` is a list of DataFrames.
- `combine_plans` is expected to merge/concat these into one plan DataFrame.

Common implementations of `combine_plans`:
- `pd.concat(plans, ignore_index=True)`
- optional sorting
- optional grouping/aggregation of duplicates

(Exact behavior depends on your `combine_plans` implementation.)

---

## End-to-end example (conceptual)

### Inputs

```py
group_name = "PIER"
element_ids = [101, 102]

components_df =
  load_case   load_group   transverse   longitudinal
0 WL_Q1_0     WL_Q1        0.10         1.00
1 WL_Q3_0     WL_Q3       -0.10        -1.00

component_map = {"transverse": "LY", "longitudinal": "LX"}
eccentricity = 6.0
```

### Processing

For row 0 (`WL_Q1_0`):
- transverse `0.10` → build uniform plan in `LY`
- longitudinal `1.00` → build uniform plan in `LX`

For row 1 (`WL_Q3_0`):
- transverse `-0.10` → build uniform plan in `LY`
- longitudinal `-1.00` → build uniform plan in `LX`

So total sub-plans created: **4** (2 rows × 2 components).

### Typical sub-plan shape (example)

Each call to `build_uniform_load_beam_load_plan_for_group(...)` might return something like:

| element_id | load_case | load_direction | line_load | eccentricity | load_group |
|----------:|-----------|----------------|----------:|-------------:|-----------|
| 101       | WL_Q1_0   | LY             | 0.10      | 6.0          | WL_Q1     |
| 102       | WL_Q1_0   | LY             | 0.10      | 6.0          | WL_Q1     |

Another sub-plan for longitudinal would have `load_direction="LX"` and `line_load=1.00`, etc.

### Final output

`combine_plans(plans)` merges all sub-plans into one plan DataFrame containing all element/load-direction/load-case entries.

---

## Failure / skip examples

### Blank load case → row skipped

If a row has:

```py
load_case = "   "
```

It is skipped entirely.

### Missing component column → treated as 0.0

If `components_df` lacks a column in `component_map`, `row.get(col, 0.0)` returns `0.0`, and it is skipped.

### Near-zero value → skipped

If `val` is very small:

```py
val = 1e-12
abs(val) <= EPS  # True
```

Then no plan is generated for that component.

---

## Notes / gotchas

- This function assumes component values are already **line loads** (k/ft). It does **no** conversion from pressure or area.
- It uses `iterrows()`; this is fine for small component tables (common in control-driven workflows).
- `load_group` defaults to `load_case` if missing, which is a common “safe default” for grouping.
- The final structure and deduplication behavior depends on `combine_plans(...)`.
