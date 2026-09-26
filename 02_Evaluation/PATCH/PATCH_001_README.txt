PATCH_001 — AZRAS Evaluation v2.2.0 baseline (patch numbering reset)

This is the first patch of the v2.2.0 baseline. Prior history (PATCH_197
through PATCH_216, plus the fixes issued earlier in this same audit as
"PATCH_217" under the old numbering) is preserved for reference under
PATCH/archive_pre_v2.2.0/ and is not deleted, but is no longer the
active patch ledger.

What changed to reach this baseline (previously issued as PATCH_217
under the old numbering, now folded into this single v2.2.0 baseline):
- module7/app.py: fixed a NameError — "project_currency" was referenced
  in build() without ever being assigned, crashing Module 7 every time
  it opened or the language was switched, leaving results blank.
- module4/app.py, module6/app.py: fixed the language-selector combobox
  rendering blank. The <<ComboboxSelected>> handler referenced only
  widget.current() instead of the StringVar itself, so the StringVar was
  garbage-collected as soon as build() returned, unsetting the
  underlying Tcl variable. Handlers now reference the StringVar directly
  (lang.get()), matching the already-correct pattern used in Module 3/7.
- module3/app.py: fixed 対象部位・設備 (component names) staying in
  whichever language was active when the scenario was last generated,
  even after switching the UI language. show_result() now re-derives the
  display name from each event's language-independent "component_key"
  via component_db, in the CURRENT UI language, instead of showing the
  language baked in at generation time.

Companion checks (ported to AZRAS Planning in this same audit from this
package's existing dev_checks/, and confirmed still relevant here):
- dev_checks/ already contained 6 self-check scripts prior to this
  baseline (module6_module7_integration, discount_rate_sensitivity,
  grid_decarbonization_scenarios, patch138_three_layer_comparison,
  lca_module_crosswalk, future_climate_8760). These remain unchanged and
  should continue to be run before every future patch.

Going forward:
New patches are numbered PATCH_002 onward; each should get its own
PATCH_NNN_README.txt in this folder, and should re-run dev_checks/
(adding a new script when a new bug class is discovered, as was done for
AZRAS Planning's v2.2.0 baseline in this same audit).
