AZRAS Compare PATCH 20 (consolidated)

Delivered as a full replacement ZIP (v1.1.20), not a diff PATCH, per the
new delivery method. Consolidates two rounds of fixes to main.py:

1. Generic exception dialog
   - Added a small local friendly_exception_text(exc, language) helper
     (Compare has no shared core package). ValueError passes through
     unchanged; any other exception type gets a short generic framing
     sentence with the raw type/message as a secondary detail. Applied
     at the one messagebox.showerror(...,str(e)) site (project-load
     error dialog).

2. English-canonical UI default
   - App.__init__ previously set self.language='ja' unconditionally,
     and the module-level CURRENT_UI_LANGUAGE also started as 'ja'.
     Both now default to 'en'. The defensive fallback in
     _change_language() (used only if the language-menu selection
     cannot be matched) also changed from 'ja' to 'en'.

Verified
- python -m py_compile passes for main.py.
- The English/Japanese menu switch is unaffected; only the startup
  default changed. TEXT_EN dictionary content unchanged.

Not changed in this patch
- No comparison/report calculation logic changed.
