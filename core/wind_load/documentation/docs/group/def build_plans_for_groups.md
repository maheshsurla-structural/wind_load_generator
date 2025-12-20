## `build_plans_for_groups(...) -> tuple[list[pd.DataFrame], bool]`

A shared “group loop” utility that builds wind-load (or similar) plans for multiple structural groups.

It centralizes the common workflow:

1. Iterate over `groups`
2. Normalize group name
3. Resolve optional `element_ids` for the group
4. Build *components* (`pd.DataFrame`)
5. Optionally dump components for debugging
6. Build a *plan* (`pd.DataFrame`)
7. Optionally dump the plan for debugging
8. Collect all non-empty plans and return `(plans, any_applied)`

---

### Implementation

```py
def build_plans_for_groups(
    *,
    groups: Iterable[str],
    build_components_for_group: Callable[[str], pd.DataFrame],
    build_plan_for_group: Callable[[str, pd.DataFrame, list[int] | None], pd.DataFrame],
    group_members: Mapping[str, list[int]] | None = None,
    dbg: Any = None,
    label_prefix: str = "",
    dump_components: bool = False,
) -> tuple[list[pd.DataFrame], bool]:
    """
    Common loop:
      - iterate groups
      - build components
      - optionally dump components
      - build plan
      - optionally dump plan
    """
    group_members = group_members or {}

    plans: list[pd.DataFrame] = []
    any_applied = False

    for g in groups:
        group_name = str(g).strip()
        if not group_name:
            continue

        element_ids = group_members.get(group_name) or None

        comp = build_components_for_group(group_name)
        if comp is None or comp.empty:
            continue

        if dump_components and dbg is not None and getattr(dbg, "enabled", False):
            dump_fn = getattr(dbg, "dump_components", None)
            if callable(dump_fn):
                dump_fn(comp, label=f"{label_prefix}COMPONENTS_{group_name}")

        plan = build_plan_for_group(group_name, comp, element_ids)
        if plan is None or plan.empty:
            continue

        if dbg is not None and getattr(dbg, "enabled", False):
            dbg.dump_plan(plan, label=f"{label_prefix}{group_name}", split_per_case=True)

        plans.append(plan)
        any_applied = True

    return plans, any_applied
```

---

## Parameters

- `groups: Iterable[str]`
  - Names (or name-like values) of groups to process.

- `build_components_for_group: Callable[[str], pd.DataFrame]`
  - Callback that takes a `group_name` and returns a **components DataFrame**.
  - “Components” typically means intermediate calculation results used to build the final plan.
  - If it returns `None` or an empty DataFrame, that group is skipped.

- `build_plan_for_group: Callable[[str, pd.DataFrame, list[int] | None], pd.DataFrame]`
  - Callback that takes:
    - `group_name`
    - `comp` (components DataFrame)
    - `element_ids` (optional list of member element IDs)
  - Returns a **plan DataFrame** (the final per-group plan).
  - If it returns `None` or an empty DataFrame, that group is skipped.

- `group_members: Mapping[str, list[int]] | None = None`
  - Optional mapping `{group_name: [element_ids...]}`.
  - If not provided, treated as `{}`.
  - If a group is missing from the mapping or has an empty list, `element_ids` becomes `None`.

- `dbg: Any = None`
  - Optional debug sink object (duck-typed).
  - Expected (if enabled):
    - `dbg.enabled: bool`
    - optional `dbg.dump_components(df, label=...)`
    - `dbg.dump_plan(df, label=..., split_per_case=True)`

- `label_prefix: str = ""`
  - Prepended to debug labels for both components and plans.

- `dump_components: bool = False`
  - If `True`, components dumping is attempted (only if `dbg` is enabled and supports `dump_components`).

---

## Return value

Returns a tuple:

1. `plans: list[pd.DataFrame]`
   - One plan DataFrame per processed group (only non-empty plans).

2. `any_applied: bool`
   - `True` if at least one plan was produced (i.e., at least one group generated a non-empty plan).
   - `False` otherwise.

---

## Step-by-step behavior

### 1) Default `group_members` to an empty mapping

```py
group_members = group_members or {}
```

- If `group_members` is `None`, use `{}`.
- Makes later lookups safe without extra checks.

---

### 2) Prepare outputs

```py
plans: list[pd.DataFrame] = []
any_applied = False
```

- `plans` will accumulate each group’s plan.
- `any_applied` tracks whether at least one group produced a plan.

---

### 3) Iterate each group

```py
for g in groups:
    group_name = str(g).strip()
    if not group_name:
        continue
```

- Converts each item `g` to a string and trims whitespace.
- Skips empty/blank names.

Examples:

- `" PIER "` → `"PIER"`
- `""` or `"   "` → skipped

---

### 4) Resolve optional member element IDs

```py
element_ids = group_members.get(group_name) or None
```

- Looks up element IDs for this group.
- If the mapping returns `[]` (empty) or `None`, it becomes `None`.

Why `or None`?
- Many downstream functions treat `None` as “no constraint provided”, while `[]` can mean “constraint provided but empty”.

---

### 5) Build components DataFrame

```py
comp = build_components_for_group(group_name)
if comp is None or comp.empty:
    continue
```

- Calls the provided callback.
- Skips the group if it returns:
  - `None`, or
  - an empty DataFrame (`comp.empty == True`)

---

### 6) Optionally dump components

```py
if dump_components and dbg is not None and getattr(dbg, "enabled", False):
    dump_fn = getattr(dbg, "dump_components", None)
    if callable(dump_fn):
        dump_fn(comp, label=f"{label_prefix}COMPONENTS_{group_name}")
```

This logic is deliberately defensive (“duck typing”):

- Only runs if:
  - `dump_components` is `True`
  - `dbg` exists
  - `dbg.enabled` is truthy

Then:
- It looks for `dbg.dump_components`.
- Only calls it if it’s callable.

Label format:
- `"{label_prefix}COMPONENTS_{group_name}"`

Example:
- `label_prefix="WIND_"`, `group_name="PIER"`
  - label becomes `"WIND_COMPONENTS_PIER"`

---

### 7) Build plan DataFrame

```py
plan = build_plan_for_group(group_name, comp, element_ids)
if plan is None or plan.empty:
    continue
```

- Calls the provided plan-builder callback with:
  - group name
  - components
  - optional element IDs
- Skips group if no plan is produced.

---

### 8) Optionally dump plan

```py
if dbg is not None and getattr(dbg, "enabled", False):
    dbg.dump_plan(plan, label=f"{label_prefix}{group_name}", split_per_case=True)
```

- If debug is enabled, calls `dbg.dump_plan(...)`.
- Label format: `"{label_prefix}{group_name}"`

Example:
- `label_prefix="WIND_"`, `group_name="PIER"`
  - label becomes `"WIND_PIER"`

`split_per_case=True` typically means:
- the dump method may split the plan into separate artifacts per load case (depends on your `dbg` implementation).

---

### 9) Collect results and mark applied

```py
plans.append(plan)
any_applied = True
```

- Adds the plan for this group to the output list.
- Marks that at least one plan exists.

---

### 10) Return

```py
return plans, any_applied
```

- `plans` contains only successful group plans.
- `any_applied` signals whether anything was produced.

---

## Example usage (conceptual)

```py
groups = ["PIER", "GIRDER"]

def build_components_for_group(name: str) -> pd.DataFrame:
    # produce intermediate table for this group
    return pd.DataFrame({"x": [1, 2], "group": [name, name]})

def build_plan_for_group(name: str, comp: pd.DataFrame, element_ids: list[int] | None) -> pd.DataFrame:
    # produce final plan (e.g., loads to apply)
    return pd.DataFrame({"group": [name], "n": [len(comp)], "member_filter": [element_ids is not None]})

plans, any_applied = build_plans_for_groups(
    groups=groups,
    build_components_for_group=build_components_for_group,
    build_plan_for_group=build_plan_for_group,
    group_members={"PIER": [10, 11, 12]},  # GIRDER omitted -> element_ids=None
    dbg=None,
    label_prefix="WIND_",
    dump_components=False,
)
```

Expected:
- `plans` is a list with two DataFrames (one per group), assuming neither is empty.
- `any_applied == True`

---

## Notes / gotchas

- `groups` can be any iterable (list, tuple, generator). If it’s a generator, it will be consumed once.
- `lru_cache` behavior is not involved here; caching happens in the callbacks if needed.
- Debug dumping is intentionally optional and “duck-typed” to keep this utility generic.
