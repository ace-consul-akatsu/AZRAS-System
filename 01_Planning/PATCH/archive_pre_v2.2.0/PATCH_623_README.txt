AZRAS Planning PATCH 623

Purpose
- Requested by the developer: use three real project drawing sets (real
  projects A, B and C) as a gap check against AZRAS's current takeoff item-category
  coverage, and add whatever real categories were missing.

What was checked
- Real project A electrical general-spec sheet (E01) and its symbol legend.
- Real project A mechanical general-spec sheet (M01) and its equipment/
  manufacturer table.
- Real project B HVAC general-spec sheet (AC-01) and its duct/damper symbol
  legend.
- Real project C project-overview sheet (A-01).

Findings
1. AI takeoff request instructions (sent to external AI reviewers) already
   covered plumbing and fire-alarm broadly, but did not separately name
   fire-suppression equipment (hydrants, sprinklers, extinguishers) --
   the M01 sheet shows this is its own discipline with its own equipment
   table, distinct from fire-alarm panels/detectors.
2. AZRAS's own built-in legend/symbol counter (Module 1's "Legend Equipment"
   tool) only had 13 electrical/low-voltage categories. The real project
   legends show many more repeated point-symbols outside electrical:
   sanitary fixtures, faucets, fire hydrants/extinguishers, gas equipment,
   chillers, pumps, water heaters, filters, HVAC diffusers/grilles/heat-
   exchange ventilators/dampers/fan-coil-units/VAV-CAV-boxes, plus several
   electrical symbols not previously listed (power distribution board as
   distinct from lighting distribution board, switches, intercoms,
   telephone outlets, grounding, handholes).
   Linear items (duct runs, pipe runs) were deliberately NOT added to this
   tool -- it counts discrete repeated point-symbols; linear quantities are
   a different measurement method and remain the AI-takeoff request's job.

Behavior
1. module1/app.py: the "audit complete scope" AI takeoff instruction now
   lists "fire alarm" and "fire suppression" as two explicit, separate
   items (previously a single combined "fire" line covering only alarm
   equipment).
2. services/legend_equipment_recognition_v9_2_4.py: EQUIPMENT_LABELS grew
   from 13 to 34 categories. All 13 original keys are unchanged (same key,
   same label) so any previously saved symbol library JSON keeps working
   unmodified. 21 new categories were added as pure additions.
3. find_equipment_pages() now also matches plumbing/sanitary/fire/gas/HVAC
   keywords (in addition to the existing electrical keywords), so those
   pages get auto-suggested (starred) too. This only affects which pages
   are pre-selected in the UI; any page can still be picked manually.
4. module1/app.py's _merge_recognized_equipment_into_takeoff(): the
   internal item-name and category-tagging tables were extended to cover
   all 21 new keys (Japanese item names, and correct "electrical
   equipment" / "plumbing equipment" / "fire protection equipment" /
   "MEP equipment" category tagging), so counted quantities for the new
   categories flow into the takeoff with a real name instead of falling
   back to the generic "設備機器 (Other)" label.

Verified
- python -m py_compile passes for module1/app.py and
  services/legend_equipment_recognition_v9_2_4.py.
- EQUIPMENT_LABELS contains 34 keys with no duplicates; all 13 original
  keys and their labels are unchanged.

Not changed in this patch
- Module 2's electrical-power/energy default table (used only for 8760-hour
  energy estimation, currently 5 entries: lighting/outlets/air_conditioning/
  ventilation/refrigerator) was NOT extended to the new categories. Most of
  the new categories (plumbing fixtures, HVAC diffusers, etc.) do not draw
  electricity the way lighting/outlets do, so folding them into that table
  is a separate, larger decision that needs its own consultation rather
  than being bundled into this category-coverage patch.
- No calculation logic, cost data, or existing category behavior changed.
