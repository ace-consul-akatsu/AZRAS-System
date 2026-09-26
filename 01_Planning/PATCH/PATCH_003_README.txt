PATCH_003 — module2/app.py: add graph button to the 8760-hour insulation/thermal-mass comparison dialog

Request: from the "断熱・蓄熱 8760時間比較" dialog, the user can already
save multiple comparison scenarios (different insulation material/
thickness/position) as dated JSON/CSV archives under
<Project folder>/8760_Comparison/. There was no way to visually compare
several saved scenarios' energy results side by side; comparing them
meant opening each saved file individually.

Added:
- ui/graph.py: new MultiSeriesBarChart (tk.Canvas subclass, no matplotlib
  dependency, drawn in the same plain-Canvas style already used by
  regional_analysis/module10_ui.py's BarChart/LineChart).
- module2/app.py: new "グラフ表示" / "Show graph" button next to
  "保存結果を読込" / "Load saved result" in the 8760 comparison dialog.
  Clicking it:
    1. scans <Project folder>/8760_Comparison/*.json for every archive
       matching schema AZRAS_8760_COMPARISON_ARCHIVE_V1;
    2. also includes the current in-memory (not yet saved) comparison
       result, if one was just run in this dialog session and isn't
       already among the saved archives;
    3. opens a new window with a metric dropdown (populated from the
       first archive's display_rows metric names -- e.g. 年間暖房負荷
       kWh, 年間冷房負荷 kWh, 年間空調電力 kWh, U値, 有効蓄熱量, etc.)
       and a bar chart showing the selected metric's "alternative" value
       for every saved scenario, one bar per scenario;
    4. each bar is labeled from the scenario's changed part/material/
       thickness (e.g. "roof:Phenolic foam200mm"), falling back to the
       save timestamp when no scenario detail is available (e.g. a
       CSV-only archive).
    Warns instead of opening an empty window if no saved comparison
    exists yet.

Verified: MultiSeriesBarChart renders correctly in a headless Xvfb Tk
session (25 canvas items drawn for a 3-bar test chart, no exceptions).
pyflakes reports zero new issues in module2/app.py or ui/graph.py (all
pre-existing warnings in module2/app.py are unrelated to this change).

Files changed:
- ui/graph.py (added MultiSeriesBarChart)
- module2/app.py (import, new button, _scenario_label + show_comparison_graph)
