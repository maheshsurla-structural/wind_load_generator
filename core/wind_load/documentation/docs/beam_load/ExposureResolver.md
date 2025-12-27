# `ExposureResolver` — Detailed Notes (with examples)

## Purpose

`ExposureResolver` is a small **caching helper** that produces **exposure depth maps** for a set of element IDs.

It is designed to make pressure → line-load conversion efficient by avoiding repeated work:

- **Reads section properties once** (`get_section_properties_cached()`)
- **Computes the exposures table once** (`compute_section_exposures(...)`)
- For any requested element set, it quickly builds:

```py
depth_by_eid: Dict[int, float]  # {element_id: exposure_depth}
```

This is useful for functions like `build_pressure_plan_from_components(...)` which need `depth_by_eid` repeatedly for different load cases / components.

---

## Class definition (reference)

```py
@dataclass
class ExposureResolver:
    """
    Resolves exposure depth maps for element IDs with caching.

    - Reads section properties once.
    - Computes exposures DF once.
    - Builds depth_by_eid quickly for any element list.
    """
    extra_exposure_y_default: float = 0.0
    extra_exposure_y_by_id: Optional[Dict[int, float]] = None

    _exposures_df: Optional[pd.DataFrame] = None

    def exposures_df(self) -> pd.DataFrame:
        if self._exposures_df is None:
            raw = get_section_properties_cached()
            self._exposures_df = compute_section_exposures(
                raw,
                extra_exposure_y_default=self.extra_exposure_y_default,
                extra_exposure_y_by_id=self.extra_exposure_y_by_id,
                as_dataframe=True,
            )
        return self._exposures_df

    def depth_map(self, *, element_ids: Sequence[int], axis: str) -> Dict[int, float]:
        ax = _validate_axis(axis)
        element_ids = [int(e) for e in element_ids or []]
        if not element_ids:
            return {}

        elem_to_sect = _get_element_to_section_map(element_ids)
        if not elem_to_sect:
            return {}

        df = self.exposures_df()
        if df is None or df.empty:
            return {}

        col = "exposure_z" if ax == "z" else "exposure_y"

        out: Dict[int, float] = {}
        for eid, sid in elem_to_sect.items():
            if sid in df.index:
                out[eid] = float(df.loc[sid, col])
        return out

    def depth_map_for_group(self, *, group_name: str, axis: str) -> Dict[int, float]:
        eids = get_structural_group_element_ids(group_name)
        return self.depth_map(element_ids=eids, axis=axis)
```

---

## What problem it solves (conceptually)

When converting wind pressure to beam line load, you typically do:

\[
\text{line\_load}_{eid} = \text{pressure} \times \text{exposure\_depth}_{eid}
\]

But **exposure depth depends on the section assigned to each element**:

1. element `eid` → has section id `sid` (from `/db/ELEM["SECT"]`)
2. section id `sid` → has exposures `exposure_y` / `exposure_z` (computed from section offsets)
3. therefore you want:

```py
{eid: exposure_depth_for_axis}
```

This class caches step (2) so you don’t recompute exposures repeatedly.

---

## Fields (dataclass attributes)

### Public configuration

- `extra_exposure_y_default: float = 0.0`  
  Default “extra Y exposure” that will be added to every section when computing `exposure_y`.

- `extra_exposure_y_by_id: Optional[Dict[int, float]] = None`  
  Optional per-section overrides:
  ```py
  {section_id: extra_y}
  ```

### Internal cache

- `_exposures_df: Optional[pd.DataFrame] = None`  
  Cache slot that holds the computed exposures DataFrame once created.

---

## Method: `exposures_df() -> pd.DataFrame`

### What it does

Returns a DataFrame like:

```text
             exposure_y  exposure_z
property_id
12                 3.25         2.00
7                  4.10         1.80
...
```

It computes it **only once** and then reuses it.

### How it works (step-by-step)

```py
if self._exposures_df is None:
    raw = get_section_properties_cached()
    self._exposures_df = compute_section_exposures(...)
return self._exposures_df
```

- On the **first call**, `_exposures_df` is `None`:
  - fetch section properties (`raw`)
  - compute exposures DataFrame
  - store it into `_exposures_df`

- On subsequent calls, it returns the cached DataFrame instantly.

### Example

```py
resolver = ExposureResolver(extra_exposure_y_default=0.25)

df1 = resolver.exposures_df()  # computes and caches
df2 = resolver.exposures_df()  # returns cached df (no recompute)
```

---

## Method: `depth_map(element_ids, axis) -> Dict[int, float]`

### Purpose

Build a mapping:

```py
{element_id: exposure_depth_for_axis}
```

Where axis is `"y"` or `"z"`.

### Step-by-step behavior

#### 1) Validate + normalize axis

```py
ax = _validate_axis(axis)
```

- returns `"y"` or `"z"` in lowercase
- raises ValueError if invalid input (like `"x"`)

#### 2) Normalize element IDs

```py
element_ids = [int(e) for e in element_ids or []]
if not element_ids:
    return {}
```

- converts each element id to `int`
- if list becomes empty, return `{}`

#### 3) Build `{eid: sid}` mapping

```py
elem_to_sect = _get_element_to_section_map(element_ids)
if not elem_to_sect:
    return {}
```

This uses cached `/db/ELEM` data and returns:

```py
{101: 12, 102: 12, 200: 7}
```

If no valid mapping, return `{}`.

#### 4) Get exposures DataFrame (cached)

```py
df = self.exposures_df()
if df is None or df.empty:
    return {}
```

#### 5) Choose exposure column by axis

```py
col = "exposure_z" if ax == "z" else "exposure_y"
```

So:
- axis `"y"` → use `"exposure_y"`
- axis `"z"` → use `"exposure_z"`

#### 6) Build output `{eid: depth}` map

```py
out: Dict[int, float] = {}
for eid, sid in elem_to_sect.items():
    if sid in df.index:
        out[eid] = float(df.loc[sid, col])
return out
```

For each element:
- look up its section id
- if that section exists in exposures df index, fetch exposure depth and store it

---

## Method: `depth_map_for_group(group_name, axis) -> Dict[int, float]`

### Purpose

Convenience wrapper for when you want exposure depths for an entire **structural group**.

```py
eids = get_structural_group_element_ids(group_name)
return self.depth_map(element_ids=eids, axis=axis)
```

- fetches element IDs from the group name
- delegates to `depth_map(...)`

---

# Worked examples (end-to-end)

## Example 1 — Y exposure map for specific elements

Assume:

### `/db/ELEM` mapping (cached)
```py
_get_element_to_section_map([101, 102, 200])  -> {101: 12, 102: 12, 200: 7}
```

### exposures_df (cached)
```text
property_id  exposure_y  exposure_z
12           3.25        2.00
7            4.10        1.80
```

Now:

```py
resolver = ExposureResolver(extra_exposure_y_default=0.25)

depths_y = resolver.depth_map(element_ids=[101, 102, 200], axis="y")
```

Result:

```py
{
  101: 3.25,  # section 12 exposure_y
  102: 3.25,  # section 12 exposure_y
  200: 4.10,  # section 7 exposure_y
}
```

---

## Example 2 — Z exposure map for the same elements

```py
depths_z = resolver.depth_map(element_ids=[101, 102, 200], axis="z")
```

Result:

```py
{
  101: 2.00,  # section 12 exposure_z
  102: 2.00,
  200: 1.80,  # section 7 exposure_z
}
```

---

## Example 3 — Use a structural group

Assume:

```py
get_structural_group_element_ids("GIRDER") -> [101, 102, 200]
```

Call:

```py
depths = resolver.depth_map_for_group(group_name="GIRDER", axis="y")
```

Same as:

```py
resolver.depth_map(element_ids=[101, 102, 200], axis="y")
```

---

## Example 4 — Missing section in exposures table

Assume element 300 maps to section 99:

```py
elem_to_sect = {300: 99}
```

But exposures df does not contain section 99.

Then:

```py
resolver.depth_map(element_ids=[300], axis="y")  # returns {}
```

(or returns `{}` or simply doesn’t include 300), because:

```py
if sid in df.index:
    ...
```

filters it out.

---

## Example 5 — Invalid axis

```py
resolver.depth_map(element_ids=[101], axis="x")
```

Raises:

```text
ValueError: axis must be 'y' or 'z', got 'x'
```

---

# Notes / gotchas

- **Axis must be `"y"` or `"z"`** (validated by `_validate_axis`).
- `element_ids` are force-cast to `int`; if a value cannot be cast, it will raise in the list comprehension.
  - If you want it more defensive, you’d mirror the try/except logic used elsewhere, but current code assumes IDs are int-like.
- Exposures are cached at the instance level:
  - new `ExposureResolver(...)` instance → new cache
  - same instance reused → one exposures computation total
- Overrides apply only to exposure Y (via `compute_section_exposures`), not exposure Z.

---

## Quick summary

- `exposures_df()` computes and caches section exposure table once.
- `depth_map(...)` returns `{eid: exposure_depth}` for a list of element IDs.
- `depth_map_for_group(...)` does the same for a group name by resolving element IDs first.
