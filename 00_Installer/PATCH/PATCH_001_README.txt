PATCH_001 — AZRAS Installer v2.2.0-aligned baseline (patch numbering reset)

This is the first patch of the v2.2.0-aligned baseline (the Installer's
own version_series is "installer_independent", so its product version
number 5.0.4 is unchanged — only the display strings referencing the
Planning/Evaluation/Compare suite version, and the patch counter, are
updated). Prior history (PATCH_1 through PATCH_034) is preserved for
reference under PATCH/archive_pre_v2.2.0/ and is not deleted, but is no
longer the active patch ledger.

What changed in this baseline:
- azras_launcher.py: updated all on-screen version strings from v2.1.0
  to v2.2.0 (window title, subtitle, "Validated set: Planning 2.2.0 /
  Evaluation 2.2.0 / Compare 2.2.0", bottom label). Removed unused
  imports (os, sys) flagged by pyflakes.
- create_AZRAS_shortcuts.py: updated the shortcut Description string from
  "AZRAS v2.1.0" to "AZRAS v2.2.0". Removed an unused import
  (ctypes.wintypes) flagged by pyflakes.
- README_JA.txt / README_EN.txt / docs/AZRAS_Installation_Guide_{JA,EN}.html:
  updated all v2.1.0 / Planning 1.0.621 / Evaluation 1.0.216 / Compare
  1.1.20 references to v2.2.0 / 2.2.0 / 2.2.0 / 2.2.0 respectively.
- Added dev_checks/language_combobox_liveness_self_check.py (ported from
  the Planning/Evaluation/Compare audit in this same session). Confirmed
  clean.

Going forward:
New patches are numbered PATCH_002 onward; each should get its own
PATCH_NNN_README.txt in this folder. Run
dev_checks/language_combobox_liveness_self_check.py and a plain
`python -m pyflakes` pass across the package before every future patch,
and update the "Validated set" string here whenever
Planning/Evaluation/Compare's own version numbers change.
