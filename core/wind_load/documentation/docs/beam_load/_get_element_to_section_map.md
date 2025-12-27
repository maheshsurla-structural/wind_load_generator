# `_get_element_to_section_map()` — detailed explanation (with examples)

## Purpose

This helper builds a mapping:

```python
{element_id: section_id}
```

It takes a list/sequence of element IDs, looks up each element in the cached MIDAS **/db/ELEM** snapshot (via `_get_all_elements_cached()`), extracts the element’s **section/property id** from the `"SECT"` field, and returns a clean `Dict[int, int]`.

This mapping is later used by exposure/pressure conversion logic to answer questions like:

- “For element `101`, which section properties row should I use to get exposure depth?”

---

## The function (as implemented)

```python
def _get_element_to_section_map(element_ids: Sequence[int]) -> Dict[int, int]:
    """Map element_id -> section_id using cached /db/elem snapshot."""
    out: Dict[int, int] = {}
    all_elem = _get_all_elements_cached()

    for eid in element_ids:
        try:
            eid_i = int(eid)
        except (TypeError, ValueError):
            continue

        edata = all_elem.get(str(eid_i))
        if not edata:
            continue

        sect_id = edata.get("SECT")
        if sect_id is None:
            continue

        try:
            out[eid_i] = int(sect_id)
        except (TypeError, ValueError):
            continue

    return out
```

---

## What `_get_all_elements_cached()` typically contains

Most MIDAS DB wrappers return element records keyed by **string element ids**, for example:

```python
all_elem = {
  "101": {"SECT": 12, "TYPE": "BEAM", "MATL": 1},
  "102": {"SECT": 12, "TYPE": "BEAM", "MATL": 1},
  "200": {"SECT": 7,  "TYPE": "BEAM", "MATL": 2},
}
```

That’s why the implementation uses `str(eid_i)` when doing lookups.

---

## Step-by-step (what each part does)

### 1) Prepare output dict

```python
out: Dict[int, int] = {}
```

Creates an empty dictionary that will be filled with `{element_id: section_id}` pairs.

---

### 2) Get cached `/db/ELEM` snapshot once

```python
all_elem = _get_all_elements_cached()
```

Fetches the cached result of reading `/db/ELEM` so the function can do many lookups without repeatedly calling MIDAS.

---

### 3) Loop over requested element IDs

```python
for eid in element_ids:
```

Processes each element ID one by one.

---

### 4) Normalize element id to an integer (`eid_i`)

```python
try:
    eid_i = int(eid)
except (TypeError, ValueError):
    continue
```

Why this exists:

- `element_ids` might contain values like `"101"`, `101`, `np.int64(101)`, etc.
- Converting to `int` makes the rest of the function consistent.
- If conversion fails (e.g., `"A1"`, `None`), the element is skipped (robust behavior).

**Examples:**

```python
int("101")      # 101
int(101.0)      # 101
int(None)       # TypeError -> skipped
int("A1")       # ValueError -> skipped
```

---

### 5) Look up element record in cached dict

```python
edata = all_elem.get(str(eid_i))
if not edata:
    continue
```

Why `str(eid_i)`?

- MIDAS snapshots often store keys as strings: `"101"`, not `101`.

So:
- `eid_i = 101`
- `str(eid_i) = "101"`
- `all_elem.get("101")` returns the element record if present.

If the element record is missing or empty → skip.

---

### 6) Extract the section id (`"SECT"`)

```python
sect_id = edata.get("SECT")
if sect_id is None:
    continue
```

- `"SECT"` is expected to be the element’s section/property id.
- If `"SECT"` is missing or explicitly `None`, skip the element (no valid section link).

---

### 7) Convert section id to int and store in output mapping

```python
try:
    out[eid_i] = int(sect_id)
except (TypeError, ValueError):
    continue
```

Why this exists:

- `sect_id` might be `"12"` (string) or `12` (int) — both valid.
- It might also be invalid (e.g., `""`, `"N/A"`, `None`) — conversion would fail.
- If conversion fails, skip that element rather than crashing.

This guarantees the output mapping is:

- keys: `int` element ids
- values: `int` section ids

---

### 8) Return the mapping

```python
return out
```

At the end you get a clean `{element_id: section_id}` mapping for all valid inputs.

---

## Examples

### Example 1 — Normal case

**Input:**
```python
element_ids = [101, 102, 200]
```

**Cached `/db/ELEM` snapshot:**
```python
all_elem = {
  "101": {"SECT": 12},
  "102": {"SECT": 12},
  "200": {"SECT": 7},
}
```

**Output:**
```python
{101: 12, 102: 12, 200: 7}
```

---

### Example 2 — Element id not found in `/db/ELEM`

**Input:**
```python
element_ids = [101, 999]
```

**Cached data:**
```python
all_elem = {"101": {"SECT": 12}}
```

- `101` → found → included
- `999` → missing → `edata=None` → skipped

**Output:**
```python
{101: 12}
```

---

### Example 3 — `"SECT"` missing for an element

**Input:**
```python
element_ids = [101, 102]
```

**Cached data:**
```python
all_elem = {
  "101": {"SECT": 12},
  "102": {"TYPE": "BEAM"}  # no SECT field
}
```

- `101` → included
- `102` → `sect_id=None` → skipped

**Output:**
```python
{101: 12}
```

---

### Example 4 — `"SECT"` not convertible to int

**Input:**
```python
element_ids = [101, 102]
```

**Cached data:**
```python
all_elem = {
  "101": {"SECT": "12"},
  "102": {"SECT": "N/A"},
}
```

- `101` → `"12"` converts to `12` → included
- `102` → `"N/A"` raises `ValueError` → skipped

**Output:**
```python
{101: 12}
```

---

## Notes / gotchas

- **String keys are common** in MIDAS DB dictionaries (`"101"` vs `101`), so using `str(eid_i)` is important for correct lookups.
- This function **silently skips** invalid/missing records rather than raising errors. That improves robustness but can hide data issues; logging skipped IDs may be helpful when debugging.
- If your MIDAS element record uses a different key than `"SECT"` for section id, you would need to change the field name in:
  ```python
  sect_id = edata.get("SECT")
  ```
