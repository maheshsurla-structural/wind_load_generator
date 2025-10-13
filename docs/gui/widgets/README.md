# 🧩 GUI Widgets Documentation

**Folder:** `docs/widgets/`  
**Purpose:** This directory contains detailed documentation for all custom GUI widgets used in the **Wind Load Generator** application.  
Each widget is implemented in `gui/widgets/` and documented here for clarity, maintenance, and onboarding of new developers.

---

## 📘 Overview

Widgets are reusable Qt components that provide specialized parts of the Wind Load Generator user interface.  
They handle user inputs, data display, and internal communication with the core logic (via `MainWindow`, `UnitSystem`, or the event bus).

---

## 🧭 Index of Widgets

| Widget | Description | File | Documentation |
|:--------|:-------------|:------|:---------------|
| **WindParameters** | Panel for wind speed and exposure category inputs. | `gui/widgets/wind_parameters.py` | [📄 wind_parameters.md](wind_parameters.md) |
| **PressureTable** | Displays computed wind pressure data by structural group. | `gui/widgets/pressure_table.py` | [📄 pressure_table.md](pressure_table.md) |
| **ControlDataDialog** | Modal dialog for defining control data (naming, geometry, units). | `gui/dialogs/control_data.py` | [📄 ../dialogs/control_data.md](../dialogs/control_data.md) |
| **WindLoadInputDialog** | Input form for manual wind load data. | `gui/dialogs/wind_load_input.py` | [📄 ../dialogs/wind_load_input.md](../dialogs/wind_load_input.md) |
| **PairWindLoadCases** | Tool for pairing and managing generated wind load cases. | `gui/dialogs/pair_wind_load_cases.py` | [📄 ../dialogs/pair_wind_load_cases.md](../dialogs/pair_wind_load_cases.md) |

> 🧱 *Each widget focuses on a specific aspect of the application, keeping the main window clean and modular.*

---

## 🧠 Design Philosophy

- **Modularity:** Each widget encapsulates its logic and UI layout.  
- **Reusability:** Widgets can be embedded in dialogs or panels without modification.  
- **Consistency:** All widgets follow the same naming and layout structure.  
- **Maintainability:** Documentation matches file and class names for easy traceability.  

---

## 📂 Directory Structure

```
docs/
└── widgets/
    ├── wind_parameters.md
    ├── pressure_table.md
    ├── README.md  ← (this file)
gui/
└── widgets/
    ├── wind_parameters.py
    ├── pressure_table.py
```

---

## 🧩 Widget Lifecycle (in the Application)

```mermaid
graph TD
A[MainWindow] --> B(WindParameters)
A --> C(PressureTable)
A --> D(ControlDataDialog)
B -->|values()| E[Core Model / wind_db]
C -->|refresh()| E
D -->|controlDataChanged| A
```

This diagram shows how widgets connect with the main window and the backend data manager.

---

## 🧾 Coding Standards

To maintain consistency across widgets:
- Use `QGroupBox` titles that clearly describe purpose (e.g., “Wind Parameters”).  
- Use `QFormLayout` for label–field pairs.  
- Always right-align numeric inputs.  
- Provide `.values()` method to export widget state.  
- Use `try/except` blocks for safe data parsing.  
- Avoid direct database or file I/O — delegate to services.  

---

## 🧱 Example Template for New Widgets

If you’re adding a new widget to `gui/widgets/`, use this as a starting point:

```python
from PySide6.QtWidgets import QWidget, QGroupBox, QVBoxLayout, QFormLayout, QLabel, QLineEdit

class NewWidget(QWidget):
    """Brief description of what this widget does."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.group = QGroupBox("Title")
        layout = QFormLayout(self.group)
        layout.addRow(QLabel("Field:"), QLineEdit())

        root = QVBoxLayout(self)
        root.addWidget(self.group)

    def values(self) -> dict:
        """Return user input as dictionary."""
        return {}
```

When done, create a Markdown file under `docs/widgets/` following the same format as [`wind_parameters.md`](wind_parameters.md).

---

## 🧰 Useful References

- [Qt for Python Docs (PySide6)](https://doc.qt.io/qtforpython/)  
- [QWidget Class Reference](https://doc.qt.io/qtforpython/PySide6/QtWidgets/QWidget.html)  
- [QFormLayout Overview](https://doc.qt.io/qtforpython/PySide6/QtWidgets/QFormLayout.html)  

---

## 🗝️ TL;DR

> The widgets in this folder define the building blocks of the Wind Load Generator’s interface — each one documented separately for clarity and future scalability.

---
