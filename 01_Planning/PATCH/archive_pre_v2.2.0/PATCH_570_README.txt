PATCH 570 — R3 verification and strict UTC return validation

Base: 1.0.569

1. Confirmed Start AI Takeoff creates the R-round REQUEST TXT, REQUEST PACKAGE ZIP, and external START TXT.
2. Standard send method remains drawing PDF/ZIP + request ZIP + START TXT.
3. Meta may receive the request ZIP extracted when required by its interface.
4. Returned JSON filename time format is UTC YYMMDD_HHMM; seconds are forbidden.
5. Fixed a validator defect that previously converted a +09:00 timestamp to UTC before checking its offset. Non-UTC offsets are now correctly noncompliant.
6. Internal AI observation JSON filenames now also use UTC YYMMDD_HHMM without seconds.
