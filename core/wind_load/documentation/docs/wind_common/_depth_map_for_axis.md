## `_depth_map_for_axis(...) -> Dict[int, float]`

Build a mapping `{element_id -> exposure_depth}` for a requested axis (`"y"` or `"z"`).

This helper resolves, **once per group**, the “effective depth” used to convert **pressure (ksf)** into **line load (k/ft)**:

- If axis is `"y"` → uses `exposure_y`
- If axis is `"z"` → uses `exposure_z`

It does this by:
1. mapping each element ID to its section ID (`_get_element_to_section_map`)
2. computing exposures per section (`compute_section_exposures(...)`)
3. creating a dictionary mapping each element to the exposure depth for its section

This output is later used in the pressure conversion workflow:

```py
line_load[eid] = pressure * depth_by_eid[eid]
```

---

### Implementation

```py
def _depth_map_for_axis(
    *,
    element_ids: list[int],
    axis: str,  # "y" or "z"
    extra_exposure_y_default: float = 0.0,
    extra_exposure_y_by_id: Dict[int, float] | None = None,
) -> Dict[int, float]:
    """
    Resolve depth_by_eid for exposure_y or exposure_z once.
    """
    if not element_ids:
        return {}

    elem_to_sect = _get_element_to_section_map(element_ids)
    if not elem_to_sect:
        return {}

    section_props_raw = get_section_properties_cached()
    exposures_df = compute_section_exposures(
        section_props_raw,
        extra_exposure_y_default=extra_exposure_y_default,
        extra_exposure_y_by_id=extra_exposure_y_by_id,
        as_dataframe=True,
    )
    if exposures_df is None or exposures_df.empty:
        return {}

    try:
        exposures_df.index = exposures_df.index.astype(int)
    except ValueError:
        pass

    col = "exposure_z" if str(axis).lower() == "z" else "exposure_y"

    depth_by_eid: Dict[int, float] = {}
    for eid, sect_id in elem_to_sect.items():
        if sect_id in exposures_df.index:
            depth_by_eid[int(eid)] = float(exposures_df.loc[sect_id, col])

    return depth_by_eid
```

---

## Parameters

- `element_ids: list[int]`
  - Element IDs for which you want exposure depth values.

- `axis: str`
  - `"y"` or `"z"` (case-insensitive).
  - Determines which exposure column is used:
    - `"y"` → `exposure_y`
    - `"z"` → `exposure_z`

- `extra_exposure_y_default: float = 0.0`
  - Default additional exposure depth added to **Y exposure** (applied by `compute_section_exposures`).

- `extra_exposure_y_by_id: Dict[int, float] | None = None`
  - Per-section (or per-ID, depending on your `compute_section_exposures` implementation) overrides for additional Y exposure.

> Note: Only Y has “extra exposure” parameters here. Z exposure does not get these extras in this helper.

---

## Output

Returns a dictionary:

```py
depth_by_eid: Dict[int, float]  # {element_id -> exposure_depth}
```

Example:

```py
{
  101: 4.0,   # element 101 uses section whose exposure_y is 4.0
  102: 4.0,
  201: 6.5,
}
```

---

## Step-by-step behavior

### 1) Guard: no elements → nothing to compute

```py
if not element_ids:
    return {}
```

---

### 2) Map each element to its section ID

```py
elem_to_sect = _get_element_to_section_map(element_ids)
if not elem_to_sect:
    return {}
```

Expected shape:

```py
elem_to_sect = {
  101: 10,   # element 101 uses section 10
  102: 10,
  201: 12,
}
```

If this mapping fails or returns empty, exposure cannot be resolved.

---

### 3) Get section properties and compute exposures per section

```py
section_props_raw = get_section_properties_cached()
exposures_df = compute_section_exposures(
    section_props_raw,
    extra_exposure_y_default=extra_exposure_y_default,
    extra_exposure_y_by_id=extra_exposure_y_by_id,
    as_dataframe=True,
)
if exposures_df is None or exposures_df.empty:
    return {}
```

`compute_section_exposures(...)` is expected to return a DataFrame indexed by **section ID** with columns including:

- `exposure_y`
- `exposure_z`

Example `exposures_df`:

| section_id | exposure_y | exposure_z |
|----------:|-----------:|-----------:|
| 10        | 4.0        | 3.5        |
| 12        | 6.5        | 5.0        |

(Exact values/units depend on your section property model.)

---

### 4) Try to ensure the index is integer section IDs

```py
try:
    exposures_df.index = exposures_df.index.astype(int)
except ValueError:
    pass
```

Why this exists:
- Sometimes a DataFrame index might be string IDs like `"10"`, `"12"`.
- Converting to `int` helps membership checks like:

```py
if sect_id in exposures_df.index:
```

If conversion fails (mixed index values), it leaves the index as-is.

---

### 5) Decide which exposure column to read

```py
col = "exposure_z" if str(axis).lower() == "z" else "exposure_y"
```

- If `axis` is `"z"` (any case) → use `exposure_z`
- Otherwise → default to `exposure_y`

So `"Y"`, `"y"`, `"something"` all map to `exposure_y` unless axis is explicitly `"z"`.

---

### 6) Build `{element_id -> exposure_depth}`

```py
depth_by_eid: Dict[int, float] = {}
for eid, sect_id in elem_to_sect.items():
    if sect_id in exposures_df.index:
        depth_by_eid[int(eid)] = float(exposures_df.loc[sect_id, col])
```

For each element:
- find its section ID
- if that section exists in `exposures_df`, store:

```py
depth_by_eid[element_id] = exposures_df.loc[section_id, exposure_col]
```

Elements whose section ID is not found are skipped.

---

## Worked examples

### Example A — axis `"y"` (exposure_y)

Input:

```py
element_ids = [101, 102, 201]
axis = "y"
```

Assume:

```py
elem_to_sect = {101: 10, 102: 10, 201: 12}

exposures_df (index = section_id):
10 -> exposure_y = 4.0
12 -> exposure_y = 6.5
```

Then:

```py
_depth_map_for_axis(element_ids=[101,102,201], axis="y")
# -> {101: 4.0, 102: 4.0, 201: 6.5}
```

---

### Example B — axis `"z"` (exposure_z)

Same mapping, but exposures:

- section 10 exposure_z = 3.5
- section 12 exposure_z = 5.0

```py
_depth_map_for_axis(element_ids=[101,102,201], axis="z")
# -> {101: 3.5, 102: 3.5, 201: 5.0}
```

---

### Example C — section not found (skipped element)

Assume:

```py
elem_to_sect = {101: 10, 999: 99}
exposures_df has only sections {10, 12}
```

Then element `999` is skipped:

```py
# -> {101: 4.0}
```

---

## How this is used downstream (pressure → line load)

Later in `build_pressure_plan_from_components(...)`, you do:

- build `depth_by_eid` once per axis
- for each pressure `p`, convert per element:

Conceptually:

```py
line_load_eid = p * depth_by_eid[eid]
```

So if:
- `pressure = 0.50 ksf`
- `exposure_y = 4.0 ft`

Then:
- `line_load = 0.50 * 4.0 = 2.0 k/ft`

---

## Notes / gotchas

- Axis handling is “fail-soft”:
  - only `"z"` selects `exposure_z`
  - everything else defaults to `exposure_y`
- The function returns `{}` if any upstream dependency returns nothing:
  - no element IDs
  - no element→section mapping
  - no exposures data
- Elements whose section ID is missing from exposures are simply omitted from the output mapping.
