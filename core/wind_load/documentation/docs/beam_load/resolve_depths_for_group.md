# `resolve_depths_for_group` — Detailed Notes (Full Explanation)

## Purpose
This function produces a mapping:

`{element_id: exposure_depth}`

for all elements in a given MIDAS **group**.

It works by:
1. Getting all element IDs in `group_name`
2. Mapping each element → its section property ID (SECT)
3. Computing exposures for all section properties (Y and Z) using `compute_section_exposures`
4. Choosing which exposure axis (`"y"` or `"z"`) to use as “depth”
5. Returning per-element depths by looking up each element’s section exposure

---

## Function code (reference)

```python
def resolve_depths_for_group(
    *,
    group_name: str,
    exposure_axis: str = "y",
    extra_exposure_y_default: float = 0.0,
    extra_exposure_y_by_id: Dict[int, float] | None = None,
) -> Dict[int, float]:
    ax = _validate_axis(exposure_axis)

    element_ids = list(get_group_element_ids(group_name))
    elem_to_sect = _get_element_to_section_map(element_ids)

    section_props_raw = get_section_properties_cached()
    exposures_df = compute_section_exposures(
        section_props_raw,
        extra_exposure_y_default=extra_exposure_y_default,
        extra_exposure_y_by_id=extra_exposure_y_by_id,
        as_dataframe=True,
    )

    # Normalize index types for reliable membership checks
    try:
        exposures_df.index = exposures_df.index.astype(int)
    except ValueError:
        pass

    depth_col = "exposure_z" if ax == "z" else "exposure_y"

    depth_by_eid: Dict[int, float] = {}
    for eid, sect_id in elem_to_sect.items():
        if sect_id in exposures_df.index:
            depth_by_eid[int(eid)] = float(exposures_df.loc[sect_id, depth_col])

    return depth_by_eid
```

---

## Inputs (parameters)

### Keyword-only arguments (`*`)
The `*` means you must call using keyword arguments.

Valid:
```python
depths = resolve_depths_for_group(group_name="WALL_A", exposure_axis="y")
```

### `group_name: str`
Name of the MIDAS element group whose elements you want depths for.

Example: `"WALL_A"`, `"ROOF_EDGE"`, `"FRAME_01"`

### `exposure_axis: str = "y"`
Which exposure axis to use as the returned “depth”.
- `"y"` → uses `exposure_y`
- `"z"` → uses `exposure_z`

This value is validated by `_validate_axis`.

### `extra_exposure_y_default: float = 0.0`
Default extra Y exposure added to *all* section properties when computing `exposure_y`.

### `extra_exposure_y_by_id: Dict[int, float] | None = None`
Optional per-section overrides for extra Y exposure:
```python
{ section_property_id: extra_y_value }
```

---

## Outputs
Returns a dictionary:

```python
{
  element_id_1: depth_value,
  element_id_2: depth_value,
  ...
}
```

Where `depth_value` is either the section’s `exposure_y` or `exposure_z` depending on `exposure_axis`.

---

## Step-by-step explanation (line by line)

### 1) Validate the axis input
```python
ax = _validate_axis(exposure_axis)
```

- Ensures `exposure_axis` is acceptable (usually `"y"` or `"z"`, possibly case-insensitive).
- Returns the normalized value (e.g., `"y"` or `"z"`).
- If invalid, `_validate_axis` likely raises an error.

Examples:
- input `"Y"` → `ax = "y"`
- input `"z"` → `ax = "z"`
- input `"x"` → error (depending on `_validate_axis` implementation)

---

### 2) Get element IDs for the group
```python
element_ids = list(get_group_element_ids(group_name))
```

- Calls `get_group_element_ids(group_name)` (your project helper)
- Converts the result into a list (so it can be reused and iterated multiple times)

Example:
- If group `"WALL_A"` contains elements `{101, 102, 103}` → `element_ids = [101, 102, 103]`

---

### 3) Map each element to its section property ID
```python
elem_to_sect = _get_element_to_section_map(element_ids)
```

Returns something like:
```python
{
  101: 5001,
  102: 5001,
  103: 5002,
}
```

Meaning:
- element 101 uses section property 5001
- element 102 uses section property 5001
- element 103 uses section property 5002

This is crucial because exposures are computed per **section property**, not per element.

---

### 4) Fetch raw section properties and compute exposures for all sections
```python
section_props_raw = get_section_properties_cached()
exposures_df = compute_section_exposures(
    section_props_raw,
    extra_exposure_y_default=extra_exposure_y_default,
    extra_exposure_y_by_id=extra_exposure_y_by_id,
    as_dataframe=True,
)
```

- `get_section_properties_cached()` retrieves the MIDAS section property rows (cached).
- `compute_section_exposures(...)` computes:
  - `exposure_y = top + bottom + extra_y`
  - `exposure_z = left + right`

Because `as_dataframe=True`, the output is a DataFrame like:

```text
             exposure_y  exposure_z
property_id
5001              3.50       2.00
5002              3.20       2.20
```

---

### 5) Normalize DataFrame index types (avoid mismatched int vs str)
```python
try:
    exposures_df.index = exposures_df.index.astype(int)
except ValueError:
    pass
```

Why this matters:
- Sometimes property IDs are strings like `"5001"` in the DataFrame index.
- But `sect_id` from `_get_element_to_section_map` might be an integer `5001`.
- Membership checks like `if sect_id in exposures_df.index` can fail if types don’t match.

So this block tries to convert the index to integers.
- If conversion fails (e.g., IDs like `"S5001"`), it keeps the original.

---

### 6) Decide which exposure column represents “depth”
```python
depth_col = "exposure_z" if ax == "z" else "exposure_y"
```

- If user requested axis `"z"` → use `"exposure_z"`
- Otherwise (axis `"y"`) → use `"exposure_y"`

Examples:
- `ax="y"` → `depth_col="exposure_y"`
- `ax="z"` → `depth_col="exposure_z"`

---

### 7) Build per-element depth mapping by looking up section exposure
```python
depth_by_eid: Dict[int, float] = {}
for eid, sect_id in elem_to_sect.items():
    if sect_id in exposures_df.index:
        depth_by_eid[int(eid)] = float(exposures_df.loc[sect_id, depth_col])
```

What happens here:
- Iterate over each element and its section property id.
- If the section id exists in the exposures table:
  - Lookup exposure value using `.loc[sect_id, depth_col]`
  - Store it under the element id

Example:
- `elem_to_sect = {101: 5001, 102: 5001, 103: 5002}`
- `depth_col = "exposure_y"`
- `exposures_df.loc[5001, "exposure_y"] = 3.5`
- `exposures_df.loc[5002, "exposure_y"] = 3.2`

Result:
```python
{
  101: 3.5,
  102: 3.5,
  103: 3.2,
}
```

Notes:
- Elements sharing the same section property get the same depth.
- If a section id is missing in `exposures_df`, that element is skipped (no entry).

---

### 8) Return the result
```python
return depth_by_eid
```

---

## Worked example (end-to-end)

Assume:
- Group `"WALL_A"` contains elements: `[101, 102, 103]`
- Element→Section map:
  ```python
  {101: 5001, 102: 5001, 103: 5002}
  ```
- Exposures computed:
  ```text
               exposure_y  exposure_z
  property_id
  5001              3.50       2.00
  5002              3.20       2.20
  ```

### Case A: `exposure_axis="y"`
- `depth_col="exposure_y"`
- Output:
  ```python
  {101: 3.5, 102: 3.5, 103: 3.2}
  ```

### Case B: `exposure_axis="z"`
- `depth_col="exposure_z"`
- Output:
  ```python
  {101: 2.0, 102: 2.0, 103: 2.2}
  ```

---

## Edge cases / behavior notes

### If group is empty
- `element_ids` becomes `[]`
- `elem_to_sect` becomes `{}`
- Loop adds nothing → returns `{}`

### If an element has no section mapping
- It will not appear in `elem_to_sect`
- Therefore it won’t appear in output

### If section id types mismatch
- The index normalization attempts to fix it by converting index to `int`
- If conversion fails, some lookups may not match, and those elements may be skipped

### If exposures DataFrame doesn’t contain a section
- That element is skipped due to:
  ```python
  if sect_id in exposures_df.index:
  ```

---

## Quick summary
- Validate axis (`y` or `z`)
- Resolve group → element IDs
- Resolve element → section property IDs
- Compute section exposures (Y and Z)
- Pick a column (`exposure_y` or `exposure_z`)
- Map each element to its section’s exposure value and return `{eid: depth}`
