AZRAS Planning PATCH 594

Problem
The full rebuild path cleared `self.result` and removed `module_outputs.module1`
from the in-memory Project before the new analysis had succeeded. Although the
disk Project JSON was not intentionally overwritten at that instant, the UI
could become blank and later error/cancellation paths could leave the active
session without the previous authoritative Module 1 result.

Correction
The rebuild is now transactional:

  last committed Module 1
    -> preserve full pre-run snapshot
    -> analyze in scrubbed working state
    -> validate/build new result
    -> autosave Project JSON
    -> only then commit new Module 1

If drawing selection, structure consistency, analysis, or autosave fails:
  -> restore the previous committed Project + Module 1 result
  -> keep the previous quantity table visible/available

The old visible quantity table is no longer blanked at rebuild start.

UI
Added:
  保存済みM1結果確認 / View Saved M1

This reads `Project JSON -> module_outputs -> module1` directly and displays
the saved quantity rows independently of the current transient analysis state.

Five-PATCH regression rule
PATCH 594 was regression checked together with PATCH 589-593:
- 589 single Current workspace
- 590 AZR-0001 two independent answers
- 591 no Responses recreation path
- 592 human-review post-rebuild save guard
- 593 collected-AI response viewer
