# StructuralGroup Code Deep Dive

This file defines `StructuralGroup`, a resource wrapper around a MIDAS "group" data model.  
It manages CRUD-style operations, ID assignment, and conversion of element lists.  
It inherits from `MapResource`, which likely provides HTTP GET/PUT behavior for a key-value map living at `/db/GRUP`.

We'll walk through each part of the code: constants, helpers, lookup methods, create/update logic, bulk operations, and element access utilities.

---

## Class Overview

```python
class StructuralGroup(MapResource):
    READ_KEY = "GRUP"
    PATH = "/db/GRUP"
```

- `StructuralGroup` subclasses `MapResource`. That means:
  - It inherits things like `get_all()` and `set_all()`.
  - You can think of `MapResource` as "a thing that lives at some path and is addressable by a map/dict of IDs → entries".

- `READ_KEY = "GRUP"`  
  Likely used by `MapResource` when extracting the relevant map from a larger payload.

- `PATH = "/db/GRUP"`  
  The REST-like path to PUT/GET the entire map of groups.

So `StructuralGroup` represents a dictionary-like resource at `/db/GRUP`:

```python
{
    "1": {"NAME": "BeamGroupA", "E_LIST": [101, 102, 103]},
    "2": {"NAME": "Columns", "E_LIST": "201 202 203"}
}
```

Keys like `"1"`, `"2"` are group IDs (string digits). Each entry has:
- `"NAME"`: human-readable group name
- `"E_LIST"`: associated element IDs, either as list[int] or a string of IDs

---

## Internal Helper: `_normalize_e_list`

```python
@staticmethod
def _normalize_e_list(e_list: Union[str, Iterable[int], Iterable[str]]) -> Union[str, list[int]]:
    if isinstance(e_list, str):
        return e_list.strip()
    try:
        normalized = [int(x) for x in e_list]
    except TypeError:
        raise ValueError("E_LIST must be a string or an iterable of IDs.")
    except ValueError:
        raise ValueError("E_LIST iterable must contain only integers (or strings of ints).")
    return normalized
```

### Purpose
Normalizes the input `E_LIST` before sending to MIDAS.

- If a string is given, return it unchanged (trimmed).
- If an iterable is given, convert all items to `int`.
- Raises descriptive errors for invalid types or contents.

---

## Lookup Methods

```python
@classmethod
def get_by_name(cls, name: str) -> Optional[Dict[str, Any]]:
    all_groups = cls.get_all()
    for entry in all_groups.values():
        if entry.get("NAME") == name:
            return entry
    return None
```

```python
@classmethod
def get_id_by_name(cls, name: str) -> Optional[str]:
    all_groups = cls.get_all()
    for k, entry in all_groups.items():
        if entry.get("NAME") == name:
            return k
    return None
```

These look up groups either by name or ID.  
Return `None` if not found.

---

## Key Management: `next_key`

```python
@classmethod
def next_key(cls) -> str:
    all_groups = cls.get_all()
    if not all_groups:
        return "1"
    nums = [int(k) for k in all_groups.keys() if str(k).isdigit()]
    return str(max(nums) + 1) if nums else "1"
```

Generates the next available numeric ID as a string.

---

## Create / Update

### `create`

```python
@classmethod
def create(cls, name: str, e_list: Union[str, Iterable[int], Iterable[str]]) -> Dict[str, Any]:
    if not name or not name.strip():
        raise ValueError("Structural group name is required.")
    e_list_norm = cls._normalize_e_list(e_list)
    if (isinstance(e_list_norm, list) and not e_list_norm) or (isinstance(e_list_norm, str) and not e_list_norm):
        raise ValueError("Element list is empty.")
    if cls.get_id_by_name(name) is not None:
        raise RuntimeError(f"Structural group name '{name}' already exists.")
    key = cls.next_key()
    entry = {"NAME": name, "E_LIST": e_list_norm}
    return cls.set_all({str(key): entry})
```

Validates input, checks for duplicate name, assigns the next ID, and sends payload.

---

### `upsert`

```python
@classmethod
def upsert(cls, name: str, e_list: Union[str, Iterable[int], Iterable[str]]) -> Dict[str, Any]:
    if not name or not name.strip():
        raise ValueError("Structural group name is required.")
    e_list_norm = cls._normalize_e_list(e_list)
    if (isinstance(e_list_norm, list) and not e_list_norm) or (isinstance(e_list_norm, str) and not e_list_norm):
        raise ValueError("Element list is empty.")
    existing_id = cls.get_id_by_name(name)
    key = existing_id if existing_id is not None else cls.next_key()
    entry = {"NAME": name, "E_LIST": e_list_norm}
    return cls.set_all({str(key): entry})
```

Same as `create`, but updates existing groups if found.  
Acts like an "update or insert" (idempotent per name).

---

## Overridden `set_all`

```python
@classmethod
def set_all(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return super().set_all(payload)
    except Exception as exc:
        raise RuntimeError(
            f"PUT {cls.PATH} failed for payload={payload!r}: {exc}"
        )
```

Adds better debugging output when the PUT operation fails.

---

## Bulk Upsert

Handles multiple groups in one request.

```python
@classmethod
def bulk_upsert(cls, entries: Iterable[Tuple[str, Iterable[int] | str]]) -> Dict[str, Any]:
    existing = cls.get_all()
    name_to_id = {}
    max_id = 0
    for k, v in existing.items():
        sk = str(k)
        if sk.isdigit():
            max_id = max(max_id, int(sk))
        n = (v.get("NAME") or "").strip()
        if n:
            name_to_id[n] = sk

    assign = {}
    next_id = max_id + 1

    for name, e_list in entries:
        if not name or not name.strip():
            raise ValueError("Structural group name is required.")
        e_list_norm = cls._normalize_e_list(e_list)
        if (isinstance(e_list_norm, list) and not e_list_norm) or (isinstance(e_list_norm, str) and not e_list_norm):
            raise ValueError(f"Element list is empty for group '{name}'.")
        name = name.strip()
        key = name_to_id.get(name)
        if key is None:
            key = str(next_id)
            next_id += 1
        assign[key] = {"NAME": name, "E_LIST": e_list_norm}

    if not assign:
        return {}
    return cls.set_all(assign)
```

### Highlights
- Reads existing data once.
- Reuses IDs for existing names.
- Creates new IDs for new names.
- Performs a single `set_all()` network call.

---

## Element Access Utilities

### `_to_int_list`

```python
@staticmethod
def _to_int_list(e_list: Any) -> list[int]:
    if not e_list:
        return []
    if isinstance(e_list, str):
        return [int(x) for x in e_list.split() if x.strip().isdigit()]
    return [int(x) for x in e_list]
```

Converts mixed representations of `E_LIST` (list or string) into a clean `list[int]`.

---

### `get_elements_by_name`

```python
@classmethod
def get_elements_by_name(cls, name: str) -> list[int]:
    entry = cls.get_by_name(name)
    return cls._to_int_list(entry.get("E_LIST")) if entry else []
```

Returns list of element IDs by group name.

---

### `get_elements_by_id`

```python
@classmethod
def get_elements_by_id(cls, group_id: Union[str, int]) -> list[int]:
    entry = cls.get_all().get(str(group_id))
    return cls._to_int_list(entry.get("E_LIST")) if entry else []
```

Returns list of element IDs by numeric ID.

---

### `name_to_elements`

```python
@classmethod
def name_to_elements(cls) -> Dict[str, list[int]]:
    out = {}
    for entry in cls.get_all().values():
        name = (entry.get("NAME") or "").strip()
        if name:
            out[name] = cls._to_int_list(entry.get("E_LIST"))
    return out
```

Creates mapping of `{ name → [elements] }` for all groups.

---

### `id_to_elements`

```python
@classmethod
def id_to_elements(cls) -> Dict[str, list[int]]:
    out = {}
    for k, entry in cls.get_all().items():
        out[str(k)] = cls._to_int_list(entry.get("E_LIST"))
    return out
```

Creates mapping of `{ id → [elements] }` for all groups.

---

## Summary

- `StructuralGroup` manages structural element groups as a key-value resource.
- Provides validated `create`, `upsert`, and `bulk_upsert` for writing.
- Provides convenience getters for name, id, and element access.
- Ensures type safety and consistent formatting of `E_LIST`.
- Offers debugging-friendly errors for failed PUT operations.

This makes it easy to read, write, and manage group data in MIDAS with consistent and predictable behavior.
