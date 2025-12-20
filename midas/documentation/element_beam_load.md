# 📘 `midas/resources/element_beam_load.py`

### 🧭 High-Level Overview
This module defines the classes and helpers used to **read**, **create**, and **send beam (frame) loads** to the MIDAS model via `/db/bmld`.  
It abstracts away the nested JSON structure used by MIDAS into clean, Pythonic objects.

---

## 📚 Table of Contents
1. [Background: How MIDAS stores beam loads](#-background)
2. [BeamLoadItem](#-beamloaditem)
3. [BeamLoadResource](#-beamloadresource)
4. [Example: Creating and Sending Loads](#-example-creating-and-sending-loads)
5. [Integration with Wind-Load Workflow](#-integration-with-wind-load-workflow)
6. [Verification Example](#-verification-example)
7. [Summary Table](#-summary)

---

## 🌍 Background

MIDAS stores beam (frame) loads in `/db/bmld` using a nested structure like:

```json
{
  "BMLD": {
    "115": { "ITEMS": [ { ...load1... }, { ...load2... } ] },
    "220": { "ITEMS": [ { ...load3... } ] }
  }
}
```

| Level | Description |
| ------ | ------------ |
| **BMLD** | Root key in the MIDAS database (`/db/bmld`) |
| **115**, **220** | Element IDs |
| **ITEMS** | List of load dictionaries for that element |
| **{...load...}** | Each entry represents a single beam load |

This module abstracts that structure into:
- `BeamLoadItem` → defines a single beam load  
- `BeamLoadResource` → manages reading/writing the `/db/bmld` resource

---

## 🧱 `BeamLoadItem`

### 🎯 Purpose
Represents a **single beam (frame) load** entry applied to one element.  
Provides conversion between a Python object and the exact MIDAS JSON structure.

---

### 💡 Quick Example

```python
from midas.resources.element_beam_load import BeamLoadItem

item = BeamLoadItem(
    ID=1,
    LCNAME="WIND_X",
    DIRECTION="GZ",
    P=[-12.3, -12.3, 0, 0],
)
```

---

### 🧮 Constructor

```python
def __init__(
    *,
    ID,
    LCNAME,
    GROUP_NAME="",
    CMD="BEAM",
    TYPE="UNILOAD",
    DIRECTION="GZ",
    USE_PROJECTION=False,
    USE_ECCEN=False,
    D=(0, 1, 0, 0),
    P=(0, 0, 0, 0),
    ECCEN_TYPE=1,
    ECCEN_DIR="GX",
    I_END=0.0,
    J_END=0.0,
    USE_J_END=None,
    USE_ADDITIONAL=False,
    ADDITIONAL_I_END=0.0,
    ADDITIONAL_J_END=0.0,
    USE_ADDITIONAL_J_END=None,
)
```

---

### 📊 Parameter Groups

| Category | Parameters | Description |
|-----------|-------------|--------------|
| **Identification** | `ID`, `LCNAME`, `GROUP_NAME` | Defines load case and tag |
| **Load Type & Direction** | `CMD`, `TYPE`, `DIRECTION`, `USE_PROJECTION` | Defines type and orientation |
| **Magnitude & Range** | `D`, `P` | Defines normalized distances and magnitudes |
| **Eccentricity (Optional)** | `USE_ECCEN`, `ECCEN_TYPE`, `ECCEN_DIR`, `I_END`, `J_END` | Defines offset parameters |
| **Additional Info** | `USE_ADDITIONAL*`, `ADDITIONAL_I_END`, `ADDITIONAL_J_END` | Extra data (e.g. exposure heights) |

---

### 🔁 `to_dict()`

Converts the object into the exact dictionary format expected by MIDAS:

```python
def to_dict(self) -> Dict[str, Any]:
```

**Example Output:**

```json
{
  "ID": 1,
  "LCNAME": "WIND_X",
  "GROUP_NAME": "Pier 3",
  "CMD": "BEAM",
  "TYPE": "UNILOAD",
  "DIRECTION": "GZ",
  "USE_PROJECTION": false,
  "USE_ECCEN": false,
  "D": [0, 1, 0, 0],
  "P": [-12.3, -12.3, 0, 0],
  "USE_ADDITIONAL": true,
  "ADDITIONAL_I_END": 7.5,
  "ADDITIONAL_J_END": 7.5,
  "USE_ADDITIONAL_J_END": true
}
```

---

### 🔄 `from_dict()`

Inverse of `to_dict()` — parses a raw MIDAS dictionary into a Python object.

```python
@classmethod
def from_dict(cls, data: Dict[str, Any]) -> "BeamLoadItem":
```

---

## 🌐 `BeamLoadResource`

### 🎯 Purpose
Provides a high-level interface for interacting with the `/db/bmld` resource in MIDAS — including reading, writing, and structuring payloads.

---

### ⚙️ Constants

```python
PATH = "/db/bmld"
READ_KEY = "BMLD"
```

---

### 📬 `get_raw()`
Fetches the raw MIDAS `/db/bmld` data.

```python
@classmethod
def get_raw(cls) -> Dict[str, Any]:
```

**Example Output:**
```python
{
    "115": {"ITEMS": [ {...}, {...} ]},
    "220": {"ITEMS": [ {...} ]}
}
```

---

### 📤 `put_raw(assign_payload)`
Sends the payload to MIDAS via a PUT request.

```python
@classmethod
def put_raw(cls, assign_payload: Dict[str, Any]) -> Dict[str, Any]:
```

Payload structure:

```json
{
  "Assign": {
    "115": {"ITEMS":[...]},
    "220": {"ITEMS":[...]}
  }
}
```

---

### 🏗️ `build_assign_from_specs(specs)`

```python
@staticmethod
def build_assign_from_specs(specs: List[Tuple[int, BeamLoadItem]]) -> Dict[str, Any]:
```

Takes a list of `(element_id, BeamLoadItem)` pairs and groups them by element.

**Example Input:**
```python
[
  (115, BeamLoadItem(ID=1, LCNAME="WIND_X")),
  (115, BeamLoadItem(ID=2, LCNAME="WIND_X")),
  (220, BeamLoadItem(ID=1, LCNAME="WIND_X")),
]
```

**Output:**
```python
{
  "Assign": {
    "115": {"ITEMS": [ {...}, {...} ]},
    "220": {"ITEMS": [ {...} ]}
  }
}
```

---

### 🚀 `create_from_specs(specs)`

Creates and immediately sends beam loads to MIDAS.

```python
@classmethod
def create_from_specs(cls, specs: List[Tuple[int, BeamLoadItem]]) -> Dict[str, Any]:
```

```python
specs = [
    (115, BeamLoadItem(ID=1, LCNAME="WIND_X", P=[-12.3, -12.3, 0, 0])),
    (220, BeamLoadItem(ID=1, LCNAME="WIND_X", P=[-12.3, -12.3, 0, 0])),
]
BeamLoadResource.create_from_specs(specs)
```

---

### 📖 `get_all_items()`

Fetches and parses all beam loads currently stored in the model.

```python
@classmethod
def get_all_items(cls) -> Dict[int, List[BeamLoadItem]]:
```

**Example Output:**
```python
{
  115: [BeamLoadItem(...), BeamLoadItem(...)],
  220: [BeamLoadItem(...)]
}
```

---

## 🧩 Example: Creating and Sending Loads

```python
from midas.resources.element_beam_load import BeamLoadItem, BeamLoadResource

specs = [
    (115, BeamLoadItem(ID=1, LCNAME="WIND_X", P=[-10.0, -10.0, 0, 0])),
    (220, BeamLoadItem(ID=1, LCNAME="WIND_X", P=[-12.0, -12.0, 0, 0])),
]

BeamLoadResource.create_from_specs(specs)
```

---

## 💨 Integration with Wind-Load Workflow

This module fits seamlessly into the automated wind load generator pipeline:

1. Compute exposure and pressure per element.  
2. Create one `BeamLoadItem` per element with:  
   - `P`: wind pressure  
   - `LCNAME`: load case name  
   - `GROUP_NAME`: structural group for traceability  
   - `USE_ADDITIONAL_*`: exposure heights  
3. Combine into a list of `(element_id, BeamLoadItem)` pairs.  
4. Call `BeamLoadResource.create_from_specs(specs)`.  
5. Verify via `BeamLoadResource.get_all_items()`.

---

## 🔍 Verification Example

```python
loads = BeamLoadResource.get_all_items()
for eid, items in loads.items():
    for item in items:
        print(eid, item.LCNAME, item.P)
```

---

## 📊 Summary

| Class | Responsibility |
| ------ | --------------- |
| **BeamLoadItem** | Defines one beam load entry and handles conversion between Python and MIDAS JSON |
| **BeamLoadResource** | Communicates with `/db/bmld`: reads, builds, and writes beam load data |

---

✅ **In short:**  
`BeamLoadItem` models *what* the load looks like.  
`BeamLoadResource` handles *how* it’s sent to and retrieved from MIDAS.

