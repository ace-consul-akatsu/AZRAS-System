AZRAS Planning PATCH 622

Cause found: reported by the developer via screenshot. Module 2's
"8760時間比較を実行" (run 8760-hour comparison) raised a raw
"FileNotFoundError: [Errno 2] No such file or directory: ...epw" when
the selected weather file did not actually exist at its saved path
(confirmed case: a New York weather file whose Project JSON path no
longer pointed at a real file on disk).

Two things were true at once:
1. The real-world problem: the weather file genuinely was not present
   at that path. Re-selecting a weather file that does exist (confirmed
   by the developer using Nashville, TN) works correctly and was not a
   defect.
2. The code problem: services/dynamic_thermal_model_v9.py's
   read_weather() -- the function actually used by Module 2's 8760-hour
   comparison -- had no existence check before handing the path to
   pandas/open(), so a missing file surfaced as a raw, untranslated
   OSError instead of an actionable message. A sibling function,
   regional_analysis/hourly_comparison_engine.py's _read_epw() (used by
   the Regional Comparison screens), already had this exact check; it
   had not been applied to this second, independent weather-reading
   code path.

Behavior
- services/dynamic_thermal_model_v9.py: read_weather() now checks
  path.exists() before doing anything else, and raises a ValueError
  with a specific Japanese message naming the missing path and telling
  the user to re-fetch the weather data or pick the file manually,
  instead of letting pandas/open() raise a raw OSError.

Verified
- python -m py_compile passes for services/dynamic_thermal_model_v9.py.
- The existing regional_analysis/hourly_comparison_engine._read_epw()
  behavior is unchanged.

Not changed in this patch
- No calculation logic changed; only what happens when the weather file
  path does not resolve to a real file.
