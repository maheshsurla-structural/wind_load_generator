## `get_structural_group_element_ids(structural_group_name: str) -> list[int]`

Return the list of element IDs (`list[int]`) belonging to a structural group identified by its **group name**.

This function is optimized with **two layers of caching**:

1. `@lru_cache(maxsize=512)` caches results **per input `structural_group_name`**, so repeated calls with the same argument return instantly.
2. `_get_all_structural_groups_cached()` is expected to cache the `/db/GRUP` snapshot, so the process performs **at most one GET** to `/db/GRUP` per Python process.

---

### Implementation

```py
@lru_cache(maxsize=512)
def get_structural_group_element_ids(structural_group_name: str) -> list[int]:
    """
    Cached lookup: return element IDs for the given structural group name.

    Uses the in-memory /db/GRUP snapshot from _get_all_structural_groups_cached(),
    so we only ever do ONE GET /db/GRUP per Python process.
    """
    target_group_name = str(structural_group_name or "").strip()
    if not target_group_name:
        return []

    structural_group_records = _get_all_structural_groups_cached()

    # Find the group record with matching NAME
    for structural_group_record in structural_group_records.values():
        record_group_name = str(structural_group_record.get("NAME") or "").strip()
        if record_group_name != target_group_name:
            continue

        raw_element_list = structural_group_record.get("E_LIST")
        if not raw_element_list:
            return []

        # Normalize to list[int] (same logic as StructuralGroup._to_int_list)
        if isinstance(raw_element_list, str):
            # Example: "1 2 3"
            return [int(token) for token in raw_element_list.split() if token.strip().isdigit()]

        element_ids: list[int] = []
        for item in raw_element_list:
            try:
                element_ids.append(int(item))
            except (TypeError, ValueError):
                pass

        return element_ids

    return []
```

---

## What `@lru_cache(maxsize=512)` does here

`functools.lru_cache` memoizes function results so the function does not recompute for the same inputs.

- **Keyed by arguments**: the raw `structural_group_name` value passed to the function.
- **Up to 512 distinct names** are cached.
- When the cache is full and a new name is requested, the **least recently used** entry is evicted.

### Practical effect

```py
get_structural_group_element_ids("GIRDER")  # computes + caches result
get_structural_group_element_ids("GIRDER")  # returns instantly from cache
```

> Note: the cache key is based on the argument value *before* normalization.  
> Calls like `"GIRDER"` and `"  GIRDER  "` are different cache keys, even though both normalize to the same `target_group_name`.  
> This documents current behavior as written.

---

## Line-by-line behavior

### 1) Normalize the input name

```py
target_group_name = str(structural_group_name or "").strip()
if not target_group_name:
    return []
```

- Converts `None` → `""`, ensures type is string, trims whitespace.
- Empty input returns `[]` immediately.

Examples:

```py
get_structural_group_element_ids("")       # []
get_structural_group_element_ids(None)     # []
get_structural_group_element_ids(" G1 ")   # treated as "G1" for lookup logic
```

---

### 2) Read cached `/db/GRUP` snapshot

```py
structural_group_records = _get_all_structural_groups_cached()
```

Expected typical shape:

```py
{
  "1": {"NAME": "GIRDER", "E_LIST": "10 11 12", ...},
  "2": {"NAME": "PIER",   "E_LIST": [20, "21", 22], ...},
}
```

This snapshot is expected to be cached in-memory, so repeated calls do not repeatedly call MIDAS.

---

### 3) Find the matching group record by `NAME`

```py
for structural_group_record in structural_group_records.values():
    record_group_name = str(structural_group_record.get("NAME") or "").strip()
    if record_group_name != target_group_name:
        continue
```

- Iterates every group record in the snapshot.
- Reads `"NAME"` defensively:
  - missing `"NAME"` becomes `""`
  - `.strip()` removes stray spaces
- Uses an **exact match** (`!=`) to find the target record.
  - Matching is case-sensitive.

---

### 4) Extract `"E_LIST"` and validate

```py
raw_element_list = structural_group_record.get("E_LIST")
if not raw_element_list:
    return []
```

- Retrieves the element list.
- If it’s missing/empty (`None`, `""`, `[]`, etc.), returns `[]`.

---

### 5) Normalize `"E_LIST"` to `list[int]`

This function supports two common MIDAS formats:

#### A) `"E_LIST"` is a whitespace-separated string

```py
if isinstance(raw_element_list, str):
    return [int(token) for token in raw_element_list.split() if token.strip().isdigit()]
```

- Splits on whitespace (e.g., `"1 2 3"` → `["1","2","3"]`)
- Keeps only tokens that are strictly numeric (`isdigit()`)
- Converts to integers

Examples:

```py
"E_LIST": "10 11 12"      -> [10, 11, 12]
"E_LIST": "10  x  12"     -> [10, 12]
"E_LIST": "10  11  12 "   -> [10, 11, 12]
```

> Note: `isdigit()` rejects negatives (e.g., `"-10"`) and tokens like `"10,"`.
> For element IDs, that’s typically desirable.

#### B) `"E_LIST"` is a list/sequence

```py
element_ids: list[int] = []
for item in raw_element_list:
    try:
        element_ids.append(int(item))
    except (TypeError, ValueError):
        pass

return element_ids
```

- Iterates through the sequence.
- Attempts to coerce each item to `int`.
- Skips items that can’t be converted.

Examples:

```py
"E_LIST": [10, "11", None, "x", 12]  -> [10, 11, 12]
"E_LIST": ["001", 2, 3.0]            -> [1, 2, 3]
```

---

### 6) If the group name is not found

```py
return []
```

If no record’s `"NAME"` matches the target, return `[]`.

Examples:

```py
get_structural_group_element_ids("NOT_A_REAL_GROUP")  # []
```

---

## End-to-end example

Assume `_get_all_structural_groups_cached()` returns:

```py
{
  "1": {"NAME": "GIRDER", "E_LIST": "10 11 12"},
  "2": {"NAME": "PIER", "E_LIST": [20, "21", None, "x", 22]},
}
```

Then:

```py
get_structural_group_element_ids("GIRDER")  # [10, 11, 12]
get_structural_group_element_ids("PIER")    # [20, 21, 22]
get_structural_group_element_ids("pier")    # []  (case-sensitive)
```

And repeated calls are served from the `lru_cache` (up to 512 distinct names).
