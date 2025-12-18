## `_safe_name(name: str) -> str`

Convert an arbitrary label into a **filesystem-friendly** single path component (safe to use in folder/file names).

This is used to ensure labels like `"ALL WIND / Case: 1"` don’t produce invalid or awkward paths.

---

### What it does

- Replaces “unsafe” characters with `_`
- Collapses repeated underscores (`"___"` → `"_"`)
- Strips leading/trailing underscores
- Avoids edge-case names like `""`, `"."`, or `".."` (returns `"unnamed"`)
- Caps length to avoid OS/path-length issues

---

### Implementation

```py
def _safe_name(name: str) -> str:
    """
    Convert an arbitrary label into a filesystem-friendly single path component.

    - Replaces unsafe characters with "_"
    - Collapses repeated underscores
    - Avoids empty/relative names
    """
    s = str(name or "").strip()
    s = _SAFE_CHARS_RE.sub("_", s)
    s = _UNDERSCORE_RUN_RE.sub("_", s).strip("_")

    # Avoid edge-case path components that are legal but undesirable.
    if not s or s in {".", ".."}:
        return "unnamed"

    # Optional: keep names from getting absurdly long.
    # (Still deterministic; avoids OS/path limits in practice.)
    return s[:128]
```

> Note: this function expects these module-level regexes to exist:
>
> - `_SAFE_CHARS_RE = re.compile(r"[^\w\-\.]+")`
> - `_UNDERSCORE_RUN_RE = re.compile(r"_+")`

---

### Line-by-line behavior

#### 1) Normalize input into a trimmed string

- `s = str(name or "").strip()`
  - If `name` is `None` or empty, uses `""`.
  - Converts to string.
  - Removes leading/trailing whitespace.

Examples:

```py
_safe_name("  Beam Load  ")   # input becomes "Beam Load"
_safe_name(None)              # input becomes ""
```

---

#### 2) Replace unsafe characters with underscores

- `s = _SAFE_CHARS_RE.sub("_", s)`

`_SAFE_CHARS_RE` is:

```py
re.compile(r"[^\w\-\.]+")
```

Meaning: replace any run (`+`) of characters that are **NOT**:
- `\w`  → letters, digits, underscore
- `-`   → hyphen
- `.`   → dot

Examples:

```py
_safe_name("ALL WIND / Case: 1")
# "ALL_WIND_Case_1"

_safe_name("a:b*c?d")
# "a_b_c_d"
```

---

#### 3) Collapse repeated underscores and strip at the ends

- `s = _UNDERSCORE_RUN_RE.sub("_", s).strip("_")`

`_UNDERSCORE_RUN_RE` is:

```py
re.compile(r"_+")
```

This means:
- `"a___b"` becomes `"a_b"`
- `.strip("_")` removes leading/trailing underscores

Examples:

```py
# after unsafe replacement you might get lots of underscores:
name = "  / ALL   WIND /  "
# could become "___ALL_WIND___"
# then collapse + strip => "ALL_WIND"
```

---

#### 4) Guard against empty or special relative path names

```py
if not s or s in {".", ".."}:
    return "unnamed"
```

- `""` would be a bad filename component.
- `"."` and `".."` are legal but dangerous/meaningful path segments.

Examples:

```py
_safe_name("")     # "unnamed"
_safe_name("   ")  # "unnamed"
_safe_name(".")    # "unnamed"
_safe_name("..")   # "unnamed"
```

---

#### 5) Cap output length

```py
return s[:128]
```

- Limits the string to 128 characters.
- Helps avoid problems with very long labels (common when labels contain many tokens).

Example:

```py
_safe_name("A" * 500)  # returns 128 "A" characters
```

---

### Quick examples

```py
_safe_name("ALL WIND / Case: 1")        # "ALL_WIND_Case_1"
_safe_name("  Beam Load  ")             # "Beam_Load"
_safe_name("a___b")                     # "a_b"
_safe_name("////")                      # "unnamed"
_safe_name("..")                        # "unnamed"
_safe_name("report.v1-final")           # "report.v1-final"
_safe_name("नमस्ते / hello")            # "नमस्ते_hello"  (unicode preserved; slash replaced)
```

---

### Typical usage in this project

Used to build safe directory/file names like:

- `wind_debug/<run_id>_<run_label>/...`
- `apply/<label>.json`

So labels coming from UI / load-case names don’t break file paths.
