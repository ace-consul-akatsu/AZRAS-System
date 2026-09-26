PATCH_217 — three fixes: Module 7 crash, Module 4/6 blank language dropdown, Module 3 stale-language component names

1) Module 7 (module7/app.py) — NameError: project_currency
Problem: build() referenced a variable "project_currency" in the event
timeline column headers, but it was never assigned in that method (only
the helper method _project_currency() existed). This raised a NameError
every time Module 7 opened or the language was switched (both call
build()), crashing the module and leaving the takeoff/cost results blank.
Fix: added "project_currency = self._project_currency()" before it is
first used, matching the working pattern already used in Module 6.

2) Module 4 and Module 6 (module4/app.py, module6/app.py) — blank
language dropdown
Problem: the language selector's StringVar ("lang") was a local variable
inside build(). Its <<ComboboxSelected>> handler referenced only
cb.current(), not the StringVar itself, so nothing kept a Python
reference to "lang" alive after build() returned. CPython immediately
garbage-collected it, and tkinter.StringVar.__del__ unsets the
underlying Tcl variable, leaving the combobox visibly blank even though
its value list and initial value were set correctly. (Module 3 and
Module 7 use the same pattern but reference "lang.get()"/"language_value.get()"
directly inside their handlers, which keeps the variable alive — that is
why only Module 4 and Module 6 showed this symptom.)
Fix: changed both handlers to check lang.get()=="日本語" instead of
cb.current()==1, matching Module 3/7's already-correct pattern. Verified
via headless Tk (Xvfb) that the combobox now correctly displays 日本語/
English after full window initialization.

3) Module 3 (module3/app.py) — 対象部位・設備 shown in the wrong
language after switching UI language
Problem: services/renewal_scenario_engine_v9_2.py bakes each event's
"component" display text into the requested language at the moment
generate_scenario() runs (correct behavior for that function). However,
show_result() displayed e["component"] verbatim. If a scenario was
generated while the UI was in English (or vice versa) and the JSON was
saved, then reopened with the UI in Japanese, the saved English text
stayed on screen until "シナリオ自動生成" was re-run — switching the
language dropdown alone did not retranslate it.
Fix: every event already carries a language-independent "component_key"
(plus two special non-component-db keys: "all_infill", "whole_building").
Added Module3App._component_display_name(event), which looks up the
correct ja/en name from self.component_db (or the small special-case map)
using the CURRENT self.i18n.language, and show_result() now calls this
instead of using the stored text directly. Falls back to the stored
"component" text only if component_key is missing/unrecognized (e.g. a
very old saved JSON), so nothing regresses to a blank cell. Verified
headlessly: a stored English "HVAC Equipment"/"All Infill" event now
displays "空調設備"/"全インフィル" when the UI is set to Japanese, and
back to English when switched, with no need to regenerate the scenario.

Files changed:
- module7/app.py (build() only)
- module4/app.py (language combobox handler only)
- module6/app.py (language combobox handler only)
- module3/app.py (added _component_display_name + show_result column only)
