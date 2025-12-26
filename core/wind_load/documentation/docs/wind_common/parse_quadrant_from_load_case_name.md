## `_QUADRANT_RE` and `parse_quadrant_from_load_case_name(name: str) -> int`

These two lines work together to extract a **quadrant number (1–4)** from a load case name.

- Quadrants are expected to appear in the name as either:
  - `_Q1`, `_Q2`, `_Q3`, `_Q4` (underscore + Q)
  - `Q1`, `Q2`, `Q3`, `Q4` (plain Q)
- Matching is **case-insensitive** (`Q1`, `q1`, `_q3`, etc. all work).
- If no quadrant marker is found, the function defaults to **Q1** (returns `1`).

---

### Code (for reference)

```py
_QUADRANT_RE = re.compile(r"(?:_Q|Q)([1-4])\b", re.I)

def parse_quadrant_from_load_case_name(name: str) -> int:
    """Parse Q1..Q4 from case name. Defaults to Q1 if missing."""
    m = _QUADRANT_RE.search(name or "")
    return int(m.group(1)) if m else 1
```

---

## Regex: `_QUADRANT_RE`

```py
_QUADRANT_RE = re.compile(r"(?:_Q|Q)([1-4])\b", re.I)
```

### What it matches

The pattern `r"(?:_Q|Q)([1-4])\b"` means:

1. `(?:_Q|Q)`
   - A **non-capturing group** matching either:
     - `_Q` (underscore + Q), or
     - `Q` (just Q)

2. `([1-4])`
   - A **capturing group** that matches a single digit `1`, `2`, `3`, or `4`
   - This is the part the function returns.

3. `\b`
   - A **word boundary**
   - Ensures the digit ends cleanly (helps avoid matching digits that are part of a longer word/number).

4. `re.I` (aka `re.IGNORECASE`)
   - Makes the match case-insensitive:
     - `Q1`, `q1`, `_Q2`, `_q3`, etc.

### Example matches

| Name snippet       | Matches? | Captured digit |
|-------------------|----------|----------------|
| `WL_Q1_0`         | ✅       | `1`            |
| `WLQ2_15`         | ✅       | `2`            |
| `wind_q3`         | ✅       | `3`            |
| `CASE-Q4`         | ✅       | `4`            |
| `Q5`              | ❌       | — (only 1–4)   |

> Note: because of `(?:_Q|Q)`, strings like `WLQ2_15` match as well (the `Q2` part is present even without `_Q`).

---

## Function: `parse_quadrant_from_load_case_name`

```py
def parse_quadrant_from_load_case_name(name: str) -> int:
    """Parse Q1..Q4 from case name. Defaults to Q1 if missing."""
    m = _QUADRANT_RE.search(name or "")
    return int(m.group(1)) if m else 1
```

### Step-by-step behavior

#### 1) Safe handling of `None` input

```py
name or ""
```

- If `name` is `None` (or empty), this becomes `""`.
- Prevents errors in regex search.

#### 2) Search for the first quadrant token

```py
m = _QUADRANT_RE.search(name or "")
```

- `.search()` finds the **first match anywhere** in the string.
- If found:
  - `m` is a match object
- If not found:
  - `m` is `None`

#### 3) Return quadrant integer or default

```py
return int(m.group(1)) if m else 1
```

- If a match exists:
  - `m.group(1)` returns the captured digit (`"1"`..`"4"`)
  - `int(...)` converts it to `1`..`4`
- If no match:
  - defaults to `1` (Q1)

---

## Examples

### Typical load case names

```py
parse_quadrant_from_load_case_name("WL_Q1_0")     # -> 1
parse_quadrant_from_load_case_name("WL_Q2_15")    # -> 2
parse_quadrant_from_load_case_name("WL_q3_30")    # -> 3   (case-insensitive)
parse_quadrant_from_load_case_name("WLQ4_60")     # -> 4   (matches plain Q4)
```

### Names without quadrant markers (defaults to Q1)

```py
parse_quadrant_from_load_case_name("WL_15")   # -> 1
parse_quadrant_from_load_case_name("")        # -> 1
parse_quadrant_from_load_case_name(None)      # -> 1
```

### Edge cases

- Multiple quadrant markers: the **first** match wins.

```py
parse_quadrant_from_load_case_name("WL_Q2_Q4_15")  # -> 2
```

- The regex only allows digits 1–4.

```py
parse_quadrant_from_load_case_name("WL_Q5_0")  # -> 1 (no match => default)
```

---

## Why the default is Q1

Defaulting to `1` avoids failing when quadrant info is missing, and allows downstream logic to treat “no quadrant” as the standard/positive-sign convention (commonly Q1). If quadrant markers are required, callers should validate names upstream instead of relying on the default.
