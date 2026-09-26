AZRAS Installer PATCH 033 (consolidated)

Delivered as a full replacement ZIP (v5.0.4-p033), per the new delivery
method.

Background
- The launcher's "Product launcher was not found" error told the user it
  searches for folders such as "*_v1.0.xxx_corrected", which does not
  match the actual matching logic (a simple startswith prefix match on
  sibling folder names, e.g. "01_AZRAS_Planning_v1.0.621") and does not
  require any "_corrected" suffix. This wording could make a real,
  correctly-named versioned folder look unsupported when it is not.
- The launcher window, README_EN.txt, README_JA.txt, and the two
  installation-guide HTML files still said "v2.0.0" and listed a stale
  "Validated set: Planning 1.0.614 / Evaluation 1.0.215 / Compare 1.1.19"
  -- Planning had already moved well past 1.0.614.

Behavior
1. azras_launcher.py
   - Window title, subtitle, and bottom label changed from v2.0.0 to
     v2.1.0.
   - "Validated set" label updated to Planning 1.0.621 / Evaluation
     1.0.216 / Compare 1.1.20.
   - The "Product launcher was not found" message no longer references
     a non-existent "_corrected" suffix; it now describes the actual
     startswith-based sibling-folder search, using the real folder_prefix
     in its example.
2. create_AZRAS_shortcuts.py: shortcut Description changed from
   "AZRAS v2.0.0" to "AZRAS v2.1.0".
3. README_EN.txt / README_JA.txt: Installer version and validated
   release set updated to p033 / Planning 1.0.621 / Evaluation 1.0.216 /
   Compare 1.1.20; "v2.0.0" wording changed to "v2.1.0".
4. docs/AZRAS_Installation_Guide_EN.html /
   docs/AZRAS_Installation_Guide_JA.html: heading changed from v2.0.0 to
   v2.1.0.

Verified
- python -m py_compile passes for azras_launcher.py, azras_installer.py,
  create_AZRAS_shortcuts.py.
- VERSION.json parses as valid JSON.
- No remaining "v2.0.0" or "1.0.614" text in the Installer payload.

Not changed in this patch
- resolve_product()'s actual folder-matching logic (startswith + one
  extra wrapper directory) is unchanged -- it already accepts a
  versioned sibling folder such as "01_AZRAS_Planning_v1.0.621". If the
  reported "Product launcher was not found" error still occurs after
  this update, the AZRAS.exe / shortcut in use may be an older build
  compiled before this resolver existed; that would need to be rebuilt
  from current source, which is outside what a text-only PATCH can fix.
