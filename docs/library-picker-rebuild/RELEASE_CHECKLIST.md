# Glass library release -- checklist

Tracking the `library-release` branch on its way to a CTO-reviewed merge into `main`.
This is the canonical checklist; the release PR body mirrors it.

- [x] **Striker exclusion** (2026-07-16) -- 146 unfired strikers filtered out of the
  shipped library (WYSIWYG); pre-struck exception verified to match zero products.
- [x] **kiln_transformative + kept-but-flagged metadata** (2026-07-17) -- 4 Bullseye
  Alchemy rows excluded as `kiln_transformative`; `reactive:true` (15 rows) and
  `iridized:true` (162 shipped rows) metadata added. Quarantine now 150 total;
  library 1332 -> 1182.
- [x] **Scale audit** (2026-07-17, scale-audit / task #18) -- 423 Bullseye products
  audited (`scripts/scale_audit.py`, sidecar `scale_audit.json`, `scale_report.md`,
  `scale_boards/`). 183 known-wrong ~10in stamps nulled, 10 whole-sheet heights made
  aspect-consistent, 198 `needs_repick` flags; iridescent transmission-shot + split-
  backdrop-seam rules folded in (14 reflection-side picks, 91 transmission re-picks;
  keys off `iridized`). Absolute sample size is a documented assumption (retune
  `SAMPLE_LONG_IN`). Pick-preference implemented + gated (`SCALE_AWARE_REPICK`) pending
  image hosting. Independent of the CTO flag export.
- [ ] **CTO flag list + VLM judge pass** -- apply the CTO's audit-UI flag export and
  a judge pass over the flagged products.
- [ ] **Image hosting** -- resolve catalog-image hosting/CDN for the shipped registry
  (`VITE_SWATCH_CDN_URL`).
- [ ] **Final review** -- CTO sign-off on the consolidated library before merge.
