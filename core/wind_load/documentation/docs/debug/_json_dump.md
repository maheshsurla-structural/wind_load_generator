## `_json_dump(path: Path, obj: Any) -> None`

Atomically writes a Python object to disk as **pretty JSON**.

This helper is built to prevent **partial / corrupted JSON files** if the process crashes mid-write. It writes to a temporary file in the same directory and then atomically replaces the target file.

---

### Why atomic writing matters

If you write directly to the final file and the process crashes mid-write, you can end up with:

- truncated JSON
- invalid JSON
- half-written content that breaks later debugging

With temp-file + replace, readers see either:

- the old complete file, or
- the new complete file

…but never a partial one.

---

### Implementation

```py
def _json_dump(path: Path, obj: Any) -> None:
    """
    Write JSON to disk atomically:
    - create parent dirs
    - write to a temp file in the same directory
    - replace the target file
    This prevents partial/corrupt files if the process crashes mid-write.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = json.dumps(obj, indent=2, ensure_ascii=False, default=str)

    # Atomic replace requires temp file on same filesystem -> use same dir.
    tmp_fd: int | None = None
    tmp_path: Path | None = None
    try:
        tmp_fd, tmp_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=str(path.parent),
            text=True,
        )
        tmp_path = Path(tmp_name)

        with open(tmp_fd, "w", encoding="utf-8") as f:
            f.write(payload)
            f.write("\n")  # friendly newline at EOF

        tmp_path.replace(path)  # atomic on most OS/filesystems
    finally:
        # If something failed before replace, best-effort cleanup.
        if tmp_path is not None and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
```

---

### Line-by-line behavior

#### 1) Normalize the path and ensure the directory exists

- `path = Path(path)`
  - Converts `path` to a `pathlib.Path` (works even if you pass a string).

- `path.parent.mkdir(parents=True, exist_ok=True)`
  - Creates the parent directory tree if missing.
  - Does nothing if it already exists.

Example:

```py
path = Path("wind_debug/run_1/apply/ALL_WIND.json")
path.parent  # -> Path("wind_debug/run_1/apply")
```

---

#### 2) Serialize the object to a JSON string (in memory)

- `payload = json.dumps(obj, indent=2, ensure_ascii=False, default=str)`
  - Produces a JSON **string** (not a file yet).
  - `indent=2`: pretty-printed output.
  - `ensure_ascii=False`: keeps Unicode readable.
  - `default=str`: converts unsupported types using `str(...)` instead of failing.

Example:

```py
obj = {"when": datetime(2025, 12, 18, 9, 30), "path": Path("a/b")}
```

Produces JSON similar to:

```json
{
  "when": "2025-12-18 09:30:00",
  "path": "a/b"
}
```

---

#### 3) Create a temp file in the same directory

- `tempfile.mkstemp(...)`
  - Creates a real temporary file and returns:
    - `tmp_fd`: OS-level file descriptor (an `int`)
    - `tmp_name`: temp file path as a string
  - `dir=str(path.parent)` ensures the temp file is on the **same filesystem**, which is important for atomic replace.

Example temp file name:

- Target: `apply/ALL_WIND.json`
- Temp: `apply/.ALL_WIND.json.x7k3p9.tmp`

---

#### 4) Write the JSON to the temp file

- `with open(tmp_fd, "w", encoding="utf-8") as f:`
  - Opens the file descriptor for text writing.

- `f.write(payload)`
  - Writes the full JSON string.

- `f.write("\n")`
  - Adds a trailing newline (nice for diffs and CLI viewing).

---

#### 5) Atomically replace the final file

- `tmp_path.replace(path)`
  - Replaces the target file with the temp file in (typically) one atomic operation.
  - If the target already exists, it gets replaced.

This is the key step that prevents partially-written files.

---

#### 6) Cleanup on failure (best effort)

The `finally:` block runs even if something fails.

- If an exception happens before `replace()`, the temp file may remain.
- This cleanup attempts to delete it, but never raises if deletion fails.

---

### Quick usage example

```py
_json_dump(Path("out/test.json"), {"a": 1, "b": [2, 3]})
```

Result (`out/test.json`):

```json
{
  "a": 1,
  "b": [
    2,
    3
  ]
}
```
