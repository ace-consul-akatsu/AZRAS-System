AZRAS Planning PATCH 629

Requested by the developer: values entered on the unresolved-item answer
screen ("不明・矛盾を画面で回答") should be stored rounded half-up
(四捨五入) to 2 decimal places.

Behavior
- module1/app.py: new module-level helper _round_half_up(value, digits=2),
  using decimal.Decimal with ROUND_HALF_UP instead of Python's built-in
  round(). This matters for two reasons:
  1. round() in Python uses round-half-to-even ("banker's rounding"), not
     round-half-up -- e.g. round(0.125, 2) can give 0.12, not 0.13.
  2. round() operates on a binary float, which cannot represent many
     decimal fractions exactly, so even "round half up by hand" logic
     built on top of float can misfire (round(2.005, 2) gives 2.0 in
     Python, not 2.01), because 2.005 is not exactly representable in
     binary floating point. Decimal(str(value)) parses the user's typed
     digits directly, avoiding that conversion error.
- Applied at the three places on this screen that parse a user-typed
  numeric value into a stored quantity:
  1. The main "承認値" (approved quantity) field.
  2. The "追加承認値" (additional-item quantity) field.
  3. The RC / 2x6 exterior-wall-system split values parsed from the
     free-text "ユーザー/設計者の指示" field.

Verified
- python -m py_compile passes for module1/app.py.
- _round_half_up("2.005", 2) -> 2.01 (Python's round(2.005, 2) gives 2.0).
- _round_half_up("12.345", 2) -> 12.35.
- _round_half_up("0.125", 2) -> 0.13.

Not changed in this patch
- No other numeric-entry field in Module 1 was touched; this patch is
  scoped to the unresolved-item answer screen the developer asked about.
