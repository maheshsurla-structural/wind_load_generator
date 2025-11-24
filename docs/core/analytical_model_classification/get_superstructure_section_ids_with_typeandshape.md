# get_superstructure_section_ids_with_typeandshape – Design Notes

File: `core/analytical_model_classification/get_superstructure_section_ids_with_typeandshape.py`  
Purpose: Identify section IDs that clearly belong to the bridge superstructure using only reliable MIDAS metadata, using a reusable dataclass-based classifier.

---

## 1. High-Level Overview

This module provides:

- A dataclass: `SuperstructureSectionClassifier`
- A wrapper function: `get_superstructure_section_ids_with_typeandshape()`

The classifier examines section metadata from `/db/SECT` and returns a list of section IDs classified as superstructure.

The classification remains:

- Metadata-driven (based only on `SECTTYPE` and `SHAPE`)
- Deterministic (no heuristics or naming rules)
- Independent of user naming conventions
- Conservative (includes only clearly superstructure sections)
- Reusable (optional preloaded section data to avoid repeated MIDAS API calls)

---

## 2. Data Model & Assumptions

### 2.1 Source of Data

Section data originates from:

```
Section.get_all()
```

This returns a dictionary mapping section ID strings to metadata, for example:

```json
{
    "1": {"SECTTYPE": "PSC",     "SHAPE": "PSCH", "SECT_NAME": "G1"},
    "2": {"SECTTYPE": "TAPERED", "SHAPE": "CPCI", "SECT_NAME": "BOX1"}
}
```

### 2.2 Optional Preloaded Data

The classifier works in two modes:

- Lazy-load mode  
  The classifier calls `Section.get_all()` internally when `sections=None`.

- Preloaded mode (recommended)  
  Pass already-fetched metadata to avoid repeated MIDAS API calls:

```
sections = Section.get_all()
classifier = SuperstructureSectionClassifier(sections=sections)
```

### 2.3 Keys Used for Classification

#### SECTTYPE

Examples:

- PSC
- COMPOSITE
- TAPERED

#### SHAPE

Used only when `SECTTYPE == "TAPERED"`.

Supported tapered shapes include:

- 1CEL, 2CEL, 3CEL, NCEL, NCE2
- PSCM, PSCI, PSCH, PSCT, PSCB
- VALU, CMPW, CP_B, CP_T
- CSGB, CSGI, CSGT
- CPCI, CPCT, CP_G
- STLB, STLI

#### SECT_NAME

Displayed only during debugging.  
Never used in classification logic.

### 2.4 Robustness Assumptions

Normalization logic:

```
sect_type = (value.get("SECTTYPE") or "").upper()
shape_type = (value.get("SHAPE") or "").upper()
```

This safely handles missing keys, `None` values, and mixed-case inputs.

---

## 3. Classification Rules

### Rule 1 — PSC and COMPOSITE

```
if sect_type in {"PSC", "COMPOSITE"}:
    include
```

### Rule 2 — TAPERED Sections With Approved Shapes

```
if sect_type == "TAPERED" and shape_type in TAPERED_SHAPES:
    include
```

Approved tapered shape codes:

```
1CEL, 2CEL, 3CEL, NCEL, NCE2,
PSCM, PSCI, PSCH, PSCT, PSCB,
VALU, CMPW, CP_B, CP_T,
CSGB, CSGI, CSGT,
CPCI, CPCT, CP_G,
STLB, STLI
```

---

## Other Section Types

Any other `SECTTYPE` (STEEL, RC, DBUSER, etc.) is excluded unless rules are added later.

---

## 4. Dataclass Behavior

### 4.1 Input Validation (`__post_init__`)

The classifier validates:

- Rejects the mistake of passing the `Section` class itself
- Ensures `sections` is a dictionary
- Validates keys (string or integer)
- Validates values (metadata dictionaries)

### 4.2 Lazy Loading

If `sections` is `None`, the classifier loads section metadata once:

```
self.sections = Section.get_all() or {}
```

---

## 5. Debug Logging

Controlled by:

- `debug=True`
- `printer` callback (defaults to `print`)

Debug mode prints:

1. A preview of the first few section records (`preview_limit`)
2. A summary count of selected IDs

Example preview line:

```
SAMPLE 12: SECTTYPE='TAPERED', SHAPE='CPCI', SECT_NAME='BOX GIRDER'
```

---

## 6. Control Flow & Structure

- `_load_sections()` fetches or returns cached data  
- `_debug_preview()` prints a small metadata preview  
- `iter_superstructure_section_ids()` contains core classification logic  
- `get_superstructure_section_ids()` wraps the generator and logs summary  
- The wrapper function retains backward compatibility:

```
get_superstructure_section_ids_with_typeandshape(...)
```

---

## 7. Why `SECT_NAME` Is Ignored

- Unreliable
- User-controlled
- Varies across models
- Not deterministic

Metadata (`SECTTYPE` and `SHAPE`) is more consistent and trustworthy.

---

## 8. Future Extensions

- Add STEEL girder logic
- Add DBUSER shape classification
- Externalize shape lists into config
- Replace debug prints with structured logging
- Add unit tests with synthetic section metadata

---

## 9. Summary

The classifier:

- Loads or reuses MIDAS section metadata
- Normalizes `SECTTYPE` and `SHAPE`
- Applies strict PSC / COMPOSITE / TAPERED rules
- Ignores unreliable naming
- Supports debug mode
- Avoids repeated MIDAS API calls
- Provides a simple wrapper for backward compatibility

A deterministic, maintainable, and metadata-driven superstructure classifier.
