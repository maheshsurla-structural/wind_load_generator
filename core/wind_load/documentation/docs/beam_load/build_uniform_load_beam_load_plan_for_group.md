# `build_uniform_load_beam_load_plan_for_group` — Detailed Notes (Full Explanation)

## Purpose
This function builds a **beam-load plan DataFrame** that applies the **same uniform line load** (`line_load`, in k/ft) to **each element** in a group (or in an explicitly provided element list).

Unlike the pressure-based function (pressure × depth), this one already receives the final **line load** directly and assigns it uniformly to all selected elements.

It returns a **pandas DataFrame** with one row per element, including metadata (load case, direction, group, etc.) and an optional **eccentricity** value.

---

## Function code (reference)

```python
def build_uniform_load_beam_load_plan_for_group(
    *,
    group_name: str,
    load_case_name: str,
    line_load: float,
    udl_direction: str,
    load_group_name: str | None = None,
    element_ids: Sequence[int] | None = None,
    eccentricity: float = 0.0,
) -> pd.DataFrame:
    if element_ids is None:
        element_ids = get_group_element_ids(group_name)

    rows: list[dict] = []
    for eid in [int(e) for e in element_ids]:
        rows.append(
            {
                "element_id": eid,
                "line_load": float(line_load),
                "load_case": str(load_case_name),
                "load_direction": str(udl_direction),
                "load_group": str(load_group_name or load_case_name),
                "group_name": str(group_name),
                "eccentricity": float(eccentricity),
            }
        )

    df = pd.DataFrame(rows)
    if not df.empty:
        df.sort_values("element_id", inplace=True)
        df.reset_index(drop=True, inplace=True)
    return df
```

---

## Inputs (parameters)

### Keyword-only arguments (`*`)
The `*` means you must call using keyword arguments.

Valid:
```python
plan = build_uniform_load_beam_load_plan_for_group(
    group_name="WALL_A",
    load_case_name="WIND+X",
    line_load=0.07,
    udl_direction="GY",
)
```

### `group_name: str`
Name of the group whose elements will receive the load (used both for:
- resolving element IDs (if `element_ids` is not passed)
- storing metadata in the DataFrame)

### `load_case_name: str`
Load case label stored in the output DataFrame for each row.

### `line_load: float`
The uniform line load value (typically **k/ft**) to apply to each element.

### `udl_direction: str`
Direction label for the uniform distributed line load (metadata).

### `load_group_name: str | None = None`
Optional “load group” label.
- If provided, used as `load_group`
- If not provided, defaults to `load_case_name`

### `element_ids: Sequence[int] | None = None`
Optional override list of elements.
- If `None`, the function uses `get_group_element_ids(group_name)`
- If provided, the group lookup is skipped and your list is used instead

### `eccentricity: float = 0.0`
Optional eccentricity value to store per row (often used for load offset/positioning depending on your MIDAS beam load model).

---

## Output
A DataFrame with one row per element and columns:

- `element_id` (int)
- `line_load` (float)
- `load_case` (str)
- `load_direction` (str)
- `load_group` (str)
- `group_name` (str)
- `eccentricity` (float)

---

## Step-by-step explanation (line by line)

### 1) Determine which element IDs to use
```python
if element_ids is None:
    element_ids = get_group_element_ids(group_name)
```

- If the caller didn’t provide `element_ids`, the function fetches them from the group name.
- If the caller *did* provide `element_ids`, this block is skipped.

Examples:
- Call without element_ids:
  - `element_ids = get_group_element_ids("WALL_A")`
- Call with element_ids:
  - `element_ids = [101, 102, 103]` (no group lookup)

---

### 2) Initialize list for row dictionaries
```python
rows: list[dict] = []
```

Each element becomes one dict row appended to `rows`.

---

### 3) Loop through element IDs (convert to int)
```python
for eid in [int(e) for e in element_ids]:
```

- Ensures each element id is an `int` (defensive normalization).
- If `element_ids` contains strings like `"101"`, it becomes `101`.

Example:
```python
element_ids = ["101", 102]
[int(e) for e in element_ids]  # -> [101, 102]
```

---

### 4) Append one row per element
```python
rows.append(
    {
        "element_id": eid,
        "line_load": float(line_load),
        "load_case": str(load_case_name),
        "load_direction": str(udl_direction),
        "load_group": str(load_group_name or load_case_name),
        "group_name": str(group_name),
        "eccentricity": float(eccentricity),
    }
)
```

What each field means:

- `"element_id": eid`
  - element id for this row

- `"line_load": float(line_load)`
  - uses the *same* line load for every element
  - cast to float for consistent output type

- `"load_case": str(load_case_name)`
  - cast to string to ensure a consistent type

- `"load_direction": str(udl_direction)`
  - cast to string

- `"load_group": str(load_group_name or load_case_name)`
  - if `load_group_name` is provided (truthy), use it
  - otherwise use `load_case_name`

- `"group_name": str(group_name)`
  - stored for tracking/debugging/filtering

- `"eccentricity": float(eccentricity)`
  - eccentricity stored per row (same for all elements in this plan)

---

### 5) Convert the list of dicts into a DataFrame
```python
df = pd.DataFrame(rows)
```

If `rows` is empty (e.g., group has no elements), `df` will be an empty DataFrame.

---

### 6) Sort and reset index if not empty
```python
if not df.empty:
    df.sort_values("element_id", inplace=True)
    df.reset_index(drop=True, inplace=True)
```

- `sort_values("element_id")` makes the plan deterministic and easier to read/debug.
- `reset_index(drop=True)` renumbers rows from `0..N-1` after sorting.
- `inplace=True` modifies the DataFrame directly.

---

### 7) Return the plan DataFrame
```python
return df
```

---

## Worked examples

### Example A: Use group elements (no `element_ids` passed)
Assume:
- `get_group_element_ids("WALL_A")` returns `[103, 101, 102]`

Call:
```python
plan = build_uniform_load_beam_load_plan_for_group(
    group_name="WALL_A",
    load_case_name="WIND+X",
    line_load=0.05,
    udl_direction="GY",
    eccentricity=0.25,
)
```

Returned DataFrame (after sorting by element_id):
```text
   element_id  line_load load_case load_direction load_group group_name  eccentricity
0         101      0.05   WIND+X            GY     WIND+X     WALL_A          0.25
1         102      0.05   WIND+X            GY     WIND+X     WALL_A          0.25
2         103      0.05   WIND+X            GY     WIND+X     WALL_A          0.25
```

---

### Example B: Provide explicit `element_ids` list (skip group lookup)
Call:
```python
plan = build_uniform_load_beam_load_plan_for_group(
    group_name="WALL_A",
    load_case_name="WIND-Z",
    line_load=-0.02,
    udl_direction="GZ",
    element_ids=[2001, 2002],
    load_group_name="WIND_SERVICE",
)
```

Returned DataFrame:
```text
   element_id  line_load load_case load_direction    load_group group_name  eccentricity
0        2001     -0.02   WIND-Z            GZ   WIND_SERVICE     WALL_A          0.0
1        2002     -0.02   WIND-Z            GZ   WIND_SERVICE     WALL_A          0.0
```

Note:
- `load_group` uses `"WIND_SERVICE"` because `load_group_name` was provided.

---

## Edge cases / behavior notes

### Empty group / empty element list
- If `element_ids` becomes empty, `rows` stays empty → returns empty DataFrame.

### Element IDs as strings
- The loop converts them to int, so `"101"` becomes `101`.
- If a value cannot be converted to int (e.g. `"A1"`), this code will raise a `ValueError` at `int(e)`.

### Eccentricity usage
- This function only *stores* eccentricity in the plan.
- How eccentricity affects the applied load depends on how your “apply plan” logic writes to MIDAS (/db/bmld schema).

---

## Quick summary
- If `element_ids` not provided, fetch them from `group_name`
- Create one plan row per element with the same `line_load`
- Add metadata: load case, direction, load group, group name, eccentricity
- Sort by `element_id` and reset index
- Return the DataFrame
