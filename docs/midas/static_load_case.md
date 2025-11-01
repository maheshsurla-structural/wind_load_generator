# 📘 `midas/resources/static_load_case.py`

### 🧭 High-Level Overview
This module defines the **`StaticLoadCase`** resource class, which manages **static load cases** (`/db/STLD`) in the MIDAS API.

It provides:
- Mappings of all supported static load types (`STATIC_LOAD_TYPES`)
- Utility methods for querying, validating, and normalizing load case data
- High-level CRUD operations (`create`, `upsert`, `bulk_upsert`)
- Automatic ID assignment and deduplication by name

---

## 📚 Table of Contents
1. [Background: MIDAS Static Load Cases](#-background)
2. [`STATIC_LOAD_TYPES`](#-static_load_types)
3. [`StaticLoadCase` Class](#-staticloadcase-class)
   - [Overview](#overview)
   - [Lookup Methods](#lookup-methods)
   - [Validation Helpers](#validation-helpers)
   - [Create and Upsert Methods](#create-and-upsert-methods)
   - [Bulk Operations](#bulk-operations)
4. [Example Usage](#-example-usage)
5. [Summary](#-summary)

---

## 🌍 Background

In MIDAS, **static load cases** define load categories like *Dead Load*, *Live Load*, *Temperature*, etc.  
They are stored in the `/db/STLD` resource.

**Example GET response:**
```json
{
  "STLD": {
    "1": { "NAME": "DL", "TYPE": "D", "DESC": "DeadLoads" },
    "2": { "NAME": "LL", "TYPE": "L" }
  }
}
```

**Example PUT request:**
```json
{
  "Assign": {
    "1": { "NAME": "DL", "TYPE": "D" },
    "2": { "NAME": "LL", "TYPE": "L" }
  }
}
```

The `StaticLoadCase` class provides a Pythonic interface for creating, updating, or retrieving these cases.

---

## ⚙️ `STATIC_LOAD_TYPES`

A global dictionary that maps **MIDAS static load codes** to **human-readable labels**.

**Example entries:**
```python
STATIC_LOAD_TYPES = {
    "D": "Dead Load",
    "L": "Live Load",
    "W": "Wind Load on Structure",
    "S": "Snow Load",
    "E": "Earthquake",
    ...
}
```

This lookup supports type validation and normalization across the API.

---

## 🧱 `StaticLoadCase` Class

### 🪶 Overview
```python
class StaticLoadCase(MapResource):
    READ_KEY = "STLD"
    PATH = "/db/STLD"
```

Represents a single static load case entry within the MIDAS model.  
This resource is fully analogous to `StructuralGroup`, `Node`, or `Element`.

It inherits from `MapResource`, which provides the base `get_all`, `set_all`, and HTTP I/O logic.

---

### 🔍 Lookup Methods

#### `get_id_by_name(name: str) -> Optional[str]`
Finds the ID of a static load case by its name.

```python
StaticLoadCase.get_id_by_name("DL")  # → "1"
```

If the case does not exist, returns `None`.

---

#### `next_key() -> str`
Computes the **next available numeric key** for creating a new load case.

```python
StaticLoadCase.next_key()  # → "3"
```

---

### ✅ Validation Helpers

#### `_normalize_type(load_type: str) -> str`
Normalizes a given load type string (like `"Dead Load"` or `"D"`) into a valid MIDAS code.

- Accepts full labels (`"Dead Load"`)
- Accepts shorthand codes (`"D"`)
- Case-insensitive matching
- Raises `ValueError` for unknown types

**Example:**
```python
StaticLoadCase._normalize_type("dead load")  # → "D"
StaticLoadCase._normalize_type("E")          # → "E"
StaticLoadCase._normalize_type("Earthquake") # → "E"
```

---

### 🏗️ Create and Upsert Methods

#### `create(name: str, load_type: str, desc: str = "") -> Dict[str, Any]`
Creates a **new** static load case.  
Fails if a case with the same name already exists.

```python
StaticLoadCase.create("DL", "Dead Load", "Main Dead Load")
```

Raises:
- `ValueError` if `name` is missing
- `RuntimeError` if a duplicate name exists

---

#### `upsert(name: str, load_type: str, desc: str = "") -> Dict[str, Any]`
Creates or **updates** a load case by name.

If the name exists → updates its type/description.  
If not → creates a new entry with the next available ID.

```python
StaticLoadCase.upsert("LL", "Live Load", "Updated live load definition")
```

---

### 📦 Bulk Operations

#### `bulk_upsert(cases: Iterable[Tuple[str, str, str | None]]) -> Dict[str, Any]`
Adds or updates multiple static load cases in one API call.

**Input format:**
```python
[
    ("DL", "Dead Load", "Dead loads"),
    ("LL", "Live Load", None),
    ("WIND_X", "Wind Load on Structure", "Wind in X direction")
]
```

**Behavior:**
- Normalizes type codes automatically  
- Assigns IDs sequentially if new  
- Reuses existing IDs if names match  
- Returns the full PUT payload structure  

**Example Output:**
```python
{
  "Assign": {
    "1": {"NAME": "DL", "TYPE": "D", "DESC": "Dead loads"},
    "2": {"NAME": "LL", "TYPE": "L"},
    "3": {"NAME": "WIND_X", "TYPE": "W", "DESC": "Wind in X direction"}
  }
}
```

---

## 💡 Example Usage

```python
# Create a new static load case
StaticLoadCase.create("DL", "Dead Load", "Primary Dead Load")

# Upsert (create or update)
StaticLoadCase.upsert("LL", "Live Load")

# Bulk create or update
StaticLoadCase.bulk_upsert([
    ("DL", "Dead Load", "Updated Dead Load"),
    ("LL", "Live Load", None),
    ("WIND_X", "Wind Load on Structure", "Wind load in X direction"),
])
```

---

## 📊 Summary

| Method | Description |
|--------|--------------|
| `get_id_by_name()` | Returns ID of load case by name |
| `next_key()` | Computes next available ID |
| `_normalize_type()` | Validates and converts human label to MIDAS code |
| `create()` | Creates a new static load case |
| `upsert()` | Creates or updates by name |
| `bulk_upsert()` | Creates or updates many cases in one PUT |

---

✅ **In short:**  
The `StaticLoadCase` class gives a high-level, reliable way to manage `/db/STLD` load cases in MIDAS,  
handling normalization, deduplication, and ID assignment automatically.
