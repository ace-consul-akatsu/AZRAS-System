AZRAS Planning PATCH 592

Observed issue
After pressing formal apply in Human Review, the dialog could show:
  Module 1 result is not available.

Cause
Formal application of the exterior-wall allocation starts a deterministic full
drawing rebuild. The rebuild can clear self.result immediately. The screen-save
path then unconditionally called _save_result_to_project(), which requires the
old self.result and therefore raised the error after the answers had already
been accepted.

Related ADD-item issue
A user-added quantity such as ADD-0001 wallpaper could exist in the review UI
but disappear from the rebuilt quantity table if it had not been persisted to
Project JSON before the rebuild started.

Correction
1. Persist human-approved direct quantities/ADD items to Project JSON BEFORE
   starting recalculation/rebuild.
2. Do not unconditionally save the old Module 1 result after rebuild starts.
3. If self.result still exists, save normally. If it has been cleared by the
   rebuild, preserve/save the already-persisted Project authority state instead.
4. The confirmation dialog now reports answered UI items separately from formal
   structured decisions, avoiding the misleading '2 decisions' count when the
   exterior-wall split contains two answers inside one formal decision.

Regression policy
This PATCH was checked together with the preceding five-PATCH range and related
critical invariants, in accordance with the AZRAS Development Constitution.
