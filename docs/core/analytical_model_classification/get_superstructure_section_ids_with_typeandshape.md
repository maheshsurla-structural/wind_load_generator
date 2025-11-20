# get_superstructure_section_ids_with_typeandshape – Design Notes

File: core/analytical_model_classification/get_superstructure_section_ids_with_typeandshape.py  
Purpose: Identify section IDs that clearly belong to the bridge superstructure using only reliable MIDAS metadata.

---

## 1. High-Level Overview

This function queries `/db/SECT` via `Section.get_all()` and returns a list of section IDs that are classified as superstructure.

The classification is intentionally:

- Metadata-driven (based only on `SECTTYPE` and `SHAPE`)
- Deterministic (no heuristics)
- Independent of any user-defined naming conventions
- Conservative (only includes sections that are clearly superstructure)

---

## 2. Data Model & Assumptions

### 2.1 Source of Data

`Section.get_all()` returns a dictionary mapping section ID strings to their metadata. Example:

```json
    {
        "1": {"SECTTYPE": "PSC", "SHAPE": "PSCH", "SECT_NAME": "G1"},
        "2": {"SECTTYPE": "TAPERED", "SHAPE": "CPCI", "SECT_NAME": "BOX1"}
    }
```

### 2.2 Keys We Care About

#### SECTTYPE
Examples:
- `PSC`
- `COMPOSITE`
- `TAPERED`

#### SHAPE

Common TAPERED shape codes include:

- `1CEL`, `2CEL`, `3CEL`, `NCEL`, `NCE2`
- `PSCM`, `PSCI`, `PSCH`, `PSCT`, `PSCB`
- `VALU`, `CMPW`, `CP_B`, `CP_T`
- `CSGB`, `CSGI`, `CSGT`
- `CPCI`, `CPCT`, `CP_G`
- `STLB`, `STLI`

#### SECT_NAME
Displayed only for debugging. Not used in logic.

### 2.3 Robustness Assumptions

Normalization used in the function:

    sect_type = (value.get("SECTTYPE") or "").upper()
    shape_type = (value.get("SHAPE") or "").upper()

---

## 3. Classification Rules

### Rule 1 — PSC and COMPOSITE

    if sect_type in {"PSC", "COMPOSITE"}:
        selected_ids.append(key)

PSC and COMPOSITE sections are always superstructure.

---

### Rule 2 — TAPERED Sections With Approved Shapes

    if sect_type == "TAPERED" and shape_type in TAPERED_SHAPES:
        selected_ids.append(key)

Approved shape list:

    {
        "1CEL", "2CEL", "3CEL", "NCEL", "NCE2",
        "PSCM", "PSCI", "PSCH", "PSCT", "PSCB",
        "VALU", "CMPW", "CP_B", "CP_T",
        "CSGB", "CSGI", "CSGT",
        "CPCI", "CPCT", "CP_G",
        "STLB", "STLI"
    }

---

## Other Section Types

Any other `SECTTYPE` (STEEL, RC, DBUSER, etc.) is excluded unless rules are added later.

---

## 4. Debug Logging

The function prints:

1. Total sections in `/db/SECT`
2. First 5 sample entries
3. Final list of selected IDs

---

## 5. Control Flow & Structure

- Early `continue` statements simplify logic  
- No name-based rules  
- Uses deterministic metadata  
- Simple top → debug → classify → summary → return sequence  

---

## 6. Why SECT_NAME Is Ignored

- Unreliable  
- Arbitrary naming  
- Can mislead classification  
- Metadata is more trustworthy  

---

## 7. Future Extensions

- Add STEEL girder logic  
- Add DBUSER shape detection  
- Move shapes to external config  
- Replace prints with logger  
- Add unit tests  

---

## 8. Summary

This function:

- Loads MIDAS metadata  
- Normalizes `SECTTYPE` and `SHAPE`  
- Applies strict PSC/COMPOSITE/TAPERED rules  
- Returns superstructure section IDs  
- Avoids naming heuristics  

A deterministic, maintainable, and metadata-driven classifier.
