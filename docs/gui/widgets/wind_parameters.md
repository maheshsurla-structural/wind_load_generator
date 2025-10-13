# 🌬️ `WindParameters` Widget

**File:** `gui/widgets/wind_parameters.py`  
**Purpose:** Provides user inputs for *wind speed* and *exposure category* in the Wind Load Generator GUI.

---

## 📖 Overview

`WindParameters` is a reusable `QWidget` that groups two simple inputs:

| Field | Widget | Type | Default |
|:------|:--------|:------|:---------|
| **Wind Speed (mph)** | `QLineEdit` | Numeric (string → float) | `150` |
| **Exposure Category** | `QComboBox` | Enum [`B`, `C`, `D`] | `C` |

This panel assumes wind speed is always entered in **miles per hour** (no global unit conversion).

---

## 🧱 Class Definition

```python
class WindParameters(QWidget):
    """Simple panel for wind speed and exposure category inputs."""
```

### Inheritance

`QObject → QWidget → WindParameters`

### Dependencies

- `PySide6.QtWidgets`
- `PySide6.QtGui.QDoubleValidator`
- `PySide6.QtCore.Qt`

---

## 🧩 Layout Hierarchy

```
WindParameters (QWidget)
└── QVBoxLayout
      └── QGroupBox("Wind Parameters")
            └── QFormLayout
                 ├── QLabel("Wind Speed (mph):") → QLineEdit
                 └── QLabel("Exposure Category:") → QComboBox
```

---

## 🧠 Constructor `__init__(self, parent=None)`

Initializes all child widgets and layouts.

| Step | Code | Description |
|:--:|:--|:--|
| 1️⃣ | `self.groupBox = QGroupBox("Wind Parameters")` | Titled container for inputs. |
| 2️⃣ | `form_layout = QFormLayout(self.groupBox)` | Creates two-column (label / field) layout. |
| 3️⃣ | `self.wind_speed = QLineEdit("150")` | Text field initialized with 150 mph. |
| 4️⃣ | `setAlignment(Qt.AlignRight)` | Right-aligns numbers for readability. |
| 5️⃣ | `setValidator(QDoubleValidator(0.0, 400.0, 2, self))` | Restricts input to 0.00–400.00. |
| 6️⃣ | `self.exposure = QComboBox()` | Dropdown with options `B`, `C`, `D`. |
| 7️⃣ | `layout = QVBoxLayout(self)` | Outer layout that holds the group box. |

---

## 💬 Validation Details

`QDoubleValidator(0.0, 400.0, 2, self)` ensures:
- only digits, decimal point, and optional sign are allowed;  
- minimum = 0.00, maximum = 400.00;  
- precision = 2 decimal places.

The placeholder `"Enter wind speed (mph)"` guides the user when the field is empty.

---

## 🎛️ Public API

### `values(self) → dict`

Returns a Python dictionary containing the current form data.

```python
def values(self) -> dict:
    """Return the form data as a dictionary."""
    try:
        ws = float((self.wind_speed.text() or "0").strip())
    except ValueError:
        ws = 0.0
    return {
        "Wind Speed": ws,
        "Exposure Category": self.exposure.currentText(),
    }
```

#### Behavior
1. Reads text from the line-edit.  
2. Replaces empty string with `"0"`.  
3. Strips whitespace.  
4. Converts to `float`; on error defaults to `0.0`.  
5. Returns selected exposure category.  

#### Example Output
```json
{
  "Wind Speed": 150.0,
  "Exposure Category": "C"
}
```

---

## 🔄 Integration in MainWindow

```python
self.wind_parameters = WindParameters(self)
main_layout.addWidget(self.wind_parameters)

# Retrieve values
params = self.wind_parameters.values()
print(params)
# → {'Wind Speed': 150.0, 'Exposure Category': 'C'}
```

---

## 🪄 Visual Representation

```
┌────────────────────────────────────┐
│  Wind Parameters                   │
│  ┌──────────────────────────────┐  │
│  │ Wind Speed (mph):  [ 150  ] │  │
│  │ Exposure Category: [  C ▼ ] │  │
│  └──────────────────────────────┘  │
└────────────────────────────────────┘
```

---

## 💡 Design Notes

- Independent of global unit system (always mph).  
- Uses Qt’s layout system for automatic resizing.  
- Failsafe numeric parsing prevents exceptions.  
- Clean API (`values()`) decouples UI from business logic.  
- Easy to extend with `.set_values()` or `parametersChanged` signal later.

---

## 🚀 Possible Enhancements

- **Add tooltips** explaining each field.  
- **Implement `.set_values(data)`** to restore saved settings.  
- **Emit a `parametersChanged` signal** whenever a value changes.  
- **Add unit selector** to support m/s or km/h in future versions.

---

## 🧾 Summary

| Component | Purpose |
|:-----------|:---------|
| `QGroupBox` | Visually groups related controls. |
| `QFormLayout` | Aligns labels and widgets neatly. |
| `QLineEdit` + `QDoubleValidator` | Validated numeric input for wind speed. |
| `QComboBox` | Fixed choices for exposure category. |
| `values()` | Converts user input into plain dictionary. |

---

## 🗝️ TL;DR

> **`WindParameters`** → a self-contained, validated form for entering wind speed and exposure category.  
> Returns clean Python data for use by the core calculation modules.

---
