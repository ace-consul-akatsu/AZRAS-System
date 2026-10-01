## v2.2.0 PATCH_054 — 2026-10-01 UTC
- Module 5 地域単価表: the save folder can be chosen. Before, the table was always saved in `<Project JSON folder set in Module 0>/Regional_Unit_Price_Tables` (AppData setting), which could be a different place from the folder the Project was opened from (e.g. Dropbox\…\260923_JSON instead of C:\AZRAS_v2.2.0\JSON).
- 「AI採用単価を地域単価表へ登録」 now first shows the folder: 「この保存先で登録」 / 「変更…」 / 「既定に戻す」 / 「キャンセル」. The choice is remembered (`storage_settings.json` → `regional_price_table_directory`, used exactly as chosen) and used by 適用 / 登録 / 内容を確認.
- The panel shows the current folder (指定 / 既定) with a new 「地域単価表の保存先を変更」 button; 適用 explains how to point to another folder when no table is found. The Project JSON folder setting is not changed.
- Added dev_checks/patch_054_price_table_folder_self_check.py; the PATCH_052 check answers the new folder dialog.

## v2.2.0 PATCH_053 — 2026-10-01 UTC
- Module 5 代表地域プロファイル: a profile picked from the list (e.g. Japan / Nagoya) jumped back to the automatic one (Japan / Tokyo). Cause: the window's `<FocusIn>` handler re-applied the automatic profile — and its indices — on every focus change while Module 5 was unsaved. A list choice is now a manual choice, kept until the new 「自動選択に戻す」 button, and saved as `location_selection_mode` in the Module 5 snapshot; in automatic mode the profile is re-applied only when the Project or its location changes (typed indices are no longer reset by focus changes).
- Automatic selection: nearest profile in the Project's country by `common.latitude/longitude` (Kasugai → Nagoya, about 12 km). Within 100 km it is a regional match (no warning; regional unit-price table allowed without asking); farther, or outside the country when the country has no profile, the header shows the distance and a warning. Without coordinates a romanised prefecture ("Aichi-ken") now also resolves; otherwise the older fallbacks are unchanged. Built-in city profiles got coordinates; indices and prices unchanged.
- Profile list built from disk: `data/regional_profiles/*.json` (new 「地域プロファイル追加」 dialog) and `data/regional_cost/*.json` datasets with a new `region_key`. Built-in profiles cannot be replaced. New `services/regional_profile_catalog.py`; Module 2 and the automatic Module 5 recalculation load the same catalog.
- Added dev_checks/patch_053_regional_profile_selection_self_check.py.

## v2.2.0 PATCH_052 — 2026-10-01 UTC
- Module 5: new 地域単価表 (regional unit-price table) panel — apply / register adopted AI prices / view / remove. One standalone versioned table per region in `<JSON folder>/Regional_Unit_Price_Tables/` (file `AZRAS_UNIT_PRICE_TABLE_<region>_<YYYY-MM>.json`), outside every Project folder. Matching by item + spec + unit + scale class; unregistered items only are sent to AI research; registered prices are never overwritten.
- Engine: price_basis_fingerprint records the table reference; new basis tokens regional_unit_price_table / regional_unit_price_table_with_ai_items / mixed_regional_unit_price_table_and_regional_database. Table prices display as provisional (yellow).
- Module 1: the 図面追加 (append drawings) button was removed; a changed drawing set is reloaded whole with PDF/ZIP読込.
- Added dev_checks/patch_052_regional_unit_price_table_self_check.py.

## v2.2.0 PATCH_051 — 2026-09-30 UTC
- Drawing analysis: per-dwelling / per-room area notes (m2/戸, m2/室, m2 x n戸) and finish-area notes (天井と床面積 …) are no longer taken as the building's floor area; if no written area is plausible for the plan, footprint x storeys is used. AZRAS terrace house: 37.6 m2 -> 245.1 m2. Other sample PDFs unchanged.
- Added dev_checks/per_unit_finish_area_not_gross_floor_area_self_check.py.

## v2.2.0 PATCH_050 — 2026-09-30 UTC
- Module 5 earthwork (RC): reads the ground-beam length Module 1 measures on the foundation plan (`rc_vector_takeoff.foundation.net_ground_beam_length_m`); the key it read before was never written, so RC projects had no earthwork. Length source recorded.
- 2x6: new `detect_2x6_strip_foundation_plan_vector` measures the foundation plan including internal strips; Module 5 earthwork accepts the Module 1 foundation-geometry shape (it crashed on a scalar `concrete_volume_m3`).
- Module 1 (2x6): slab-on-ground uses the area inside the stems when the plan is resolved; strip-footing concrete included in the provisional foundation rebar.
- Added dev_checks/foundation_earthwork_contract_self_check.py.

## v2.2.0 PATCH_049 — 2026-09-30 UTC
- CSV language: result CSVs follow the UI language at save time. English output unchanged; Japanese output has Japanese headers (lang/csv_ja.json) and translated status codes; numbers untouched; untranslated columns stay in English, never blank. New shared core/csv_export.py.
- Module 1 detailed-quantity CSV: Japanese item / evidence class / basis / source as on the 詳細数量 tab; AZRAS Key column stays English-canonical. English default file name is now `<project>_Detailed_Quantities.csv`.
- Module 5 construction-cost CSV: Japanese headers/status codes and a 工種・品目名 column (Japanese only). Module 10 selected-hour regional CSV and Module 2 8760 comparison CSV headers; the 8760 CSV reload accepts both 指標 and metric.
- Added dev_checks/csv_language_self_check.py. No calculation or Project JSON change.

## v2.2.0 PATCH_048 — 2026-09-24 UTC
- module1/app.py: removed two identical duplicated dict keys ('AZRAS actual sloped roof area', 'Exterior doors'); added dev_checks/duplicate_dict_key_self_check.py (pyflakes misses same-value duplicates).
- dev_checks/pyflakes_undefined_names_self_check.py: FAIL instead of SKIP when pyflakes is missing; FAIL on unparseable files.
- Version single source of truth (VERSION.json): README/NOTICE 2.2.0; removed plain VERSION and unused version_info_AZRAS_Planning_Basic.txt; version_info generated by build_tools/make_version_info.py (old one-line file stopped the PyInstaller build); core/version.py finds VERSION.json in PyInstaller 6 _internal; .spec bundles resources/ and module1 data. Added dev_checks/version_consistency_self_check.py.
- AI request ZIP now includes the Japanese longitudinal-observation protocol (was looked up under a non-existent name); English protocol brought to the same sections; added dev_checks/ai_request_package_resources_self_check.py. Removed obsolete APPLY_LOCATION.txt. v2.2.0 baseline release.

## v2.2.0 PATCH_047 — 2026-09-23 UTC
- module1/app.py: removed two duplicated dictionary keys found by the cross-product audit ('図面' in _CANONICAL_EN_REPLACEMENTS; 'Exterior window glazing' in the EN->JA display table, which made 外壁窓ガラス display as 外部窓ガラス).

## v2.2.0 PATCH_046 — 2026-09-24 UTC
- Module 5 final approximate-cost recheck filenames now explicitly include `FINAL`: step ⑤ saves `YYMMDD_HHMM_AZRAS_AI_APPROX_COST_CHATGPT_FINAL_RECHECK_REQUEST.txt`, and the recheck request requires the final ChatGPT response filename `YYMMDD_HHMM_AZRAS_AI_APPROX_COST_FINAL_<project>_chatgpt.json`.
- Step ⑤/⑥ labels now read ChatGPT final re-check in Japanese/English. Import compatibility remains unchanged; legacy filenames are not hard-rejected.
- Added `dev_checks/patch_046_ai_cost_final_filename_self_check.py`.

## v2.2.0 PATCH_045 — 2026-09-23 UTC
- Module 5 AI Approximate Cost: reviewer-only currency compatibility, explicit rejection guidance for TAKEOFF JSON selected in cost workflow, strengthened step ③ reviewer output contract, and timestamp/address compatibility.
- Added dev_checks/patch_045_ai_cost_reviewer_import_self_check.py.

## 1.0.631 — 2026-09-19 UTC
- module1/app.py _ensure_azras_mandatory_scope_coverage_rows() (PATCH_576): fixed a guard bug ("if method and method!='azras'") that failed to skip injection when construction_method_id was empty/unset, causing AZRAS-Platform-only structural coverage rows (AZRAS internal RC party-wall concrete, AZRAS internal 2x6 partition framing, AZRAS ceiling/1F/2F/roof framing material) to appear — already answered as 0.0 — in Module 1's "不明・図面矛盾への回答" screen on an ordinary non-AZRAS project (reported with screenshots: a 2x6 project with 建築システム=一般建築). The guard now only proceeds when the method is confirmed to be exactly "azras"; any such rows already present in a non-AZRAS project, identified solely by this function's own coverage_gap_required/coverage_gap_key markers, are removed without touching any user-entered data. Added dev_checks/azras_scope_leakage_regression_self_check.py. See PATCH/PATCH_027_README.txt (in Japanese).

## 1.0.630 — 2026-09-18 UTC
- services/project_export_paths.py (_data_root_from_path): fixed a bug where selecting a save folder literally named "JSON" (case-insensitive, with no "Data" ancestor above it — e.g. a user's own Dropbox\...\JSON folder configured via Module 0's "Select Project JSON/CSV folder" dialog) caused a brand-new project's very first save to land one directory ABOVE the folder the user actually selected, instead of inside it. The dead special case ("if the immediate parent folder is named json, jump to its parent") was removed; the "Data" ancestor search that the portable EXE/Data/JSON fallback layout relies on is untouched and still works. Reported directly by the user with screenshots showing one new project ("260918_RC_Rahmen_Sample") landing beside the JSON folder instead of inside it, while two earlier projects that already had their own per-project subfolder saved correctly. Added dev_checks/json_save_folder_regression_self_check.py covering the custom-JSON-folder case, the portable EXE/Data/JSON case, and the already-bundled re-save case. See PATCH/PATCH_026_README.txt (in Japanese).

## 1.0.629 — 2026-09-18 UTC
- module1/app.py and module5/app.py: added a shared AZRAS_AI_STANDARD_RULES_V2_EN header (English canonical, 5 items: a 10-minute response-time target with an interim-report/continue-check fallback that never trades away accuracy for speed; minimum-privilege — no connecting to or logging into closed/authenticated networks, no data beyond the supplied materials and ordinary public web search, no writes/execution on external systems without explicit authorization; sandboxing to the supplied materials and public web only; a human-approval checkpoint before any out-of-scope action; and monitoring/anomaly reporting instead of silently proceeding) and inserted it into every AI-facing request text AZRAS generates: module1 _ai_takeoff_request_text and _ai_takeoff_recheck_request_text; module5 _ai_cost_request_text, _ai_cost_review_request_text and _ai_cost_recheck_request_text. Requested directly by the user, embedded in-body per their own earlier decision (rather than sent as a separate attachment) so it cannot be missed or deprioritized by the responding AI. See PATCH/PATCH_024_README.txt (in Japanese).

## 1.0.628 — 2026-09-18 UTC
- module1/app.py _ai_takeoff_recheck_request_text(): the final drawing-takeoff re-check request no longer resends every collected AI's full takeoff_items for every item. Added _final_recheck_qty_close()/_final_recheck_split_by_agreement() to split items into confirmed_matching_items (a one-line summary, used when the item is already confirmed/manual in Planning and every reporting AI's quantity/unit matches within 0.1% with no unresolved/conflicting status) and items_requiring_review (full per-AI evidence, for everything else) plus new_items_proposed_by_ai for AI-proposed items with no matching local_id. Requested directly by the user after independently diagnosing that the growing length of the recheck request (observed at 9,105 lines on one project) was slowing down AI response time. Added rules 12–13 to the request text stating that confirmed_matching_items is a time-saving summary, not a locked result, and must be re-opened if the AI's own re-check of the drawings finds a conflict.
- module5/app.py _ai_cost_recheck_context(): applied the same idea to the construction-cost ChatGPT re-check request. Added _ai_cost_recheck_needs_full_evidence() and split items into confirmed_supported_items (one-line summary, for cost_item_key/package_key values every reviewer's review_findings marked supports_primary_basis) vs. researched_items_needing_review/independent_reviews (full evidence, kept only for challenges_primary_basis/fills_primary_gap/clarifies_primary_ambiguity/still_unresolved/unrecorded findings); reviewers left with nothing but supported items are dropped from the packet entirely. Added rules 11–12 to the request text with the same not-a-locked-result caveat.
- See PATCH/PATCH_023_README.txt for full background and rationale (in Japanese).

## 1.0.627 — 2026-09-17 UTC
- Removed the separate "基礎" (foundation) row from the 8760-hour insulation/thermal-mass comparison screen (module2/app.py) and renamed the "床・土間" row's label to "床・土間・ベタ基礎" (services/envelope_insulation_model_v1.py COMPONENT_LABELS_JA). The foundation row could never show anything but 未確認/unresolved for any project, since Module 1 never populates a distinct assemblies["foundation"] entry, and for mat-foundation (べた基礎) construction the foundation and the ground-floor slab are the same physical pour, so a separate row was structurally incapable of reflecting a confirmed foundation-bottom-insulation setting. This was requested directly by the user after two prior patches (PATCH_016, PATCH_021) fixed the underlying data-flow but the confusing two-row split remained. Added dev_checks/foundation_row_removed_self_check.py.

## 1.0.626 — 2026-09-17 UTC
- Fixed module2/app.py's 8760-hour insulation/thermal-mass comparison screen: the "床・土間" row's population code only checked floor_saved.get("slab_under_insulation") to decide whether the floor's insulation is confirmed project evidence, so a project using foundation_bottom_insulation ("ベタ基礎底断熱あり") instead of slab_under_insulation ("土間下断熱あり") showed 現状断熱位置 as 未確認 (unresolved) even though that setting is fully confirmed in the floor thermal settings panel. This is the same omission PATCH_016 fixed in environment_engine_v9_1.py's calculation, occurring independently in a different file. Fixed both occurrences to check either flag. Added dev_checks/comparison_floor_position_self_check.py.
- module1/app.py _localize_takeoff_text(): added dictionary entries for further garbled-label gaps found in the field (Branch, Cold-water, Hot-water, condensate drain, drain, structural sheathing, decking, exhaust routes).

## 1.0.625 — 2026-09-17 UTC
- Strengthened the AZRAS AI START instruction text generated by the request-package export (module1/app.py) for EVERY AI provider, after a Gemini submission for 260916_AZRAS_Sample returned a simplified, non-compliant response (own JSON shape, missing mandatory takeoff_items coverage, no calculation_ledger/evidence). Added an explicit, provider-neutral list of previously-seen failure modes (simplified summary instead of full takeoff_items, non-standard JSON shape, guessed/rounded quantities instead of drawing-derived ones), restated the hard output contract more forcefully, and added an 8-item pre-send self-check checklist the responding AI is asked to verify against its own draft before sending. The identity section remains generic (no provider is hardcoded), since this same text is sent to whichever AI the user targets. Added dev_checks/azras_ai_start_template_self_check.py to guard against this template silently regressing or a future edit hardcoding one provider's identity into the shared text.

## 1.0.624 — 2026-09-17 UTC
- Added resources/ai_takeoff_contract/AZRAS_AI_START_GEMINI_EMPHASIS_v1.txt: a Gemini-targeted variant of the AZRAS AI START instruction text, written after a Gemini submission for 260916_AZRAS_Sample returned a simplified, non-compliant response (own JSON shape, missing mandatory takeoff_items coverage, no calculation_ledger/evidence). Adds an explicit list of previously-seen Gemini failure modes and an 8-item pre-send self-check checklist. Not yet wired into the automatic request-package generator (module1/app.py); intended for manual use in place of the standard START.txt when specifically targeting Gemini.

## 1.0.623 — 2026-09-16 UTC
- Fixed module1/app.py _localize_takeoff_text(): the Japanese-mode phrase substitution used a case-sensitive, non-word-boundary str.replace() loop, so freely-worded item names imported from external AI-review data (e.g. an AZRAS_AI_TAKEOFF JSON import) displayed as a garbled English/Japanese mashup (e.g. "Electrical 配線 / 電線管 / circuiting"), including stray plural "s" suffixes glued onto translated Japanese words (e.g. "幹線s"). Replaced with a case-insensitive, word-boundary-aware regex substitution and added a suffix-stripping pass, plus dictionary entries for the specific missing words found in the field. Added dev_checks/garbled_mixed_language_label_self_check.py to guard against regressing to the old substitution mechanism.

## 1.0.622 — 2026-09-16 UTC
- Fixed a regression of PATCH_629 (2026-09-15): _screen_review_structured_decision() (added after PATCH_629) stored compound-answer values with plain float(raw) and never called _round_half_up(), silently reintroducing round-half-to-even/floating-point rounding error for the "RC/2×6外壁の内訳値" exterior-wall-split answer. The single-value "承認値" path was unaffected (different function). Routed the compound path through _round_half_up() as well.
- Added dev_checks/round_half_up_regression_self_check.py: source-level check that _screen_review_structured_decision() still calls _round_half_up(), plus a behavioral check of the known 2.005->2.01 / 0.125->0.13 edge cases, verified to fail against the pre-fix code and pass against the fixed code.

## 1.0.621 — 2026-09-16 UTC
- Fixed environment_engine_v9_1.py: the ground U-value calculation had no branch reading floor_thermal_settings.foundation_bottom_insulation ("ベタ基礎底断熱あり"). Checking that box alone (without also checking "土間下断熱あり") caused the user's entered thickness/conductivity to be silently ignored, fell through to a Module 1 drawing-assembly fallback, and mislabeled the result as slab_under_insulation=true in floor_thermal_breakdown even though floor_thermal_settings correctly recorded it as false. Added a dedicated foundation_bottom_insulation branch using the user's own values, reported under its own ground_insulation_source="floor_thermal_foundation_bottom".
- Fixed module2/app.py 8760-hour insulation/thermal-mass comparison screen (PATCH_402): a comparison row's 比較断熱位置 defaulted to "その他" (mass_coupling factor 0.50) whenever Module 1 had not resolved insulation_position, while the baseline run always applies full mass coupling (1.00, equivalent to "exterior") since it never applies any scenario override. Checking a wall/RC-wall/slab comparison row therefore silently halved that component's active thermal mass regardless of the actual thickness change being tested, which could swing annual heating/cooling totals in the wrong direction relative to the insulation change alone. Defaulted the unresolved case to "exterior" instead, matching the baseline's implicit assumption.
- module2/app.py: made "ベタ基礎底断熱あり" and "土間下断熱あり" mutually exclusive checkboxes (previously both could be checked at once with only one silently taking effect), and changed the shared thickness-entry label from the fixed "土間下断熱厚" to a position-neutral label.

## 1.0.620 — 2026-09-10 UTC
- Fixed independent-AI JSON collection for vendor transport differences observed with Gemini and Meta AI.
- Added conservative one-level unwrapping of vendor/browser envelopes when they contain a recognizable AZRAS takeoff object with non-empty takeoff_items and AZRAS identity/analysis signals.
- Changed required_filename vs response_timestamp minute mismatches from a pre-import exception into recorded contract noncompliance, so the response can still be collected as evidence for later recheck/final determination.
- Identity mismatches remain hard failures; no quantities are fabricated or silently promoted.

## 1.0.619 — 2026-09-10 UTC
- Removed active-runtime compatibility for retired `AI_Takeoff` / `AI_Evolution` storage folders.
- Project/R1 is now the sole AI takeoff storage root; no fallback reads or writes to retired storage are performed.
- Renamed active round metadata to `ai_takeoff_round` / `ai_takeoff_response_index`; old AI_Evolution metadata is removed when a new R1 request is created.
- Building System changes purge R1 evidence for the previous system.
- R2 remains future-only.

## 1.0.618 — 2026-09-10 UTC
- Replaced the user-facing AI_Takeoff / AI_Evolution Current storage layout with the developer-approved R1 four-stage workflow directly under each Project folder.
- AI Takeoff start now creates R1/01_Request for Estimate, 02_AI response, 03_Request for Recheck, and 04_Final determination at the same time.
- R2 is explicitly future-only and is not created.
- Independent AI responses are archived to 02_AI response; re-check requests to 03_Request for Recheck; exact formal imported/human final JSON to 04_Final determination.
- New requests no longer create legacy AI_Takeoff or AI_Evolution folders. Existing legacy folders are not automatically deleted.

## 1.0.617 — 2026-09-10 UTC
- Added `AI_Evolution/Current/Send_to_AI` as the single unambiguous attachment folder for every AI.
- The folder contains only the registered drawing PDF/ZIP files, the current request package ZIP, and the current START TXT.
- AZRAS-side MANIFEST, REQUEST_CURRENT, Protocol, Schema, and Template files remain outside the send folder under `Current`.
- Updated the AI Takeoff start window to display the Send_to_AI path and instruct the user to send every file in that folder.
- Preserved the existing independent-AI, Current-only, no-peer-answer, and drawing SHA-256 contracts.

## 1.0.616 — 2026-09-10 UTC
- Fixed the real-project AI TAKEOFF REQUEST canonical boundary: legacy/mixed canonical_* values are no longer trusted verbatim and all outgoing machine-readable fields pass through the hard English gate.
- Added deterministic English mappings for the current AZRAS sample rows that previously emitted migration placeholders. Source-language evidence remains only under source_text_original.
- Fixed semantic duplicate suppression so exterior-window and exterior-door aliases are detected from both canonical and original row wording. In the verified sample, local_id 26 is suppressed as a duplicate of 2 and local_id 27 as a duplicate of 3.
- Verified against 260910_AZRAS_Sample: outgoing worklist 31 rows = confirmed 1 + estimated 23 + unresolved 7; two semantic duplicates suppressed; zero Japanese-script residuals and zero migration placeholders outside source_text_original.

## 1.0.615 — 2026-09-10 UTC
- Simplified the AI Takeoff start window: removed the long on-screen request body, added compact Project > AI_Takeoff location/file guidance, retained short-message copy and a fallback full-request copy button.
- The saved canonical REQUEST TXT and Current package remain authoritative; no AI contract/schema/calculation logic changed.

# AZRAS Planning v1.0.605 / PATCH 605

- Audited active Planning UI for Japanese/English mixing.
- Localized remaining hard-coded Module 1 document-status and validation messages.
- Localized manual quantity-edit unit choices while preserving stored/source units.
- Recovered the AI fixed-observation protocol from a corrupted overlong ZIP filename and restored its intended UTF-8 filename.
- No approved quantity formula, Building System authority rule, AI current-only retention rule, or Cost Provider calculation logic changed.

## 1.0.602
- First correction from the 00→03 full-system audit.
- Removed active use of the legacy chronological AI review-history path.
- Same-provider row claims now replace the provider prior claim even when the source filename changes.
- Current provider snapshots remain the canonical AI state; UI summaries read current provider state instead of old history events.
- Normal retention cleanup removes legacy chronological AI-review events from Project quantity_takeoff.
- Normalized VERSION.json metadata from stale PATCH/schema 584 to 601 and removed the obsolete automatic Human Review Excel-history feature claim.
- Normalized the formal public product name to AZRAS Planning while retaining historical source-folder compatibility.
- Rechecked PATCH 596-600 critical regression invariants.

## 1.0.600
- Performed a comprehensive regression audit at the 600 milestone.
- Audited all 76 Python source files: all compiled successfully.
- Re-verified AI provider canonicalization, AI_Evolution Current-only storage, no Responses/R* recreation, exterior-wall two-answer review, omitted-scope continuity, carried_gap_keys scope safety, transactional Module 1 rebuild, AI-response viewer, saved-M1 viewer, building-system-change AI purge, and construction-selection lock.
- Found and fixed two retention-policy regressions:
  1. `_drawing_review_issue_rows()` still read the obsolete historical `decision_ledger`.
  2. Formal Human Review still automatically wrote dated HUMAN_REVIEW_FINAL JSON and Excel history files.
- Human Review is now current-state-only: current approved values are saved in Project JSON, historical human-answer ledgers/files are not automatically retained, and review Excel is created only by explicit user export.
- Updated Human Review success/UI wording so it no longer claims that audit JSON/Excel history was created.
- Existing user-saved current values and current imported AI snapshots remain subject to PATCH 598 retention rules.
- Regression checked across PATCH 594-599 plus the wider 600-milestone audit matrix.

## 1.0.599
- Fixed PDF registration / Drawing Analysis changing an explicitly selected Building System.
- User selection is now authoritative for all systems, not only AZRAS Platform.
- Building System, Structure and Method selections are persisted immediately when explicitly selected.
- PDF structure recognition is descriptive evidence only and cannot overwrite an explicit construction selection.
- Drawing registration now persists the complete construction selection in `_input_snapshot`, not only `structure_type`.
- Analysis captures a construction-selection lock before rebuild, restores it before profile resolution, and restores it again before final save/commit.
- The same lock behavior was regression-tested for AZRAS Platform, General/Steel, and General/RC cases.
- Regression checked with PATCH 594-598 critical behavior.

## 1.0.598
- Replaced historical human-review retention with current-state-only retention.
- Human `decision_ledger`, old HUMAN_REVIEW source JSON/Excel references, previous/manual-original values, and other human-answer history are removed from active Project JSON.
- Current user/designer-approved values already saved in Project JSON remain as active state; user-added/manual quantity blocks are retained.
- Current imported AI responses remain, one current snapshot per canonical provider.
- When Building System changes (General Building <-> AZRAS Platform), all imported AI state for the old system is deleted from the active Project state, including provider snapshots, FINAL AI review state, mirrored AI review data, and AI_Evolution/Current working cache.
- External/source JSON files on disk are not deleted.
- Existing Project JSONs are migrated to this retention policy when Module 1 opens and on subsequent saves.
- Regression checked with PATCH 593-597 and the exact current-project retention conditions.

## 1.0.597
- Reopen prior human-reviewed items when a newer ChatGPT FINAL reports conflict/unresolved.
- Old human answers remain audit history but no longer suppress newer conflicts.
- RC/2x6 exterior-wall allocation remains a two-value compound human-review question.
- Regression checked through the previous five PATCH range.

## 1.0.596
- Fixed `name 'carried_gap_keys' is not defined` during ChatGPT FINAL JSON import.
- Root cause: PATCH 595 inserted the omitted-scope continuity call into `_stage_ai_takeoff_payload()` (first-round collection) instead of `_apply_ai_takeoff_final_review()`, while the FINAL summary referenced `carried_gap_keys`.
- Removed the misplaced call from first-round staging.
- The omitted-scope continuity guard now runs only inside FINAL-review application, after FINAL rows are processed and before the summary is created.
- Regression checked with PATCH 591-595 critical behavior and the exact variable-scope failure condition.

## 1.0.595
- Fixed disappearance of omitted-scope audit questions after importing an incomplete ChatGPT FINAL review.
- Independent-AI `local_id:null / add_new` scope findings remain evidence only, but a FINAL JSON may no longer silently erase them by omission.
- Added normalized omitted-scope continuity keys for reinforcement, roof waterproofing, electrical lighting/receptacles/wiring/panels, HVAC equipment/ventilation/distribution, plumbing/gas, and fire protection.
- If a FINAL JSON does not address a previously discovered physical-scope gap, AZRAS creates one unresolved audit row and keeps it in Human Review rather than treating absence as resolution.
- Existing numeric/estimated rows resolved by the current analysis are not forced back to unresolved; this guard only prevents silent scope disappearance.
- Regression checked with PATCH 590-594 critical behavior.

## 1.0.594
- Changed Drawing Analysis / Quantity Calculation full rebuild to a transactional replacement model.
- The last committed Module 1 result remains visible and recoverable while a replacement analysis is running.
- The in-memory working project is scrubbed for clean analysis, but a full pre-run Project/Module 1 snapshot is retained until successful Project JSON autosave.
- On missing drawings, structure-gate cancellation, analysis failure, or autosave failure, the previous committed Module 1 state is restored.
- A new result becomes authoritative only after `_save_result_to_project()` succeeds.
- Added `保存済みM1結果確認 / View Saved M1` to inspect the Module 1 body stored in Project JSON even when the active analysis result is unavailable.
- Regression checked together with the previous five PATCHes (589-593) and related critical invariants.

## 1.0.593
- Added `収集済みAI回答確認 / View Collected AI` beside AI JSON collection.
- The viewer works even when the Module 1 quantity table/result is blank because it reads the persistent Project JSON AI-provider store directly.
- Shows current provider, source JSON filename, import time, analysis status, item count, and each takeoff item's local_id/status/quantity/unit/item.
- Re-run warning now reports the exact current AI response count/provider names and explains that these are evidence data separate from the Module 1 quantity table.
- Regression checked against the previous five-PATCH range and related critical invariants.

## 1.0.592
- Fixed Human Review formal-apply error `Module 1 result is not available.` caused by an immediate full rebuild clearing `self.result` before the post-apply save.
- Human-approved direct quantities and ADD items are now persisted to Project JSON before rebuild starts.
- Post-apply save no longer assumes that the pre-rebuild Module 1 result still exists.
- Corrected the formal-apply confirmation count to distinguish answered UI items from structured formal decisions.
- Regression-checked current change together with the preceding five-PATCH range/related critical invariants, including provider canonicalization, Current workspace, no Responses recreation, and AZR-0001 two-answer behavior.

## 1.0.591
- Removed the AI_Evolution/Current/Responses subfolder. AI observation JSON files are now stored directly in AI_Evolution/Current.
- Added one centralized `_normalize_ai_evolution_workspace()` policy used by both package generation and AI observation storage, preventing separate code paths from recreating old R*/Responses structures.
- Existing legacy R1/R2/... and Current/Responses folders are automatically removed by the current workspace normalizer.
- Updated operational Module 1 instructions and the AI longitudinal-observation protocol from old Round/Rx/Responses terminology to Current.
- Added a cross-patch regression matrix verifying critical behavior from PATCH 588, 589, 590 and 591 together.

## 1.0.590
- Fixed human-review regression where AZR-0001 exterior-wall system allocation was rendered as one generic answer.
- Compound-field detection now inspects canonical_item, item, source_text_original, calculation basis, unresolved reason and related row metadata instead of allowing a canonical migration placeholder to mask the actual question.
- AZR-0001 now renders two independent visible rows/answers: RC exterior wall area and 2x6 exterior wall area.
- Formal apply is blocked until both values are answered.
- Human-review audit target_item now falls back to the actual row item when canonical_item is only an unresolved-migration placeholder.

## 1.0.589
- AI_Evolution no longer creates R1/R2/R3/... folders on repeated analysis/request generation.
- The active workspace is now `AI_Evolution/Current` and is replaced on a new current run.
- Legacy `R<number>` folders are removed automatically when the next AI evolution package is prepared.
- Project JSON keeps only the current AI evolution state; `ai_evolution_rounds` history is removed.
- AI observation files use one `CURRENT_<provider>` record per provider and replace the previous current observation.

## 1.0.588
- AI takeoff collection now counts one current response per actual AI provider.
- Legacy aliases such as `ChatGPT`/`chatgpt`, `Claude (Anthropic)`/`claude`, and `Meta AI - Muse Spark 1.1`/`meta` are collapsed.
- When the same AI is imported again, its previous response is replaced; old same-provider answers are not retained in the active Project JSON.
- Existing legacy 7-entry stores migrate automatically to 4 providers where applicable.

## 1.0.587
- Independent AI takeoff collection now safely accepts a missing root `schema` only when the payload is strongly recognizable as the current AZRAS takeoff structure.
- Such payloads are always stored as `noncompliant_evidence_only`; AZRAS does not silently repair or formally adopt them.
- A conflicting/non-AZRAS schema is still rejected.
- Regression verified against the Meta response `260909-0331-AZRAS-AI-Takeoff-260908-AZRAS-Sample-Meta.json` (33/33 local-id overlap).

## 1.0.586
- Module 5 construction-cost AI request windows now show and copy a direct chat launch instruction, so attached TXT instructions are not relied on as executable commands.
- Applied to primary ChatGPT research, independent-AI review, and ChatGPT re-check stages.
- Added persistent on-screen guidance in the construction-cost panel.

## 1.0.584 / PATCH 584
- Added a direct AI-chat activation prompt for Meta AI and other services that treat attached TXT files as reference data instead of executable instructions.
- The activation prompt must be pasted into the AI chat body after attaching the common drawings/request package; START TXT remains in the package for auditability but is no longer the sole execution trigger.
- The direct prompt enforces JSON-only AZRAS_AI_TAKEOFF output, mandatory local_id coverage, unresolved-row encoding, actual responder identity, and UTC YYMMDD_HHMM filename consistency.
- Preserved the identical independent evidence package across AI providers; no prior/peer AI response is added to the activation prompt.

## 1.0.580 / PATCH 580
- Human-review questions now support multiple independent answer fields.
- AZRAS exterior-wall allocation displays separate RC exterior wall area and 2x6 exterior wall area inputs instead of forcing two values into one instruction/quantity field.
- Added generic `human_review_fields` metadata support for future compound questions.
- Legacy instruction-text parsing remains as backward-compatible fallback only.


## v1.0.579 / PATCH 579
- Added AZRAS in-app human-review UI for Unknown / Drawing Conflict items.
- Human answers now generate an internal HUMAN_REVIEW_FINAL audit JSON and are formally applied without requiring Excel/JSON editing or a ChatGPT round-trip.
- Review Excel is retained as an optional external-designer handoff only.
- Added direct user/designer additional-item entry in the same screen.
- Added formal human parameter for AZRAS RC/2x6 exterior-wall area allocation and rebuild consumption.
- Normalized common Japanese area/volume unit symbols for screen-entered direct quantities.
- Fixed ADD-row creation when quantity_takeoff.rows is initially empty.
## 1.0.576 / PATCH 576
- Added mandatory AZRAS scope coverage register for quantities missing from both software and AI review.
- Mandatory gaps appear as unresolved Module 1 rows and at the bottom of Drawing Review Excel v1.4.
- Human-confirmed gap quantities become eligible for Module 5 quantity/cost linkage.

# 1.0.573 — PATCH 573
- Added actual-responder AI identity hard gate and canonical Meta AI token `meta`.
- Added mandatory root `required_filename` and generic-browser filename fallback for services such as Gemini that cannot control download names.
- Rejects claimed AZRAS attachment filenames whose AI identity conflicts with `analysis.ai_reviewer` / `required_filename`.
- Fixed elevation opening classification to associate door labels spatially with repeated area labels; verified current AZRAS sample as windows 55.74 m² and exterior doors 6.33 m².
- Added false-100% completeness checks for omitted electrical and RC reinforcement scopes.

# v1.0.567
- Hardened AI Takeoff output contract: JSON file only; no prose summaries, clarification questions or next-step offers.
- Added explicit fallback rule: unresolved items must still be returned inside JSON.
- Added AZRAS_AI_TAKEOFF_RESPONSE_TEMPLATE_v1.0.json to the AI request package.
- UI now warns that prose responses are invalid and must not be used as formal AI JSON.
- No quantity/calculation logic changes.

# v1.0.566
- AI解析の案内 now explicitly states that the entire R1/R2/R3 folder must NOT be sent to an AI.
- Send only the current Round request package ZIP plus drawing PDFs/ZIPs as separate attachments.
- Responses, previous-round answers and peer-AI answers must remain AZRAS-side to preserve independent longitudinal comparison.
- User Guide updated with the same operating rule.
- No calculation/quantity logic changes.

# v1.0.565
- Fixed AI Takeoff guide crash introduced by PATCH 563/564.
- Escaped literal JSON braces inside the f-string returned by _ai_takeoff_request_text().
- AI解析の案内 can now open normally; no quantity/calculation logic changed.

# v1.0.564
- AI longitudinal request ZIP no longer embeds drawing PDFs/ZIPs.
- Drawings are sent separately to each AI exactly as in the existing AZRAS workflow.
- Manifest still records filename, size and SHA-256 for every registered drawing.
- Replay rule now requires the unchanged request ZIP plus separately attached drawings matching the recorded SHA-256 values.
- No quantity/calculation/formal-adoption changes.

# v1.0.563
- Added AZRAS AI longitudinal observation package (AI_Evolution) without changing formal quantity adoption.
- AI Takeoff start creates a reproducible ZIP containing the exact request, fixed v1.1 protocol, AI-origin metadata schema, manifest, and registered PDFs/ZIPs when accessible.
- Manifest records SHA-256 for request and drawing set; unchanged ZIP can be resent later for identical-condition observation.
- Independent AI responses are normalized into separate AZRAS_AI_ANSWER_OBSERVATION v1.1 records during JSON collection.
- previous/peer comparison and human final fields remain AZRAS-side only; responding AI never receives prior answers.
- No quantity/calculation/English Canonical adoption changes.

# v1.0.562
- Japanese Module 1 button label changed from 「不明・図面矛盾Excel作成」 to 「不明・図面矛盾Excel再作成」.
- Clarifies that the normal workflow auto-generates the review workbook after formal AI JSON processing; this button is for manual regeneration.
- No quantity/calculation/English Canonical changes.

# v1.0.561
- HUMAN_REVIEW_FINAL is a hard final-authority gate over older AI FINAL unresolved/conflict decisions.
- Data-quality/save gates preserve human-reviewed recalculated quantities as confirmed.
- AZRAS Platform identity is synchronized across Project common, detailed_configuration and Module 1 result; stale active general wood_frame/2x4 identity is disabled.
- Intended for clean new-Project AZRAS validation after legacy JSON removal.

# v1.0.560
- HUMAN_REVIEW_FINAL-derived quantities are normalized as confirmed recalculated rows, not provisional-general-specification rows.
- AZRAS internal RC wall now records approved opening geometry and no longer carries the provisional opening-height label after human review.
- Human-reviewed rows are excluded from the provisional-spec editor and Table 1 unresolved flow.
- Generic normalization applies to future HUMAN_REVIEW_FINAL parameter rows as well.
- No change to the 25.461 m3 calculation formula/result itself.

# v1.0.559
- HUMAN_REVIEW_FINAL import now automatically triggers required recalculation.
- Window decisions can make elevation drawings authoritative and recalculate total/orientation from registered elevation evidence.
- Approved APW 430 / glazing construction is carried into Opening Master and downstream performance without inventing a U-value.
- Targeted window recalculation preserves unrelated AI-final evidence; full rebuild is fallback only.

# v1.0.558
- Drawing Review Excel asks root-cause component rows instead of aggregate/total rows.
- Aggregate conflicts trace referenced local_id/component rows; resolved HUMAN_REVIEW_FINAL targets are not re-asked.
- Specific Japanese questions added for internal RC/CB120 and reinforcement issues.
- No quantity/calculation logic changes.

# v1.0.557
- Fixed Drawing Review Excel crash introduced in v1.0.556: drawing_file/page/drawing_no are resolved before Japanese M-P template generation.
- No quantity/calculation, AI-resolution, or English Canonical changes.

# v1.0.556
- Japanese Drawing Review Excel M-P columns are now generated from structured issue data using Japanese templates, not translated from AI English prose.
- English Canonical / AI evidence remain preserved in Project JSON.
- No quantity/calculation changes.

# v1.0.555
- Japanese Drawing Review Excel: localized all human-readable review columns; preserved Canonical keys, filenames, units, numeric values and user-entered instructions.
- No quantity/calculation changes.

# v1.0.554
- Japanese Drawing Review Excel: localize AI-derived free-text fields at export time; English Canonical remains unchanged.
- No quantity/calculation changes.

# v1.0.553
- Restored/ensured Windows launcher BAT: run_AZRAS_Planning_Basic_without_build.bat.
- Launcher connectivity only; no quantity, calculation, or i18n logic changes from v1.0.552.

# v1.0.552
- Formalized the Drawing Analysis external human-review workflow.
- Added in-app export of only Unknown / Drawing Conflict issues to a language-matched Excel workbook.
- Excel contains Review_List / Instructions / Lists and uses timestamped project AI_Takeoff storage.
- AI Final import now offers review-Excel creation when unresolved/conflicting issues remain.
- Human-resolved items are not repeatedly re-exported while original audit evidence is retained.
- Existing HUMAN_REVIEW_FINAL import remains the formal path back into Planning; human parameters survive re-analysis.
- No unrelated quantity or building-performance logic changed.

# v1.0.551
- Added formal ChatGPT human-review FINAL JSON import path for designer/user answers from the Drawing Review Excel.
- Human geometry decisions are stored as named parameters and survive future PDF re-analysis.
- AZRAS internal RC opening geometry can now use approved count/width/height instead of the provisional 2.000m opening height.
- AZRAS timber framing general specification approval is persisted separately from quantity certainty.
- No unrelated quantity logic changed.

# v1.0.550
- Japanese Drawing Analysis: remaining English fragments in specified rows and Source/参照元 cells localized.
- i18n/display only; no quantity/calculation changes.

# AZRAS Planning v1.0.549 — PATCH 549

- Presentation/i18n-only correction from v1.0.548.
- Localized residual English text in Japanese Drawing Analysis rows, including the user-reported 08, 10–14, 16, 24, 26–30 range.
- Fixed Module 2 English result rows 06/07 so peak datetimes use `YYYY-MM-DD HH:MM` instead of Japanese month/day notation.
- No quantity formulas, quantity adoption, stair quantity, or RC/CB120 quantity logic changed.

# AZRAS Planning v1.0.548 — PATCH 548

- Language/i18n-only follow-up to PATCH 547; no quantity, adoption, stair, RC, or CB120 calculation changes.
- Re-normalizes existing persisted `canonical_*` values instead of trusting legacy mixed Japanese/English Canonical fields.
- Adds deterministic migration mappings for historical mixed strings such as `図 faces`, `施工 area`, `実斜 area`, and related partially translated evidence/formula text.
- Preserves drawing-native/source wording in `source_text_original` while enforcing English-only machine Canonical fields.
- Regression audit against `260906_azars_Sample.json`: 201 contaminated canonical strings -> 0 Japanese-script residuals and 0 migration fallbacks.
- Python compile and ZIP integrity checks passed.

# AZRAS Planning v1.0.547 — PATCH 547

- Language/i18n-only correction from approved v1.0.546 baseline; no quantity or calculation-basis change.
- Repaired residual mixed-language artifacts such as `図 faces`, `下 faces`, `施工 area`, `実斜 area`, and `times数` in Module 1 Japanese presentation/generated text.
- Strengthened English Canonical normalization for drawing, installation-area, material-type, designer-set and related generated metadata.
- Preserved original drawing/source-language evidence separately under `source_text_original`.
- Kept Japanese/future languages as presentation layers derived from English Canonical.

# AZRAS Planning v1.0.546 — PATCH 546

- Audited AZRAS timber/infill quantity certainty without changing the approved quantity formulas: framing components and the method-specific total are explicitly `estimated / assumed / yellow` because member sizes and pitches remain provisional.
- Internal-partition gypsum-board quantity now inherits unresolved opening evidence: if one-sided hinge/opening candidates remain, the rational numeric quantity is retained but shown as provisional/yellow instead of confirmed.
- Partition substrate applicable area inherits the same certainty as its finish quantity.
- Provisional partition-stud and ceiling-furring member lengths are explicitly yellow; drawing-derived geometry remains separate from provisional member spacing.
- No new timber member size, pitch, opening dimension, or material quantity was invented in this patch.

# AZRAS Planning v1.0.544 — PATCH 544

- Prevented AZRAS RC concrete summary rows from being counted in addition to their physical detail owners.
- Reinforcement schedule components remain preserved as audit breakdown while one schedule-derived total is the physical/cost owner, eliminating component+total double counting.
- Classified AZRAS roof pitch/projected/sloped geometry as quantity-basis-only; it remains traceable in Detailed quantities but is not a construction-cost owner.
- Module 5 primary cost breakdown omits supporting/intermediate quantity rows; those rows remain available in audit/detail views.

# AZRAS Planning v1.0.543 — PATCH 543

- Cleaned the Module 1 primary drawing-quantity table so only current physical quantity owners and genuine unresolved physical scopes are shown. Audit-only, superseded, duplicate-summary and component-breakdown rows remain available in Detailed quantities.
- Added English Canonical concrete ownership aliases for `Mat foundation concrete` and `AZRAS perimeter RC wall concrete`, preventing the generic `Total concrete` row from competing with current-PDF component owners.
- When current-PDF geometry resolves `AZRAS internal RC wall concrete`, stale unresolved/planning aliases are moved to audit metadata instead of remaining as a second visible physical row.
- Rebuilds a single current `AZRAS total RC concrete` summary and re-applies quantity ownership on Project restore/display for legacy-project compatibility.

# PATCH 542 — Module 1 / Module 5 bilingual quantity display normalization

- Fixed Japanese/English mixed quantity labels in Module 1 presentation.
- Fixed Module 5 English remnants 「正味」「水平投影」 by exact legacy-to-English aliases.
- Fixed Japanese display of `ceiling gypsum board` and AZRAS ceiling gypsum-board variants.
- Preserved English Canonical internal architecture; legacy mixed labels are handled at the display/compatibility boundary.

# PATCH 541 — English Canonical enforcement for multilingual UI

- Module 1 internal item matching now prefers `canonical_item` and canonical English normalization instead of Japanese display strings.
- AZRAS provisional-edit branches and RC aggregation lookup were changed to English Canonical identifiers.
- Module 5 quantity/audit displays now prefer `canonical_item`; Japanese is presentation translation only.
- Project JSON canonical English fields remain the downstream contract; source drawing text may remain in `source_text_original` for traceability.
- No quantity, cost formula, thermal formula, or Project JSON key schema was intentionally changed.

# PATCH 540
- Module 1 quantity tables now route item, calculation-basis, and source text through the bilingual presentation layer in both Japanese and English modes.
- Module 5 quantity/cost audit rows expanded with AZRAS-specific Japanese/English display mappings.
- Stored Project JSON canonical data and calculation logic are unchanged.

## v1.0.538 / PATCH 538
- Module 9 now rebinds Project-owned Data/weather/coefficient paths to the currently active Project before restore, EPW download/status refresh, selection persistence, and regional JSON calculation. This prevents a still-open Module 9 window from writing EPW files into a previously active Project folder after Module 0 switches Projects.
- Module 9 no longer reopens as a blank table when an older/stale base-Project save lost `regional_analysis.additional_locations` while generated independent regional Project JSONs still exist. It reconstructs only files whose `regional_derivation` explicitly points back to the active base Project, then repairs the Module 9 index in the base JSON.
- Module 1 Japanese presentation mapping expanded for current RC-MRF canonical quantity/audit labels. Canonical Project JSON remains English.
- Module 5 now translates Module 1 coverage/audit item names for Japanese presentation instead of rendering raw English Canonical `item` values.

## v1.0.537 / PATCH 537
- Added a Module 1 save gate: if True North Rotation is blank, warn immediately and do not publish/save Module 1 until the user enters a drawing-confirmed value. 0° is accepted only as an explicit value, not as a default.
- Module 5 now fingerprints only cost-relevant Module 1 content. True-north/orientation-only edits no longer force an unnecessary construction-cost recalculation. Quantity, geometry-area, construction-detail, and MEP changes still invalidate Module 5 as before.
- Intended recovery after a north-only correction is now: save Module 1 -> recalculate/save Module 2 -> generate Module 9 regional Projects. Module 5 remains current unless cost-relevant Module 1 data also changed.

## v1.0.536 / PATCH 536

- Prevent unsolicited top-level `Data` / `*_気象情報` folder creation.
- Store Project-owned EPW, weather catalog, and regional coefficient files under `<Project folder>/Data`.
- Opening Module 9 no longer creates weather/coefficient folders; they are created only when data is actually downloaded or explicitly updated.
- Module 2 automatic EPW retrieval now uses the active Project folder instead of `Documents/AZRAS_Platform`.

## v1.0.535 / PATCH 535
- Replaced the shared whole-GFA timber intensity with method-specific component takeoff. 2×6 and AZRAS now calculate exterior timber wall, internal timber wall, upper-floor framing and roof framing independently from their own drawing geometry.
- Current sample provisional totals become approximately 9.415904 m3 for 2×6 and 7.856688 m3 for AZRAS; both remain yellow because framing member schedules are incomplete.
- Added RC internal-partition LGS steel mass when AI/drawing review explicitly resolves the partition as 105 mm LGS. Current sample: approximately 0.305570 t.
- LGS is not inferred from wall thickness alone: absent explicit material-resolution evidence, wood/2×4/LGS remains unresolved.
- Component rows are audit-only; one physical total flows to cost/LCA.

## v1.0.534 / PATCH 534
- Fixed ChatGPT FINAL review semantics: a numeric FINAL correction marked conflicting/adopt is now adopted as a yellow provisional quantity; a conflict/unresolved result with no numeric replacement remains red.
- Existing Project JSONs automatically re-apply stored FINAL review metadata on load, so corrected opening/concrete values do not require re-running AI takeoff.
- Rational provisional-general-specification quantities are classified yellow before broad specification-only/unresolved legacy labels; human-review flags no longer suppress a usable yellow quantity.
- Fixed certainty/data-quality pass ordering so red/yellow/audit state cannot drift after Project restore.
- Superseded opening/rebar/concrete summary rows are neutral audit-only; audit ownership has absolute precedence over legacy provisional compatibility.
- Added single ownership for AZRAS structural timber so the legacy general-timber row and AZRAS timber-infill row are not double-counted.
- Module 5 quantity bridge now consumes yellow structural timber and corrected openings directly; 2x6 provisional foundation/slab rebar 0.9804 t is used instead of a generic fallback.

## v1.0.533 / PATCH 533
- Neutralized superseded legacy opening/concrete/rebar predecessor rows as audit-only when a stronger current-PDF/canonical physical owner exists.
- Prevents duplicate/old red rows from falsely inflating the human-input / unquantified warning.
- Does not auto-resolve genuine conflicts such as AZRAS internal RC wall material identity.


## v1.0.532 / PATCH 532
- Fixed Module 1 certainty classification: a defensible numeric provisional/general-specification calculation is yellow/assumed even when the final designer specification remains unconfirmed.
- Yellow assumed quantities are eligible downstream; genuine conflicts/unreadable/no-rational-quantity rows remain red and blocked.
- Added legacy compatibility in Module 5 quantity eligibility for clearly labelled rational provisional rows.
# PATCH 529 — Regional 8760 CO2 parity repair

- Module 10 regional hourly calculation now calls `services.dynamic_thermal_model_v9.simulate`, the same 8760-hour thermal solver used by Module 2.
- Removed the drift-prone duplicate thermal-balance implementation in `regional_analysis/hourly_comparison_engine.py`.
- Restores Module 2 handling for thermal-mass enable/disable, external-insulation multiplier, night heat release, natural night ventilation, opaque-roof solar gain and global solar shading.
- Added machine-readable `thermal_solver_contract.same_solver_as_module2=true` to regional snapshots.
- Fixed `core/project_store.py` so unresolved facade gross/opaque areas no longer overwrite `exterior_wall_area_m2` with window+door area (62.07 m2). The sample projects now synchronize net exterior wall area to 205.848 m2 from Module 1 opaque-by-orientation geometry.
- Door area is synchronized independently from final facade surfaces (6.33 m2 north for the current samples).
- Regression: synthetic 8760 EPW on 2x6 / AZRAS / RC-MRF produced Module 2 vs Module 10 heating/cooling electricity differences below 0.0001 kWh/year.

# AZRAS Planning v1.0.527 — PATCH 527

- Cross-audited Module 1 → Module 2 → Module 9/10 → Compare thermal/8760 handoff.
- Restored AZRAS exterior RC wall and dwelling-separation RC wall concrete volumes from final Module 1 takeoff.
- Added bilingual RC-frame component bridge, including RC wall, columns, beams, upper/roof slabs and ground slab without candidate/summary double counting.
- Removed legacy Module 1 heat-capacity top-up whenever physical component quantities are available; Module 2 active fractions are now authoritative.
- Prevented `AZRAS total RC concrete` and other summary rows from double-counting Module 1 material thermal capacity.
- Preserved Module 2 night heat release / natural night ventilation / conductance inputs in the actual Module 9/10 regional 8760 ModelConfig.
- Added `thermal_input_contract` to Module 10 snapshots for downstream validation.

# AZRAS Planning v1.0.526 — PATCH 526

- Fixed false CrossReview rejection in `各AI JSON収集`.
- A row-level `peer_review` object is now treated as CrossReview only when it affirmatively states that other-AI claims were reviewed or contains non-empty reviewed claims.
- `agreement` / `critique` commentary alone does not make an otherwise independent AI response a CrossReview.
- Verified against `260905_1810_AZRAS_AI_Takeoff_260905_RC_MRF_claude.json`: accepted as an independent Claude response.
- Kept explicit retired CrossReview detection for `review_type` and `resolution_action: cross_review_existing`.
## v1.0.530 — 2026-09-06
- Fixed downstream concrete quantity ownership so Module 1 generic/profile rows, current-PDF detail rows, and human-readable totals are not added as independent physical quantities.
- AZRAS sample concrete now resolves to the eligible physical owners 61.275 m3 mat foundation + 32.235 m3 perimeter RC wall = 93.510 m3; unresolved internal RC/CB120 wall quantity remains excluded rather than invented.
- Preserves an existing tagged Module 1 reinforcement planning quantity before any concrete-intensity fallback; AZRAS uses 8.4159 t provisional rather than 19.4454 t derived from the former duplicated concrete total.
- RC frame concrete resolves from detail components once (129.419064 m3), excluding summary and pre-opening candidate duplicates.
- 2x6 concrete remains 12.255 m3.
## v1.0.531 — 2026-09-06
- Unified downstream quantity adoption with the Module 1 display rule: confirmed quantities and yellow provisional/assumed numeric quantities are included; red/unknown/spec/audit quantities are excluded.
- Added a stale-Project compatibility guard so an old `blocked_until_resolved` flag cannot silently suppress an explicitly yellow `assumed_yellow` / `assumed` quantity.
- MEP package/detail monetary ownership remains protected against double counting.
- Added a prominent Module 5 result notice that yellow quantities are included and red unquantified items are omitted until human input/recalculation.
## 1.0.568
- Standardized AI takeoff sending as drawing PDF/ZIP + request package ZIP + external START TXT.
- Added strict AZRAS schema/local_id completeness validation and evidence-only noncompliance status.
- Switched AI workflow filenames/timestamps to UTC; filename prefix is YYMMDD_HHMM with no seconds.
## 1.0.569
- Standardized remaining AZRAS-generated operational timestamps and filename stamps to UTC where code still used local system time.
- AI/approx-cost request filename prefixes use UTC `YYMMDD_HHMM` (no seconds).
- Report/output timestamps now explicitly state UTC.
- Removed remaining legacy JST wording from the old takeoff contract path.
- Added AI takeoff dependency/total consistency gate: total RC concrete must reconcile all applicable RC components, and kg/m3 reinforcement estimates must use the reconciled RC total rather than a partial component row.
- Preserved the R3 delivery method: drawing PDF/ZIP + request-package ZIP + START TXT. Meta AI may receive the extracted request-package contents when ZIP reading is unsupported.


## 1.0.570 / PATCH 570
- Verified AI takeoff R3 send artifact generation path.
- Fixed strict UTC validation: the original response_timestamp offset must be +00:00/Z, not merely convertible to UTC.
- Unified AI observation output filename timestamps to UTC `YYMMDD_HHMM` with no seconds.
- Corrected VERSION.json patch/schema metadata to 570.

## 1.0.577
- Added free user/designer ADD-xxxx section to drawing-review Excel, including editable Y notes.
- Added formal Module 1 + cost-link path for HUMAN_REVIEW_FINAL user-added quantities.

## 1.0.581 / PATCH 581
- Closed the in-app human-review persistence gap: HUMAN_REVIEW_FINAL direct quantities are persisted before full drawing rebuilds.
- User/designer ADD scopes are recreated from Project JSON after deterministic PDF analysis, preserving quantity, unit, notes, decision identity/date, and Cost Key.
- Human-confirmed user-added rows can use an explicit Cost Key in Module 5; `クロス張り` maps to `interior_finish`.
- Unmapped user-added physical quantities remain explicit unpriced monetary gaps and are never silently zero-priced.
- Human-review quantity changes mark Module 5 as requiring recalculation; normal Module 1 dependency fingerprinting remains authoritative.

## 1.0.582 / PATCH 582
- Unified structured multi-answer review fields across AZRAS UI and drawing-review Excel.
- Review_List keeps legacy A:Y columns and adds Z:AH Answer 1-3 item/value/unit slots.
- AZR-0001 now exports RC exterior wall area and 2x6 exterior wall area as two independent required answers; legacy single Approved value is intentionally blank.
- Preserved PATCH 581 human-review persistence and cost linkage.

## 1.0.583 / PATCH 583
- Human-review UI now expands compound exterior-wall allocation into two visible rows: `AZR-0001-1 RC exterior wall area` and `AZR-0001-2 2x6 exterior wall area`.
- Each compound quantity can be answered/changed independently; formal apply blocks until all required quantities for the compound issue are supplied.
- New `ADD-xxxx` items are inserted into the left-hand table immediately after Save/Update and remain selectable/editable.
- Previously formalized user-added rows are shown when the review window is reopened and are updated by stable `user_added_issue_id`, preventing duplicate rows when item names/categories are changed.
- Removed the manual External Review Excel button from the normal human-review screen.
- Formal apply now automatically writes a UTC-dated `AZRAS_HUMAN_REVIEW_<project>.xlsx` audit workbook beside the project AI/Human Review files; same-minute saves receive a numeric suffix instead of overwriting history.
- Project JSON remains the single current active state; Excel is audit/history only.
