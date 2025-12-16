# `apply_beam_load_plan_to_midas` — Detailed Notes (Full Explanation)

## Purpose
This function takes a **beam-load plan** (a pandas DataFrame) and **writes it into MIDAS** via `/db/bmld` using a **safe per-element merge strategy**.

Key design goals:
- **Don’t overwrite other loads by accident**: it reads existing `/db/bmld` once, merges loads per element, then writes back.
- **Stable, valid IDs**: assigns new `BeamLoadItem.ID` per element using the “next available id”.
- **Optional “replace existing for these load cases”**: can remove existing items for the plan’s load cases before merging.
- **Optional aggregation of duplicate rows**: can sum line loads for identical keys before writing.
- **Batching**: splits writes into multiple PUT requests so that **total ITEMS per PUT** stays under `max_items_per_put`, while **never splitting a single element across PUTs**.

---

## Function code (reference)

```python
def apply_beam_load_plan_to_midas(
    plan_df: pd.DataFrame,
    *,
    max_items_per_put: int = 5000,
    debug: DebugSink | None = None,
    debug_label: str = "ALL_WIND",
    replace_existing_for_plan_load_cases: bool = True,
    aggregate_duplicates: bool = True,
    resource: Any = BeamLoadResource,   # dependency injection hook
) -> pd.DataFrame:
    """
    Apply a beam-load plan to MIDAS (/db/bmld) using safe merge-per-element writes.

    Adds per-PUT terminal progress like:
      PUT #1 | elements=.. | NEW=.. (cum ../..) | TOTAL ITEMS=.. | limit=..

    Parameters
    ----------
    plan_df : pd.DataFrame
        Required cols: element_id, line_load, load_case, load_direction, load_group
        Optional: eccentricity
    max_items_per_put : int
        Upper bound on total ITEM records in a single PUT request.
    replace_existing_for_plan_load_cases : bool
        If True, remove existing items whose LCNAME is in the plan's load cases.
    aggregate_duplicates : bool
        If True, combines duplicate rows by summing line_load for identical
        (element_id, load_case, load_direction, load_group, eccentricity).

    Returns
    -------
    pd.DataFrame
        The normalized/aggregated DataFrame that was applied.
    """
    if plan_df is None or plan_df.empty:
        logger.info("apply_beam_load_plan_to_midas: plan_df empty; nothing to send.")
        return plan_df

    max_items_per_put = max(int(max_items_per_put), 1)
    df = _normalize_plan_df(plan_df, aggregate_duplicates=aggregate_duplicates)

    if debug and debug.enabled:
        debug.dump_plan(df, label=debug_label, split_per_case=True)

    # -----------------------------
    # 1) Read existing /db/bmld once
    # -----------------------------
    raw_existing = resource.get_raw() or {}

    existing_items_by_eid: Dict[int, List[Dict[str, Any]]] = {}
    for eid_str, elem_block in raw_existing.items():
        try:
            eid = int(eid_str)
        except (TypeError, ValueError):
            continue
        existing_items_by_eid[eid] = list(((elem_block or {}).get("ITEMS", []) or []))

    # -----------------------------
    # 2) Per-element next-id map once
    # -----------------------------
    next_id_by_eid = _next_id_by_element_from_raw(raw_existing)

    def alloc_id(eid: int) -> int:
        nxt = next_id_by_eid.get(eid, 1)
        next_id_by_eid[eid] = nxt + 1
        return nxt

    plan_cases = set(df["load_case"].astype(str).str.strip())

    # -----------------------------
    # 3) Build NEW items (store grouped by element)
    # -----------------------------
    new_by_eid: Dict[int, List[BeamLoadItem]] = defaultdict(list)

    for lcname, lc_df in df.groupby("load_case", sort=False):
        lcname = str(lcname).strip()
        if not lcname:
            continue

        for row in lc_df.itertuples(index=False):
            eid = int(getattr(row, "element_id"))
            q = float(getattr(row, "line_load"))
            if abs(q) < EPS:
                continue

            direction = str(getattr(row, "load_direction"))
            ldgr = str(getattr(row, "load_group"))

            ecc = float(getattr(row, "eccentricity", 0.0))
            use_ecc = abs(ecc) > EPS

            new_by_eid[eid].append(
                BeamLoadItem(
                    ID=alloc_id(eid),
                    LCNAME=lcname,
                    GROUP_NAME=ldgr,
                    CMD="BEAM",
                    TYPE="UNILOAD",
                    DIRECTION=direction,
                    USE_PROJECTION=False,
                    USE_ECCEN=use_ecc,
                    D=[0, 1, 0, 0],
                    P=[q, q, 0, 0],
                    ECCEN_TYPE=1,
                    ECCEN_DIR="GZ",
                    I_END=ecc,
                    J_END=ecc,
                )
            )

    if not new_by_eid:
        logger.info("apply_beam_load_plan_to_midas: all loads ~0; nothing to send.")
        return df

    touched_eids = sorted(new_by_eid.keys())
    total_new_rows = sum(len(v) for v in new_by_eid.values())

    # -----------------------------
    # 4) Merge per element ONCE (optional safe replace)
    # -----------------------------
    merged_items_by_eid: Dict[int, List[Dict[str, Any]]] = {}
    merged_size_by_eid: Dict[int, int] = {}

    for eid in touched_eids:
        existing = existing_items_by_eid.get(eid, [])

        if replace_existing_for_plan_load_cases and plan_cases:
            existing = [
                it for it in existing
                if str(it.get("LCNAME", "")).strip() not in plan_cases
            ]

        merged = list(existing)
        merged.extend(it.to_dict() for it in new_by_eid[eid])

        merged_items_by_eid[eid] = merged
        merged_size_by_eid[eid] = len(merged)

    # -----------------------------
    # 5) PUT in batches: sum(ITEMS) <= max_items_per_put
    #    Never split an element across PUTs.
    # -----------------------------
    sent_new = 0
    req = 0
    idx = 0

    while idx < len(touched_eids):
        batch: List[int] = []
        batch_items = 0

        while idx < len(touched_eids):
            eid = touched_eids[idx]
            elem_items = merged_size_by_eid[eid]

            # If single element exceeds limit, still send it alone
            if not batch and elem_items > max_items_per_put:
                batch = [eid]
                batch_items = elem_items
                idx += 1
                break

            # If adding would exceed limit, stop here
            if batch and (batch_items + elem_items > max_items_per_put):
                break

            batch.append(eid)
            batch_items += elem_items
            idx += 1

        assign = {str(eid): {"ITEMS": merged_items_by_eid[eid]} for eid in batch}

        req += 1
        new_count = sum(len(new_by_eid[eid]) for eid in batch)
        sent_preview = sent_new + new_count

        # ✅ Terminal progress line per PUT
        print(
            f"[apply_beam_load_plan_to_midas] PUT #{req} | "
            f"elements={len(batch)} | "
            f"NEW={new_count} (cum {sent_preview}/{total_new_rows}) | "
            f"TOTAL ITEMS={batch_items} | "
            f"limit={max_items_per_put}",
            flush=True,
        )

        if debug and debug.enabled:
            batch_specs: List[Tuple[int, BeamLoadItem]] = []
            for eid in batch:
                batch_specs.extend((eid, it) for it in new_by_eid[eid])
            debug.dump_chunk_specs(
                batch_specs,
                label=debug_label,
                chunk_index=req,
                reason=f"element-batched items<= {max_items_per_put}",
            )

        resource.put_raw({"Assign": assign})
        sent_new += new_count

    logger.info(
        "apply_beam_load_plan_to_midas done. Sent %s new items across %s requests.",
        sent_new,
        req,
    )
    return df
```

---

## Inputs (parameters)

### `plan_df: pd.DataFrame`
A plan table describing what loads should be applied.

Required columns:
- `element_id` (element number)
- `line_load` (k/ft)
- `load_case` (string label → becomes `LCNAME`)
- `load_direction` (string)
- `load_group` (string → becomes `GROUP_NAME`)

Optional:
- `eccentricity` (float)

### `max_items_per_put: int = 5000`
This is a **batch size limiter**:
- A single PUT sends a set of elements, each with an `ITEMS` list.
- The function ensures:  
  `sum(len(ITEMS) for each element in PUT) <= max_items_per_put`  
  (except one edge case: if a single element alone exceeds the limit, it is still sent alone.)

### `debug: DebugSink | None` + `debug_label`
If debug is enabled, it dumps:
- the normalized plan (optionally split per case),
- and per-PUT chunk specs.

### `replace_existing_for_plan_load_cases: bool = True`
If `True`, for any element you touch, it will **remove existing load items** whose `LCNAME` matches any load case present in the plan, before merging in the new ones.

This prevents duplicates like:
- existing WIND+X items
- plus new WIND+X items
resulting in double application.

### `aggregate_duplicates: bool = True`
Passed into `_normalize_plan_df`. If enabled, it sums `line_load` for identical:
- `(element_id, load_case, load_direction, load_group, eccentricity)`

### `resource: Any = BeamLoadResource`
Dependency injection hook:
- Must provide `get_raw()` and `put_raw(...)`
- Defaults to `BeamLoadResource` used to access `/db/bmld`

This is useful for:
- testing (inject a fake resource),
- or swapping API clients.

---

## Output
Returns the **normalized (and possibly aggregated)** DataFrame `df` that was actually used to generate new MIDAS items.

Important: this does **not** return MIDAS responses; it returns the “applied plan”.

---

## Step-by-step explanation (algorithm walkthrough)

### 0) Early exit on empty plan
```python
if plan_df is None or plan_df.empty:
    ... return plan_df
```
If there’s nothing to apply, it returns immediately.

---

### 1) Sanitize inputs + normalize the plan DataFrame
```python
max_items_per_put = max(int(max_items_per_put), 1)
df = _normalize_plan_df(plan_df, aggregate_duplicates=aggregate_duplicates)
```

- Ensures `max_items_per_put` is at least 1.
- Calls `_normalize_plan_df` to:
  - validate required columns,
  - clean strings,
  - coerce numeric columns,
  - drop invalid rows,
  - optionally aggregate duplicates,
  - stable sort.

---

### 2) Optional debug dump
```python
if debug and debug.enabled:
    debug.dump_plan(df, label=debug_label, split_per_case=True)
```
If debugging, it records the plan.

---

### 3) Read existing `/db/bmld` once (important for safe merge)
```python
raw_existing = resource.get_raw() or {}
```

This gets the current beam load database content (raw dict).

Then it builds:
```python
existing_items_by_eid[eid] = elem_block["ITEMS"]
```

So later you can do:  
**merged = existing + new**  
instead of accidentally overwriting.

---

### 4) Compute the next available load item ID per element
```python
next_id_by_eid = _next_id_by_element_from_raw(raw_existing)
```

`alloc_id(eid)` then:
- reads the current next id (default 1),
- increments it,
- returns the allocated id.

This ensures each new `BeamLoadItem` has a unique `ID` within its element’s `ITEMS`.

---

### 5) Determine which load cases are present in the plan
```python
plan_cases = set(df["load_case"].astype(str).str.strip())
```

Used later for safe replacement:
- remove existing items where `LCNAME` in `plan_cases`.

---

### 6) Build NEW `BeamLoadItem`s grouped by element (`new_by_eid`)
```python
new_by_eid: Dict[int, List[BeamLoadItem]] = defaultdict(list)
```

Then for each load case group:
```python
for lcname, lc_df in df.groupby("load_case", sort=False):
```

- `sort=False` keeps original order of cases (as they appear in `df`).

Then for each row:
- reads element id, line load, direction, load group, eccentricity,
- skips near-zero loads (`abs(q) < EPS`),
- creates a `BeamLoadItem(...)` and appends it to `new_by_eid[eid]`.

#### What `BeamLoadItem(...)` is doing
Each row becomes a MIDAS beam load record with fields like:
- `ID`: allocated per element
- `LCNAME`: load case name
- `GROUP_NAME`: load group name
- `TYPE="UNILOAD"`: uniform line load
- `DIRECTION`: direction string
- `P=[q, q, 0, 0]`: sets uniform load (start/end equal to q)
- Eccentricity fields:
  - `USE_ECCEN` is True only if `abs(ecc) > EPS`
  - `I_END` and `J_END` set to ecc

---

### 7) If everything got skipped (all ~0), return
```python
if not new_by_eid:
    ... return df
```
This can happen if the plan exists but every `line_load` is essentially zero.

---

### 8) Merge: existing + new (and optionally replace by load case)
For each touched element:
- start from existing items,
- optionally remove items whose `LCNAME` is in plan cases,
- append the new items.

```python
if replace_existing_for_plan_load_cases and plan_cases:
    existing = [it for it in existing if it["LCNAME"] not in plan_cases]
merged = existing + new_items
```

This is the **core safety mechanism**:
- if you’re applying “WIND+X” loads, it can cleanly replace old WIND+X items while keeping other load cases intact.

---

### 9) Batch PUT logic (limit total ITEMS per request)
Goal:
- send elements in batches such that:
  - `sum(merged_size_by_eid[eid] for eid in batch) <= max_items_per_put`
- **never split a single element across PUTs**:
  - each element is atomic: its entire `ITEMS` list is sent together.

Special edge case:
- If one element alone has more items than the limit,
  it still sends that element alone (otherwise it would never send).

It builds:
```python
assign = {
  "101": {"ITEMS": [...]},
  "102": {"ITEMS": [...]},
}
resource.put_raw({"Assign": assign})
```

---

### 10) Terminal progress line per PUT
For each request, it prints something like:
```text
[apply_beam_load_plan_to_midas] PUT #2 | elements=15 | NEW=40 (cum 80/120) | TOTAL ITEMS=4980 | limit=5000
```

Meaning:
- PUT request number
- how many elements are included
- how many new items were added in this PUT
- cumulative new items sent / total new items
- total merged items sent (existing+new) across those elements
- the configured batch limit

---

### 11) Optional debug chunk dump (per PUT)
If debug is enabled, it gathers the exact `(eid, BeamLoadItem)` pairs sent as “new” in that batch and dumps them.

---

### 12) Perform the PUT and update counters
```python
resource.put_raw({"Assign": assign})
sent_new += new_count
```

Then loop continues until all touched elements are sent.

---

### 13) Final log + return normalized plan
At the end it logs totals and returns the normalized/aggregated DataFrame `df`.

---

## Worked example (conceptual)

### Input plan_df (before normalization)
```text
element_id  line_load  load_case  load_direction  load_group  eccentricity
101         0.05       WIND+X     GY              WIND+X      0.0
101         0.02       WIND+X     GY              WIND+X      0.0   # duplicate key
102         0.10       WIND+X     GY              WIND+X      0.25
```

If `aggregate_duplicates=True`, the two rows for element 101 are combined:
- element 101: 0.05 + 0.02 = 0.07

So applied `df` becomes:
```text
element_id  line_load  load_case  load_direction  load_group  eccentricity
101         0.07       WIND+X     GY              WIND+X      0.0
102         0.10       WIND+X     GY              WIND+X      0.25
```

Now assume existing `/db/bmld` already has items for:
- element 101: WIND+X (old) and DEAD (other)
- element 102: DEAD only

If `replace_existing_for_plan_load_cases=True`:
- old WIND+X items are removed
- DEAD items remain
- new WIND+X items are appended with new IDs

Finally it batches and PUTs the merged per-element blocks.

---

## Important behavior notes / pitfalls

### “Replace existing” happens only for elements you touched
Only elements that get new items (`touched_eids`) are merged and written.
Elements not in the plan are not modified.

### Near-zero loads are skipped
If `abs(q) < EPS`, no BeamLoadItem is created for that row.

### Batch limit counts TOTAL merged items, not just new
`max_items_per_put` is applied to the **total** merged size (existing + new) in each element block.

### Single element can exceed the limit
If one element has more items than `max_items_per_put`, the function still sends it alone.

### Uses `print()` for progress
Progress is printed to terminal/console per request (useful for long operations).

---

## Quick summary
- Normalize plan (and optionally aggregate duplicates)
- Read existing `/db/bmld` once
- Compute next IDs per element
- Build BeamLoadItem objects for plan rows
- Merge with existing items per element (optionally replace by plan load cases)
- PUT updates in batches that respect an ITEMS limit and never split elements
- Return the normalized/aggregated DataFrame that was applied
