AZRAS Evaluation PATCH 216 (consolidated)

Delivered as a full replacement ZIP (v1.0.216), not a diff PATCH, per the
new delivery method. Consolidates two rounds of fixes:

1. Generic exception dialogs (module3/app.py, module4/app.py,
   module6/app.py, module7/app.py)
   - New core/error_text.py: friendly_exception_text(exc, language),
     mirroring Planning's helper. ValueError passes through unchanged;
     any other exception type gets a short generic framing sentence
     with the raw type/message as a secondary detail. Applied at every
     remaining messagebox.showerror(...,str(exc)) site.

2. English-canonical UI default (main.py, core/i18n.py)
   - main.py previously created I18N(ROOT, "ja") and set
     self._ui_language = "ja" unconditionally on every launch, so
     Evaluation always opened in Japanese regardless of Planning's
     English default. Both now default to "en".
   - core/i18n.py's own internal default and its fallback for an
     unrecognized language code changed from "ja" to "en", now driven
     by the file's existing LANGUAGE_ORDER = ("en","ja") tuple.

Verified
- python -m py_compile passes for every .py file in this ZIP.
- lang/ja.json and lang/en.json key parity unchanged (768/768).
- The English/Japanese menu switch is unaffected; only the startup
  default changed.

Not changed in this patch
- No evaluation/comparison calculation logic changed anywhere in this
  ZIP.
