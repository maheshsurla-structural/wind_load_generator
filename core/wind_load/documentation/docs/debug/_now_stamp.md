## `_now_stamp() -> str`

Return a compact timestamp string (in **local time**) suitable for use in IDs, folder names, and filenames.

This function is typically used to create a run identifier like `20251218_093012`.

---

### Implementation

```py
def _now_stamp() -> str:
    """Timestamp used for run_id (local time)."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")
```

---

### Line-by-line behavior

- `datetime.now()`
  - Gets the current date/time in the machine’s **local timezone**.
  - Example (conceptually): `2025-12-18 09:30:12.123456`

- `.strftime("%Y%m%d_%H%M%S")`
  - Formats the datetime into a filesystem-friendly string:

    - `%Y` = 4-digit year (e.g., `2025`)
    - `%m` = 2-digit month (01–12)
    - `%d` = 2-digit day (01–31)
    - `_`  = literal underscore separator
    - `%H` = 2-digit hour in 24-hour format (00–23)
    - `%M` = 2-digit minute (00–59)
    - `%S` = 2-digit second (00–59)

So the output always looks like:

```
YYYYMMDD_HHMMSS
```

---

### Examples

If the current local time is **Dec 18, 2025 at 09:30:12**, then:

```py
_now_stamp()
# "20251218_093012"
```

If the current local time is **Jan 3, 2026 at 17:05:09**, then:

```py
_now_stamp()
# "20260103_170509"
```

---

### Notes

- This string format is:
  - sortable by time (lexicographically sorts in chronological order)
  - safe in filenames (no colons or spaces)
- Resolution is **seconds** (multiple calls within the same second can return the same value).
  - If you need uniqueness beyond seconds, you’d add microseconds (not done here by design).
