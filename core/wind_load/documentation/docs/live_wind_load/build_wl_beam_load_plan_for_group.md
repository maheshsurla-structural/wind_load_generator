## `build_wl_beam_load_plan_for_group(...) -> pd.DataFrame`

Build a **beam line-load plan** for a given structural group using precomputed wind-load “components”.

This function is a thin adapter around `build_line_load_plan_from_components(...)` that:

1. Validates the `components_df` input
2. Resolves the group’s element IDs (either from the model group database or from a provided list)
3. Maps component columns to MIDAS load directions (`LY`, `LX`)
4. Delegates the actual plan generation to `build_line_load_plan_from_components(...)`

If inputs are missing or invalid (no components or no elements), it returns an **empty DataFrame**.

---

### Implementation

```py
def build_wl_beam_load_plan_for_group(
    group_name: str,
    components_df: pd.DataFrame,
    *,
    eccentricity: float = 6.0,
    element_ids: list[int] | None = None,
    elements_in_model=None,
    nodes_in_model=None,
) -> pd.DataFrame:
    if components_df is None or components_df.empty:
        return pd.DataFrame()

    if element_ids is None:
        eids = get_structural_group_element_ids(group_name)
    else:
        eids = [int(e) for e in element_ids]

    if not eids:
        return pd.DataFrame()

    return build_line_load_plan_from_components(
        group_name=group_name,
        components_df=components_df,
        component_map={"transverse": "LY", "longitudinal": "LX"},
        element_ids=eids,
        eccentricity=eccentricity,
    )
```

---

## Inputs

- `group_name: str`
  - Structural group name used to locate member element IDs (when `element_ids` is not provided).

- `components_df: pd.DataFrame`
  - Per-group components table (typically built earlier in the pipeline).
  - Must be non-empty.
  - Expected to contain component columns referenced by `component_map`, i.e.:
    - `transverse`
    - `longitudinal`
  - Typically also contains columns like `load_case`, `angle`, etc. (exact requirements depend on `build_line_load_plan_from_components`).

- `eccentricity: float = 6.0`
  - Eccentricity passed through to `build_line_load_plan_from_components`.
  - Units depend on your model’s unit system (commonly inches or mm).

- `element_ids: list[int] | None = None`
  - Optional override: explicit element IDs to use instead of looking up the group membership.

- `elements_in_model=None`, `nodes_in_model=None`
  - Present in the signature but not used in the current implementation.
  - These are likely placeholders for future filtering/validation logic.

---

## Output

A plan DataFrame produced by `build_line_load_plan_from_components(...)`.

If there is nothing to build, returns `pd.DataFrame()` (empty).

---

## Step-by-step behavior

### 1) Guard: no components → no plan

```py
if components_df is None or components_df.empty:
    return pd.DataFrame()
```

- If the components table is missing or empty, there is nothing to convert into line loads.
- Returns an empty DataFrame for consistent downstream handling.

**Example:**

```py
build_wl_beam_load_plan_for_group("PIER", pd.DataFrame())
# -> empty DataFrame
```

---

### 2) Resolve element IDs to apply loads to

```py
if element_ids is None:
    eids = get_structural_group_element_ids(group_name)
else:
    eids = [int(e) for e in element_ids]
```

Two modes:

#### Mode A — derive membership from the model group database

- When `element_ids` is not provided, the function uses:

```py
get_structural_group_element_ids(group_name)
```

This typically returns the structural group’s element membership from a cached `/db/GRUP` snapshot.

#### Mode B — use provided element IDs

- When `element_ids` is provided, it is normalized into `list[int]`:

```py
[int(e) for e in element_ids]
```

This ensures a stable type even if inputs are strings or numpy ints.

**Example:**

```py
element_ids = ["101", 102, 103]
# eids becomes [101, 102, 103]
```

---

### 3) Guard: no element IDs → no plan

```py
if not eids:
    return pd.DataFrame()
```

- If the group has no members, or membership lookup failed, there’s nowhere to assign loads.
- Returns an empty DataFrame.

**Example:**

```py
# Suppose get_structural_group_element_ids("EMPTY") returns []
build_wl_beam_load_plan_for_group("EMPTY", components_df)
# -> empty DataFrame
```

---

### 4) Build the plan using shared builder

```py
return build_line_load_plan_from_components(
    group_name=group_name,
    components_df=components_df,
    component_map={"transverse": "LY", "longitudinal": "LX"},
    element_ids=eids,
    eccentricity=eccentricity,
)
```

This delegates plan creation to `build_line_load_plan_from_components(...)`.

#### `component_map={"transverse": "LY", "longitudinal": "LX"}`

This mapping tells the builder:

- take the `components_df["transverse"]` component and create loads in direction `LY`
- take the `components_df["longitudinal"]` component and create loads in direction `LX`

So the function encodes a domain rule:

- transverse wind component → apply as `LY`
- longitudinal wind component → apply as `LX`

---

## End-to-end example (conceptual)

### Input components

Assume `components_df` has one row per load case for the group:

| load_case  | angle | transverse | longitudinal |
|-----------|------:|-----------:|-------------:|
| WL_Q1_0   | 0     |  0.10      |  1.00        |
| WL_Q3_0   | 0     | -0.10      | -1.00        |

And suppose the group contains elements:

```py
eids = [101, 102, 103]
```

### What this function does

It calls the builder with:

- `element_ids=[101, 102, 103]`
- `component_map={"transverse": "LY", "longitudinal": "LX"}`
- `eccentricity=6.0`

### Example output shape (typical)

The exact columns depend on `build_line_load_plan_from_components`, but a common plan table might look like:

| element_id | load_case | load_direction | line_load | eccentricity | load_group |
|----------:|-----------|----------------|----------:|-------------:|-----------|
| 101       | WL_Q1_0   | LY             | ...       | 6.0          | ...       |
| 101       | WL_Q1_0   | LX             | ...       | 6.0          | ...       |
| 102       | WL_Q1_0   | LY             | ...       | 6.0          | ...       |
| ...       | ...       | ...            | ...       | ...          | ...       |

The important point is:

- Each component column becomes loads in a specific direction (LY/LX)
- Loads are generated for every element in `eids`

---

## Notes / gotchas

- `elements_in_model` and `nodes_in_model` are currently unused; passing them has no effect.
- If `element_ids` is omitted, group membership depends entirely on `get_structural_group_element_ids(group_name)`.
- If an empty DataFrame is returned, it usually means:
  - no components, or
  - no elements found for the group.
```
