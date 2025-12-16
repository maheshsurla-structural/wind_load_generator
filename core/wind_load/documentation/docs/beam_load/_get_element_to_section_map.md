# `_get_element_to_section_map()` — detailed explanation (with examples)

## Purpose

This helper builds a mapping:

```python
{element_id: section_id}
```

It takes a list of element IDs, looks up each element in the cached MIDAS **/db/ELEM** data (via `_get_all_elements_cached()`), extracts the element’s **section/property id** from the `"SECT"` field, and returns a clean `Dict[int, int]`.

---

## The function

```python
def _get_element_to_section_map(element_ids: List[int]) -> Dict[int, int]:
    """
    Return {element_id: section_id} for each element in element_ids.
    Uses /db/ELEM via midas.elements.get_all() (cached).
    """
    out: Dict[int, int] = {}
    all_elem_data = _get_all_elements_cached()

    for eid in element_ids:
        edata = all_elem_data.get(str(eid))
        if not edata:
            continue

        sect_id = edata.get("SECT")  # adjust if your key differs
        if sect_id is None:
            continue

        try:
            out[int(eid)] = int(sect_id)
        except (TypeError, ValueError):
            continue

    return out
```

---

## What `_get_all_elements_cached()` typically contains

Many MIDAS DB wrappers return element records keyed by **string element ids**, for example:

```python
all_elem_data = {
  "101": {"SECT": 12, "TYPE": "BEAM", "MATL": 1},
  "102": {"SECT": 12, "TYPE": "BEAM", "MATL": 1},
  "200": {"SECT": 7,  "TYPE": "BEAM", "MATL": 2},
}
```

That’s why the code uses `str(eid)` when doing the lookup.

---

## Step-by-step (what each part does)

### 1) Prepare output dict

```python
out: Dict[int, int] = {}
```

Creates an empty dictionary that will be filled with `{element_id: section_id}` pairs.

---

### 2) Get cached element database snapshot

```python
all_elem_data = _get_all_elements_cached()
```

Fetches the cached result of reading `/db/ELEM` (so the function can do many lookups without repeatedly calling MIDAS).

---

### 3) Loop over the requested element ids

```python
for eid in element_ids:
```

Processes each element one by one.

---

### 4) Look up element data using `str(eid)`

```python
edata = all_elem_data.get(str(eid))
```

- MIDAS element records are often keyed by **strings**, e.g. `"101"`, not `101`.
- So `str(eid)` makes the lookup consistent.

**Example:**
- If `eid = 101`, then `str(eid) == "101"`.
- `all_elem_data.get("101")` returns `{"SECT": 12, ...}`.

---

### 5) Skip if the element record is missing/empty

```python
if not edata:
    continue
```

This handles cases where:
- The element id isn’t present in `/db/ELEM` (invalid id, deleted, not loaded, etc.)
- The record exists but is empty/falsey.

`continue` means “skip this element and move to the next”.

---

### 6) Extract the section id (`"SECT"`)

```python
sect_id = edata.get("SECT")
```

- `"SECT"` is expected to be the section/property id used by that element.
- If your MIDAS export/db uses a different key, you’d adjust it here.

---

### 7) Skip if `"SECT"` is missing

```python
if sect_id is None:
    continue
```

This ensures you only include entries that *actually have* a valid section id value.

---

### 8) Convert both ids to `int` safely and store

```python
try:
    out[int(eid)] = int(sect_id)
except (TypeError, ValueError):
    continue
```

Why this block exists:

- Sometimes `sect_id` may come back as a string `"12"` → valid.
- Sometimes it may come back as something invalid like `""`, `"N/A"`, or a non-numeric type.
- If conversion fails, we skip that element rather than crashing.

This also guarantees the returned dict uses integer keys/values.

---

### 9) Return the mapping

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

**Cached /db/ELEM snapshot:**
```python
all_elem_data = {
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

### Example 2 — Element id not found in /db/ELEM

**Input:**
```python
element_ids = [101, 999]
```

**Cached data:**
```python
all_elem_data = {"101": {"SECT": 12}}
```

- `eid=101` → found → included
- `eid=999` → not found → `edata=None` → skipped

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
all_elem_data = {
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

### Example 4 — `"SECT"` is not convertible to int

**Input:**
```python
element_ids = [101, 102]
```

**Cached data:**
```python
all_elem_data = {
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

- **Key type mismatch is common**: MIDAS DB dictionaries often use string keys for ids. Using `str(eid)` avoids missing lookups.
- This function **silently skips** invalid/missing records rather than raising errors. That’s useful for robustness but can hide data issues; if needed, log skipped ids for debugging.
- The comment `# adjust if your key differs` is important: if your element record uses a different field name than `"SECT"`, update it.
