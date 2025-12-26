## `combine_plans(plans: list[pd.DataFrame]) -> pd.DataFrame` — Updated Notes (based on actual usage)

### Purpose

`combine_plans` is the **final aggregation step** for the plan-building pipeline.

In this codebase, it is called from:

- `build_line_load_plan_from_components(...)`
  - which generates sub-plans via `build_uniform_load_beam_load_plan_for_group(...)`
- `build_pressure_plan_from_components(...)`
  - which generates sub-plans via `convert_pressure_to_line_loads_by_exposure_depth(...)`

Those two sources may produce plan DataFrames with **slightly different sets of columns**, but they share the **core columns** needed for sorting and downstream consistency.

---

### Implementation

```py
def combine_plans(plans: list[pd.DataFrame]) -> pd.DataFrame:
    """
    Combine plan dfs into one (sorted).
    """
    if not plans:
        return pd.DataFrame()
    out = pd.concat(plans, ignore_index=True)
    out.sort_values(["load_case", "element_id"], inplace=True)
    out.reset_index(drop=True, inplace=True)
    return out
```

---

## What “plans” look like in this project

### A) Sub-plans from `build_uniform_load_beam_load_plan_for_group(...)`

These are created in `build_line_load_plan_from_components(...)`:

```py
plan = build_uniform_load_beam_load_plan_for_group(...)
plans.append(plan)
```

Typical columns for these sub-plans (based on your documented function):

- `element_id` (int)
- `line_load` (float)
- `load_case` (str)
- `load_direction` (str) — e.g. `"LX"`, `"LY"`
- `load_group` (str)
- `group_name` (str)
- `eccentricity` (float)

### B) Sub-plans from `convert_pressure_to_line_loads_by_exposure_depth(...)`

These are created in `build_pressure_plan_from_components(...)`:

```py
plan = convert_pressure_to_line_loads_by_exposure_depth(...)
plans.append(plan)
```

These plans are also expected to include at least:

- `element_id`
- `load_case`

…and commonly also:

- `line_load` (because pressure is converted to line load per element)
- `load_direction`
- `load_group`
- (plus possibly extra metadata columns such as `pressure`, `exposure_depth`, etc., depending on your implementation)

> Important: Even if the pressure-based plan contains extra columns not present in uniform-load plans, `pd.concat` can still combine them — missing columns become `NaN` for rows that don’t have them.

---

## Step-by-step behavior (what it actually does)

### 1) If no sub-plans exist, return empty DataFrame

```py
if not plans:
    return pd.DataFrame()
```

This happens when upstream logic skips everything, e.g.:

- `components_df` empty
- all component values are ~0 (`abs(val) <= EPS`)
- no element IDs or no depth maps available

---

### 2) Concatenate all sub-plans into one DataFrame

```py
out = pd.concat(plans, ignore_index=True)
```

Key behavior of `pd.concat` in your usage:

- Rows are stacked vertically.
- `ignore_index=True` ensures a clean 0..N-1 index.
- If some plan DFs have extra columns and others don’t:
  - the result contains the **union of all columns**
  - missing values become `NaN`

**Example (different schemas):**

- uniform-load plan columns: `element_id, load_case, line_load, eccentricity`
- pressure-based plan columns: `element_id, load_case, line_load, pressure`

After concat, output columns include both `eccentricity` and `pressure`,
and each row has `NaN` for whichever column it didn’t originate with.

---

### 3) Sort by the two “contract” columns

```py
out.sort_values(["load_case", "element_id"], inplace=True)
```

This enforces deterministic ordering across the entire output:

1. group by `load_case`
2. sort elements within each case by `element_id`

**Why this matters in your pipeline:**
- You generate many sub-plans across load cases and directions.
- Sorting makes:
  - debug output stable
  - comparisons between runs easier
  - application order consistent

> Contract: Every plan DF passed to `combine_plans` must contain `load_case` and `element_id`.
> If any sub-plan is missing either, this will raise a `KeyError`.

---

### 4) Reset index after sorting

```py
out.reset_index(drop=True, inplace=True)
```

Sorting keeps the old row indices; this resets them to `0..N-1`.

---

## Concrete end-to-end example (mirrors actual usage)

Assume two sub-plans were created:

### Sub-plan 1 (uniform load, from `build_uniform_load_beam_load_plan_for_group`)
| load_case | element_id | load_direction | line_load | eccentricity |
|----------|-----------:|----------------|----------:|-------------:|
| WL_Q1_0  | 102        | LY             | 0.10      | 6.0          |
| WL_Q1_0  | 101        | LY             | 0.10      | 6.0          |

### Sub-plan 2 (pressure-converted plan, from `convert_pressure_to_line_loads_by_exposure_depth`)
| load_case | element_id | load_direction | line_load | pressure |
|----------|-----------:|----------------|----------:|---------:|
| WL_Q1_0  | 101        | LX             | 1.00      | 0.50     |
| WL_Q1_0  | 102        | LX             | 1.10      | 0.50     |

Now:

```py
out = combine_plans([df1, df2])
```

Result (after concat + sort):

| load_case | element_id | load_direction | line_load | eccentricity | pressure |
|----------|-----------:|----------------|----------:|-------------:|---------:|
| WL_Q1_0  | 101        | LY             | 0.10      | 6.0          | NaN      |
| WL_Q1_0  | 101        | LX             | 1.00      | NaN          | 0.50     |
| WL_Q1_0  | 102        | LY             | 0.10      | 6.0          | NaN      |
| WL_Q1_0  | 102        | LX             | 1.10      | NaN          | 0.50     |

This shows the **real “different DF shapes” behavior**:
- concat keeps all columns
- missing columns fill with `NaN`
- sorting uses only `load_case` and `element_id`

---

## Notes / gotchas (based on your actual pipeline)

- ✅ Safe to combine sub-plans from different builders **as long as** they include `load_case` and `element_id`.
- ✅ It’s normal for some rows to have `NaN` in columns like `eccentricity` (pressure plans) or `pressure` (uniform plans).
- ❗ `combine_plans` does not deduplicate rows. If two sub-plans produce identical rows, both remain.
- ❗ If you ever want to sort more deterministically when multiple rows share the same `(load_case, element_id)` (e.g., different `load_direction`), you could extend sorting to:
  - `["load_case", "element_id", "load_direction"]`
  (but that would be a code change; current behavior is fine if stable enough for you.)

