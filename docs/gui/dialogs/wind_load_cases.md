# 🪟 `gui/dialogs/pair_wind_load_cases.py`

### 🧭 What this dialog does
This dialog is the little GUI tool that lets the user **pair wind angles** (0°, 15°, 30°, …) with **wind load case names** for two families of wind loads:

1. **WS** → *Wind on Structure*  
2. **WL** → *Wind on Live Load*

It:
- shows a table of load cases vs angles,
- auto-generates reasonable load case names using your **`WindLoadNamingSettings`** (so users don’t have to type everything),
- lets the user **hide/show** WS rows,
- loads/saves from/to your shared `wind_db`,
- emits a signal with a **clean dataclass model** when the user clicks **Apply**.

So it’s basically a **“wind-load naming + angle matrix editor”**.

---

## 📚 Table of Contents
1. [Data layer](#-data-layer)
2. [Naming helpers](#-naming-helpers)
3. [Table model: `WindLoadTableModel`](#-table-model-windloadtablemodel)
4. [Main dialog: `WindLoadCases`](#-main-dialog-windloadcases)
   - [UI build](#ui-build)
   - [Angle handling](#angle-handling)
   - [Autofill logic](#autofill-logic)
   - [WS row visibility](#ws-row-visibility)
   - [Persistence with `wind_db`](#persistence-with-wind_db)
5. [Data flow summary](#-data-flow-summary)

---

## 🧱 Data layer

### 1) `LoadCaseAssignment`
```python
@dataclass
class LoadCaseAssignment:
    case: str
    angle: int
    value: str
```
Represents **one cell** in the table, but in normalized form:
- `case`  → load case name (row)
- `angle` → angle in degrees (column)
- `value` → final text that user / autofill put in that cell (usually the MIDAS load case name to create)

This is what eventually goes to the DB.

---

### 2) `PairWindLoadModel`
```python
@dataclass
class PairWindLoadModel:
    ws_cases: List[LoadCaseAssignment] = field(default_factory=list)
    wl_cases: List[LoadCaseAssignment] = field(default_factory=list)
```
A **container** for everything in the dialog: one list for **WS**, one for **WL**.

It also has:

```python
def to_frames(self) -> Dict[str, pd.DataFrame]:
    return {
        "WS Cases": pd.DataFrame([asdict(a) for a in self.ws_cases]),
        "WL Cases": pd.DataFrame([asdict(a) for a in self.wl_cases]),
    }
```

So the dialog can hand off the result in a **pandas-friendly** format to whatever is storing it (`wind_db`).

---

## 🧩 Naming helpers

### `_parse_row_label(label: str) -> tuple[str, str]`
Purpose: figure out whether a row is **strength** or **service** and what its code is.

Examples:
- `"Strength III"` → `("strength", "III")`
- `"Service I"` → `("service", "I")`
- anything else → `("", "")`

This is needed so autofill knows whether to use the **strength label** or **service label** from `WindLoadNamingSettings`.

---

### `_compose_name(...) -> str`
```python
def _compose_name(
    cfg: WindLoadNamingSettings,
    *,
    base: str,
    limit_kind: str,
    case_code: str,
    angle: int | float,
) -> str:
    ...
    return cfg.text.template.format(**tokens)
```

This is the **central naming rule**.

It takes:
- the naming config from UI (`WindLoadNamingSettings`)
- the base (e.g. `"WS"`, `"WL"`, or whatever user defined)
- limit kind: `"strength"` or `"service"`
- case code: e.g. `"III"`
- angle: e.g. `15`

and feeds it into a **template** (from the settings!) like:

```text
{base}_{limit}{case}_{angle_prefix}{angle}
```

That way **all names stay consistent** with the user’s global naming settings.

---

## 📋 Table model: `WindLoadTableModel`

This is a reusable `QAbstractTableModel` for **“cases x angles”** tables.

### Constructor
```python
class WindLoadTableModel(QAbstractTableModel):
    def __init__(
        self,
        *,
        title: str,
        load_cases: Sequence[str],
        angles: Sequence[int],
        angle_prefix: str,
        show_case_column: bool,
    ) -> None:
        ...
```

- `title`: `"WS"` or `"WL"`, used to tweak autofill rules
- `load_cases`: rows (for WS it’s multiple, for WL it’s just `["WL"]`)
- `angles`: columns (0, 15, 30, …)
- `angle_prefix`: e.g. `"θ"` or `"Ang"` or `"Dir"`
- `show_case_column`: WS has a visible first column with the row name, WL does **not** (it has only 1 conceptual row)

Internally it stores **just the cell values** in:

```python
self._cells: list[list[str]]
```

one row per load case.

---

### Important overrides

- `rowCount`, `columnCount`: normal
- `data`: 
  - if `show_case_column` → first column is the load case name
  - the rest are the actual editable cells
- `setData`:
  - prevents editing the fixed first column
  - emits `dataChanged` properly
- `headerData`:
  - shows `"Load Case"` in column 0 if needed
  - otherwise shows e.g. `"θ 15"` for angles

---

### Model utilities

#### `replace_angles(...)`
Used when the **user changes the number/value of angles** in the top panel.  
It resizes the internal `_cells` to match the new angle count.

#### `set_cell(row, angle, value)`
Lets the dialog set a cell by **angle value**, not by column index — nicer and more resilient.

#### `to_assignments() -> List[LoadCaseAssignment]`
This is what the dialog uses to **collect everything** the user entered.

It walks all rows and angles and returns only **non-empty** cells, already normalized to:

```python
LoadCaseAssignment(case=..., angle=..., value=...)
```

Note the WL special case:
```python
case_name = case if self.show_case_column else self.title
```
→ if there is no case column (WL), we use the table title as the case name.

---

## 🪟 Main dialog: `WindLoadCases`

```python
class WindLoadCases(QDialog):
    dataChanged = Signal(PairWindLoadModel)
    ...
```

This is the actual pop-up.

It:

1. builds the UI (angles bar + WS table + WL table + buttons),
2. pulls existing data from `wind_db`,
3. auto-fills missing cells,
4. on **Apply** → converts models to dataclasses → persists → emits signal.

---

### UI build

- **Top group**: “Angle Configuration”
  - number of angles (`QSpinBox`)
  - up to 5 drop-downs (`QComboBox`) to pick angle values
- **Middle group 1**: “Wind on Structure (WS)”
  - a **row of checkboxes** to show/hide WS cases
  - a table view with the `WindLoadTableModel`
- **Middle group 2**: “Wind on Live Load (WL)”
  - single-row table (no case column)
- **Bottom row**: `Apply` + `Close`

---

## 🧮 Angle handling

Angles are **driven by the top bar**.

- `self.MAX_ANGLES = 5` → UI allows up to 5
- user changes number → `_on_num_angles_changed`
  - enables/disables the angle combo boxes
  - calls `_rebuild_models()`
- user changes angle text → `_on_angle_text_changed` → `_rebuild_models()`

**Why rebuild?**  
Because both WS and WL tables depend on the **current set of angles**, so we create **new models** with the new angle list.

```python
self.ws_model = WindLoadTableModel(...)
self.wl_model = WindLoadTableModel(...)
```

and then we **swap the table widget** with `_replace_last_widget(...)`.

---

## 🪄 Autofill logic

After rebuilding, the dialog calls:

```python
self._autofill_all()
```

which calls `_autofill_model(...)` for both WS and WL.

### `_autofill_model(...)`
For each row + angle:
1. figure out if this row is **strength** or **service** with `_parse_row_label`
2. if it’s WL and has no strength/service → force `"service"`
3. **skip** if the cell already has a value (don’t overwrite user input)
4. otherwise **build a name**:
   - for WL → simpler: `f"{base}_{prefix}{angle}"`
   - for WS → full template via `_compose_name(...)`

Finally it emits `dataChanged` for the whole data area so the view repaints.

---

## ✅ WS row visibility

The WS group has a checkbox **per load case** (coming from `LOAD_CASES` in `wind_database`).

When a checkbox is toggled:
- we recompute the **visible WS cases**
- ensure **at least one** is always visible
- rebuild the models (so the table has those rows only)
- autofill again

This lets the user say: “for this model I only care about Service I and Strength III”.

---

## 💾 Persistence with `wind_db`

### On Apply
```python
def _on_apply(self) -> None:
    ws_assignments = self.ws_model.to_assignments()
    wl_assignments = self.wl_model.to_assignments()
    model = PairWindLoadModel(ws_cases=ws_assignments, wl_cases=wl_assignments)

    wind_db.ws_cases = pd.DataFrame([...])
    wind_db.wl_cases = pd.DataFrame([...])
    wind_db.update_wind_pressures()

    self.dataChanged.emit(model)
    QMessageBox.information(...)
    self.accept()
```

So it does **three** things:

1. **Saves** WS + WL to the shared `wind_db` object (as DataFrames)
2. **Triggers** `wind_db.update_wind_pressures()` → so the rest of the app reacts
3. **Emits** `dataChanged` with a clean dataclass → so the GUI / controller layer can react

Errors are logged (`log.exception(...)`) and shown as a message box.

---

### On Load (`_load_from_db`)
When the dialog opens, it tries to **restore** the last user configuration:

1. `wind_db.get_data()` → returns something like:
   - `"WS Cases"` → DataFrame
   - `"WL Cases"` → DataFrame
2. If there are angles in DB → **update the top angle bar** to match
3. If WS has only some cases → update the **checkboxes** to match
4. Then re-create the models and **write the cell values back** with `set_cell(...)`
5. Finally call `_autofill_all()` to fill in blanks

So the dialog is **stateful** between runs.

---

## 🔄 Data flow summary

```text
DB (wind_db)  ──► dialog opens ──► _load_from_db()
                            │
                            ▼
                   user edits tables
                            │
                            ▼
                   user clicks Apply
                            │
                            ▼
               tables → assignments → PairWindLoadModel
                            │
                            ├─► write back to wind_db (as DataFrames)
                            ├─► wind_db.update_wind_pressures()
                            └─► emit dataChanged(model)
```

---

## 📝 Key ideas

- **Two tables, same logic** → reuse `WindLoadTableModel`
- **Angles drive everything** → change angles → rebuild models
- **Autofill is non-destructive** → it won’t overwrite existing cells
- **Naming is centralized** in `WindLoadNamingSettings`
- **Persistence** is via `wind_db` in pandas format
- **Signal** exposes a clean dataclass to the rest of the app

---
