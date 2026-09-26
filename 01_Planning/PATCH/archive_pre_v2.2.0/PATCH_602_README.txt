AZRAS Planning PATCH 602

Public product title correction:
- AZRAS Planning Basic -> AZRAS Planning
- AZRAS Planning Basic Version -> AZRAS Planning Version

The historical source/work-folder identifier `01_AZRAS_Planning_Basic` is not
renamed where it is required as an internal filesystem/module identifier.

Regression:
- All Python sources compile.
- No user-visible `AZRAS Planning Basic` product-title string remains.
- PATCH 601 current-state/AI retention corrections remain in place.
