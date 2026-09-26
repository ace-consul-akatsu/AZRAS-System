AZRAS Planning PATCH 579

1. Added an in-app human-review screen: 「不明・矛盾を画面で回答」.
2. Normal users can answer unresolved/drawing-conflict items directly in AZRAS.
3. AZRAS internally creates an AZRAS_HUMAN_REVIEW_FINAL audit JSON and immediately applies it through the same formal human-review engine.
4. Unanswered items remain unresolved; they are never converted to zero.
5. The Review Excel remains available only as an optional external-designer handoff route.
6. Added user/designer additional-item entry directly on the review screen.
7. Explicit RC exterior-wall / 2x6 exterior-wall area allocation can be entered as a two-value human instruction and is persisted as the formal design parameter for rebuild.
8. Unit input aliases such as ㎡ / m² and ㎥ / m³ are normalized to m2 / m3 for direct approved quantities.
9. Fixed ADD-row creation when the quantity-row list is initially empty.

Current answered Excel transcription:
- AZR-0001: RC exterior wall 113.16 m2; 2x6 exterior wall 114.48 m2.
- ADD-0001: finish / wallpaper 213.204 m2.
- Cells containing only placeholder value "1" were not converted into human decisions.
