AZRAS Installer PATCH 034

Cause found: the developer's actual working folders use the new short
naming convention introduced by the new full-replacement-ZIP delivery
method ("01_Planning_621", "02_Evaluation_216", "03_Compare_020"),
which does NOT start with "01_AZRAS_Planning" / "02_AZRAS_Evaluation" /
"03_AZRAS_Compare". The existing prefix search was working correctly;
those folder names were simply never in the set of names it searched
for, so "Product launcher was not found" was the correct result for
that input, not a logic bug.

Behavior
- azras_launcher.py: PRODUCT_SPECS folder_prefixes now also include the
  short form as a recognized alias, alongside the existing
  "0N_AZRAS_<Product>" names:
  - Planning: "01_AZRAS_Planning", "01_AZRAS_Planning_Basic",
    "01_Planning"
  - Evaluation: "02_AZRAS_Evaluation", "02_Evaluation"
  - Compare: "03_AZRAS_Compare", "03_Compare"
- No other resolver logic changed.

Verified
- Reproduced the developer's exact reported folder layout
  (00_Installer_033 / 01_Planning_621 with
  run_AZRAS_Planning_without_build.bat at its root) in an isolated test
  and confirmed resolve_product() now resolves it correctly.
- python -m py_compile passes for azras_launcher.py.

Not changed in this patch
- The "0N_AZRAS_<Product>" canonical names remain fully supported; this
  only adds the short form as an additional alias, it does not replace
  anything.
