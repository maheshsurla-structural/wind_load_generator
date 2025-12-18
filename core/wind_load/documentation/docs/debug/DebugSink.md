## `DebugSink`

A minimal, **run-scoped** debug sink that writes structured JSON artifacts to disk.

Its primary job is to capture **the exact PUT payload(s)** sent to MIDAS (e.g., from `apply_beam_load_plan_to_midas()`), and store them under a deterministic “run folder” along with a `manifest.json` index.

---

### Outputs

Given:

- `base_dir = wind_debug/` (default)
- `run_id = 20251218_093012`
- `run_label = WIND`
- `label = ALL_WIND`

The sink writes:

- `wind_debug/20251218_093012_WIND/manifest.json`
- `wind_debug/20251218_093012_WIND/apply/ALL_WIND.json`

---

### Class definition (for reference)

```py
class DebugSink:
    """
    Minimal run-scoped debug sink.

    Behavior:
      - When enabled: write JSON artifacts under a run directory.
      - Primary artifact: ONE JSON file containing the exact PUT payload(s)
        sent to MIDAS by apply_beam_load_plan_to_midas().

    Output:
      wind_debug/<run_id>_<run_label>/apply/<label>.json
    """
    enabled: bool = False
    base_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent / "wind_debug")
    run_label: str = "WIND"
    run_id: str = field(default_factory=_now_stamp)

    # internal manifest (optional but handy)
    manifest: Dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        # Normalize base_dir early (nice for consistent manifests).
        self.base_dir = Path(self.base_dir)

        if not self.enabled:
            return

        # Initialize manifest once per run.
        self.manifest = {
            "run_id": self.run_id,
            "run_label": self.run_label,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "artifacts": [],
        }
        self._write_manifest()

    @property
    def run_dir(self) -> Path:
        # Derive run directory deterministically from id + label.
        return self.base_dir / f"{self.run_id}_{_safe_name(self.run_label)}"

    def _add_artifact(self, kind: str, path: Path, meta: Optional[Dict[str, Any]] = None) -> None:
        if not self.enabled:
            return

        # Be defensive: ensure manifest shape even if someone toggles enabled late.
        if not self.manifest:
            self.manifest = {
                "run_id": self.run_id,
                "run_label": self.run_label,
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "artifacts": [],
            }
        self.manifest.setdefault("artifacts", []).append(
            {"kind": str(kind), "path": str(path), "meta": meta or {}}
        )
        self._write_manifest()

    def _write_manifest(self) -> None:
        if not self.enabled:
            return
        _json_dump(self.run_dir / "manifest.json", self.manifest)

    def dump_apply_payload(self, *, label: str, put_payloads: list[dict]) -> None:
        """
        Write exactly ONE JSON file containing the exact payload(s) sent to MIDAS PUT.

        Parameters
        ----------
        label : str
            Usually debug_label from apply_beam_load_plan_to_midas (e.g. "ALL_WIND")
        put_payloads : list[dict]
            List of raw payloads passed to BeamLoadResource.put_raw(),
            each typically like {"Assign": {...}}.
        """
        if not self.enabled:
            return

        safe_label = _safe_name(label)
        out_path = self.run_dir / "apply" / f"{safe_label}.json"

        payload = {
            "label": str(label),
            "n_puts": int(len(put_payloads)),
            "puts": put_payloads,  # keep exact structure
        }

        _json_dump(out_path, payload)
        self._add_artifact(
            "apply_payload",
            out_path,
            {"label": str(label), "n_puts": int(len(put_payloads))},
        )
```

---

## Fields and initialization

### `enabled: bool = False`

- Master switch.
- If `enabled` is `False`, the sink becomes a no-op:
  - no folders are created
  - no files are written
  - all dump methods return immediately

Example:

```py
dbg = DebugSink(enabled=False)
dbg.dump_apply_payload(label="ALL_WIND", put_payloads=[{"Assign": {...}}])
# writes nothing
```

---

### `base_dir: Path = .../wind_debug`

- Base output directory for all debug artifacts.
- Default is `wind_debug` next to this module:

```py
Path(__file__).resolve().parent / "wind_debug"
```

Example resolved output:

```
core/wind_load/wind_debug/
```

---

### `run_label: str = "WIND"`

- A human-readable label used as part of the run folder name.
- Is sanitized via `_safe_name()` before being used in a path.

---

### `run_id: str = field(default_factory=_now_stamp)`

- Unique-ish identifier for the run (second resolution).
- Default comes from `_now_stamp()` (e.g., `20251218_093012`).

---

### `manifest: Dict[str, Any]`

- A small index describing what the sink wrote.
- Stored in `manifest.json` under the run directory.
- `repr=False` means it won’t appear in `DebugSink(...)` string representation (keeps logs clean).

---

## `__post_init__()`

```py
def __post_init__(self) -> None:
    self.base_dir = Path(self.base_dir)

    if not self.enabled:
        return

    self.manifest = {
        "run_id": self.run_id,
        "run_label": self.run_label,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "artifacts": [],
    }
    self._write_manifest()
```

### What it does

1. **Normalizes `base_dir` to a `Path`**
   - This ensures downstream code can reliably do path operations.

2. **If disabled, returns immediately**
   - Avoids directory creation and IO.

3. **If enabled, initializes the manifest**
   - Records:
     - `run_id`
     - `run_label`
     - `created_at` (ISO timestamp, second precision)
     - `artifacts` list (starts empty)

4. **Writes `manifest.json` immediately**
   - So even if no artifacts are written later, the run folder has a record.

---

## `run_dir` property

```py
@property
def run_dir(self) -> Path:
    return self.base_dir / f"{self.run_id}_{_safe_name(self.run_label)}"
```

### What it does

Computes the output folder for this run:

```
<base_dir>/<run_id>_<safe_run_label>/
```

Example:

- `run_id = "20251218_093012"`
- `run_label = "ALL WIND / Case: 1"`
- `_safe_name(run_label) = "ALL_WIND_Case_1"`

Result:

```
wind_debug/20251218_093012_ALL_WIND_Case_1/
```

---

## `_write_manifest()`

```py
def _write_manifest(self) -> None:
    if not self.enabled:
        return
    _json_dump(self.run_dir / "manifest.json", self.manifest)
```

### What it does

Writes (or rewrites) the manifest file at:

```
<run_dir>/manifest.json
```

This is called:
- once during initialization (`__post_init__`)
- again after every artifact is added

---

## `_add_artifact(kind, path, meta=None)`

```py
def _add_artifact(self, kind: str, path: Path, meta: Optional[Dict[str, Any]] = None) -> None:
    if not self.enabled:
        return

    if not self.manifest:
        self.manifest = {...}

    self.manifest.setdefault("artifacts", []).append(
        {"kind": str(kind), "path": str(path), "meta": meta or {}}
    )
    self._write_manifest()
```

### What it does

Adds an artifact record to the manifest and persists it.

- Early returns if disabled.
- Defensively initializes the manifest if it’s unexpectedly empty (e.g., someone toggled `enabled` late).
- Ensures `manifest["artifacts"]` exists.
- Appends:

```json
{
  "kind": "apply_payload",
  "path": "wind_debug/.../apply/ALL_WIND.json",
  "meta": { "label": "ALL_WIND", "n_puts": 2 }
}
```

- Calls `_write_manifest()` to persist changes.

---

## `dump_apply_payload(label, put_payloads)`

This is the main public method used by your wind-load pipeline.

```py
def dump_apply_payload(self, *, label: str, put_payloads: list[dict]) -> None:
    if not self.enabled:
        return

    safe_label = _safe_name(label)
    out_path = self.run_dir / "apply" / f"{safe_label}.json"

    payload = {
        "label": str(label),
        "n_puts": int(len(put_payloads)),
        "puts": put_payloads,
    }

    _json_dump(out_path, payload)
    self._add_artifact("apply_payload", out_path, {"label": str(label), "n_puts": int(len(put_payloads))})
```

### Key behaviors

- **Keyword-only parameters** (`*`) enforce calls like:

```py
dbg.dump_apply_payload(label="ALL_WIND", put_payloads=[...])
```

- Writes exactly **one JSON file** per call:

```
<run_dir>/apply/<safe_label>.json
```

- Stores:
  - original `label`
  - count of PUT payloads (`n_puts`)
  - the raw list of payload dicts (`puts`) unchanged

- Registers the file in `manifest.json` via `_add_artifact`.

---

## End-to-end example

```py
dbg = DebugSink(enabled=True, run_label="WIND")

put_payloads = [
    {"Assign": {"1": {"LCNAME": "W1", "ITEMS": [{"ELEM": 10, "VAL": 1.2}]}}}},
    {"Assign": {"2": {"LCNAME": "W1", "ITEMS": [{"ELEM": 11, "VAL": 1.1}]}}}},
]

dbg.dump_apply_payload(label="ALL_WIND", put_payloads=put_payloads)
```

Creates:

```
wind_debug/<run_id>_WIND/
  manifest.json
  apply/
    ALL_WIND.json
```

`apply/ALL_WIND.json` contains:

```json
{
  "label": "ALL_WIND",
  "n_puts": 2,
  "puts": [
    { "Assign": { "1": { "LCNAME": "W1", "ITEMS": [ ... ] } } },
    { "Assign": { "2": { "LCNAME": "W1", "ITEMS": [ ... ] } } }
  ]
}
```

And `manifest.json` lists that artifact under `artifacts`.
