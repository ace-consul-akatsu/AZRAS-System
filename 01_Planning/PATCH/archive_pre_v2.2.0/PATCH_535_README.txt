AZRAS Planning PATCH 535

Purpose
- Stop using one whole-building GFA timber intensity for both 2×6 and AZRAS.
- Calculate structural timber independently from each method drawing scope: exterior timber wall + internal timber wall + upper-floor framing + roof framing.
- Keep component rows visible as audit detail and expose one physical total downstream.
- In RC projects, when AI/drawing review explicitly identifies 105 mm LGS partitions, calculate the LGS steel mass as a yellow provisional quantity and send it to cost/LCA.
- If LGS is not explicitly identified, do not guess wood/2×4/LGS from wall thickness alone.

Current sample planning assumptions (yellow/designer-editable)
- wall studs 38×140 @455 mm; 1.15 plate/blocking factor
- internal timber studs 38×89 @455 mm + top/bottom plates
- upper-floor joists 38×235 @455 mm
- roof rafters 38×235 @455 mm
- RC LGS: 105 mm stud/runner, t0.8 mm, stud 105/45/10, runner 105/40, @455 mm

These assumptions are not drawing-confirmed material schedules. Drawing-derived geometry is preserved separately, and the provisional framing parameters remain yellow and designer-editable.
