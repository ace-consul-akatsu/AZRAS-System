AZRAS Planning Version 2.2.0 (patch number: see "patch" in VERSION.json)
Official product slot: 01 AZRAS Planning
Formal flow: 01 Planning -> 02 Evaluation -> 03 Compare
Planning owns the authoritative planning-stage Project JSON.
PDF/ZIP analysis must not silently change Building System / Structure / Method.
Human Review is current-state-only. One current AI snapshot is retained per canonical provider.
Changing Building System removes current imported AI state. AI takeoff data use only the four Project/R1 workflow folders.
Missing/unresolved values are not silently replaced with zero.
Run: run_AZRAS_Planning_without_build.bat
Build: build_AZRAS_Planning.bat
Historical Planning_Basic identifiers are compatibility aliases only.

AI safety and audit (Planning_22):
- AZRAS Planning itself does not call AI-service APIs. It exports request TXT/ZIP files for user-controlled exchange with AI services.
- On AI JSON import, AZRAS technically allows only public HTTP/HTTPS evidence URLs and rejects localhost, loopback, RFC1918/private/link-local targets, credential-bearing URLs, single-label intranet hosts, and non-web schemes.
- This is an AZRAS-side enforcement boundary; AZRAS does not claim control over an AI provider's internal network isolation.
- Generated requests and imported/rejected AI responses are logged project-locally with hashes, reviewer/time metadata, explicit source URLs, and contract/security anomalies; a rolling 7-day anomaly summary is refreshed.
- Hidden chain-of-thought is neither requested nor stored. Audit evidence is limited to observable request/response artifacts and explicit calculation_basis/decision/evidence fields, source URLs, hashes, and validation anomalies.
