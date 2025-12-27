## `_validate_axis(axis: str) -> str`

Validate and normalize an axis input so downstream code can safely assume it is either `"y"` or `"z"`.

This helper:
- converts the input to a string
- trims whitespace
- lowercases it
- checks it is one of the allowed axis values: `{"y", "z"}`
- returns the normalized axis (`"y"` or `"z"`)
- otherwise raises a `ValueError`

---

### Implementation

```py
def _validate_axis(axis: str) -> str:
    ax = str(axis).strip().lower()
    if ax not in {"y", "z"}:
        raise ValueError(f"axis must be 'y' or 'z', got {axis!r}")
    return ax
```

---

## Step-by-step explanation

### 1) Normalize the input

```py
ax = str(axis).strip().lower()
```

What this does:

- `str(axis)`  
  Ensures the value is treated as a string even if the caller passed an int/None/etc.

- `.strip()`  
  Removes leading/trailing whitespace.

- `.lower()`  
  Converts to lowercase so `"Y"` and `"y"` are treated the same.

Examples:

```py
_validate_axis("Y")      # ax becomes "y"
_validate_axis("  z ")   # ax becomes "z"
_validate_axis(" y\n")   # ax becomes "y"
```

---

### 2) Validate allowed values

```py
if ax not in {"y", "z"}:
    raise ValueError(f"axis must be 'y' or 'z', got {axis!r}")
```

- Checks if the normalized value is either `"y"` or `"z"`.
- If not, raises a `ValueError` with a helpful message.
- `{axis!r}` uses Python “repr” formatting so you can clearly see what was passed.

Examples:

```py
_validate_axis("x")
# ValueError: axis must be 'y' or 'z', got 'x'

_validate_axis("")
# ValueError: axis must be 'y' or 'z', got ''

_validate_axis(None)
# ValueError: axis must be 'y' or 'z', got None
```

---

### 3) Return normalized axis

```py
return ax
```

If validation passes, return `"y"` or `"z"` (always lowercase).

---

## Worked examples

### Valid inputs

```py
_validate_axis("y")     # "y"
_validate_axis("Y")     # "y"
_validate_axis(" z ")   # "z"
_validate_axis("\nZ")   # "z"
```

### Invalid inputs

```py
_validate_axis("x")       # raises ValueError
_validate_axis("yz")      # raises ValueError
_validate_axis("")        # raises ValueError
_validate_axis(None)      # raises ValueError
_validate_axis(123)       # raises ValueError (ax becomes "123")
```

---

## Why this helper is useful

Without `_validate_axis`, many functions end up doing “silent defaults” like:

```py
col = "exposure_z" if axis == "z" else "exposure_y"
```

That can hide bugs, because `"Z "` or `"X"` might accidentally get treated as `"y"`.

With `_validate_axis`, bad input fails early and loudly, making debugging much easier.
