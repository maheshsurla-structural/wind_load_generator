# ⚙️ `unit_manager/converter.py`

**Purpose:** Provides fast, dependency-free helper functions to convert between **length** and **force** units used in structural or wind load calculations.  
**Design Principle:** Every conversion is normalized through SI base units (`meters`, `newtons`) before converting to the target unit.  
This ensures consistency and accuracy across different measurement systems (Imperial ↔ Metric).

---

## 📖 Overview

This module defines dictionaries for supported units and two conversion functions:

| Function | Description |
|:----------|:-------------|
| `convert_length()` | Converts between any supported length units. |
| `convert_force()` | Converts between any supported force units. |

All lookups are **case-insensitive** and raise `ValueError` if an unsupported unit is provided.

---

## 📁 Module Data

### `_LENGTH_TO_M`

| Unit | Description | Conversion Factor to meters |
|:------|:-------------|:-----------------------------|
| `MM` | millimeter | `0.001` |
| `CM` | centimeter | `0.01` |
| `M`  | meter (base) | `1.0` |
| `IN` | inch | `0.0254` |
| `FT` | foot | `0.3048` |

---

### `_FORCE_TO_N`

| Unit | Description | Conversion Factor to newtons |
|:------|:-------------|:------------------------------|
| `N` | newton (base) | `1.0` |
| `KN` | kilonewton | `1_000.0` |
| `LBF` | pound-force | `4.4482216152605` |
| `KIPS` | kip (1000 lbf) | `4_448.2216152605` |
| `KGF` | kilogram-force | `9.80665` |
| `TONF` | metric ton-force | `9_806.65` |

---

## 🧩 Function Reference

### `convert_length(value: float, from_sym: str, to_sym: str) -> float`

**Description:**  
Converts a numerical length value from one unit to another using `_LENGTH_TO_M`.

**Parameters:**

| Name | Type | Description |
|:------|:------|:-------------|
| `value` | `float` | Numeric length value to convert. |
| `from_sym` | `str` | Source unit (e.g., `"FT"`, `"IN"`, `"M"`). |
| `to_sym` | `str` | Target unit (e.g., `"M"`, `"CM"`, `"FT"`). |

**Returns:**  
`float` — Converted length value in the target unit.

**Raises:**  
`ValueError` — If an unknown unit symbol is passed.

**Example Usage:**
```python
>>> convert_length(12.0, "FT", "M")
3.6576

>>> convert_length(10, "in", "cm")
25.4
```

---

### `convert_force(value: float, from_sym: str, to_sym: str) -> float`

**Description:**  
Converts a force value between any supported units using `_FORCE_TO_N`.

**Parameters:**

| Name | Type | Description |
|:------|:------|:-------------|
| `value` | `float` | Numeric force value to convert. |
| `from_sym` | `str` | Source unit (e.g., `"KIPS"`, `"LBF"`, `"N"`). |
| `to_sym` | `str` | Target unit (e.g., `"KN"`, `"KIPS"`, `"LBF"`). |

**Returns:**  
`float` — Converted force value in the target unit.

**Raises:**  
`ValueError` — If an unknown unit symbol is passed.

**Example Usage:**
```python
>>> convert_force(5.0, "kips", "kN")
22.2411080763025

>>> convert_force(100, "LBF", "N")
444.82216152605
```

---

## 🧠 Implementation Details

Each conversion follows the same principle:

```python
value_in_base = value * from_factor
value_in_target = value_in_base / to_factor
```

- For **length**, the base unit is **meters**.  
- For **force**, the base unit is **newtons**.  
- The input units are normalized with `.upper()` to ensure case-insensitivity.  
- `KeyError` exceptions are caught and re-raised as clear `ValueError` messages.

---

## ⚠️ Error Handling

When an invalid or unsupported unit is supplied:

```python
>>> convert_length(1, "YD", "M")
ValueError: Unknown length unit: YD
```

and for forces:

```python
>>> convert_force(1, "PSI", "N")
ValueError: Unknown force unit: PSI
```

---

## 📏 Precision Notes

- Constants are **industry-standard** (exact definitions for inch, foot, lbf, etc.).  
- All results are standard Python `float` values.  
- Floating-point rounding applies (IEEE-754).  
- For formatted output, use:
  ```python
  print(f"{convert_length(1, 'FT', 'M'):.3f} m")
  ```
- In tests, compare using `math.isclose()` with a small tolerance.

---

## 🧪 Example Unit Tests (pytest)

```python
import math
from unit_manager.converter import convert_length, convert_force

def test_convert_length_ft_to_m():
    assert math.isclose(convert_length(1, "FT", "M"), 0.3048, rel_tol=1e-12)

def test_convert_length_in_to_cm():
    assert math.isclose(convert_length(10, "IN", "CM"), 25.4, rel_tol=1e-12)

def test_convert_force_kips_to_kn():
    assert math.isclose(convert_force(1, "KIPS", "kN"), 4.4482216152605, rel_tol=1e-12)

def test_convert_force_lbf_to_n():
    assert math.isclose(convert_force(100, "LBF", "N"), 444.82216152605, rel_tol=1e-12)
```

---

## 🧩 Design Considerations

| Design Goal | Explanation |
|:--------------|:-------------|
| **Lightweight** | Pure Python, zero dependencies. |
| **Consistent** | All conversions pass through SI base units. |
| **Safe** | Raises explicit `ValueError` for unknown symbols. |
| **Fast** | Simple dictionary lookups, O(1) performance. |
| **Extendable** | Easily add more units or aliases. |

---

## 💡 Example Integration

```python
from unit_manager.converter import convert_length, convert_force

beam_length = convert_length(25, "FT", "M")
applied_load = convert_force(3.5, "KIPS", "kN")

print(f"Beam Length: {beam_length:.3f} m")
print(f"Applied Load: {applied_load:.2f} kN")
```

**Output:**
```
Beam Length: 7.620 m
Applied Load: 15.57 kN
```

---

## 🧾 Summary

| Function | Base Unit | Description |
|:-----------|:-----------|:-------------|
| `convert_length()` | meter (m) | Converts between distance units |
| `convert_force()` | newton (N) | Converts between force units |

---

## 🗝️ TL;DR

> A simple, reliable, and precise unit conversion module for **length** and **force**.  
> Ensures cross-system consistency across all components of the Wind Load Generator.

---
