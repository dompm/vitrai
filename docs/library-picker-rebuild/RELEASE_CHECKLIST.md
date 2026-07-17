# Glass library release -- checklist

Tracking the `library-release` branch on its way to a CTO-reviewed merge into `main`.
This is the canonical checklist; the release PR body mirrors it.

- [x] **Striker exclusion** (2026-07-16) -- 146 unfired strikers filtered out of the
  shipped library (WYSIWYG); pre-struck exception verified to match zero products.
- [x] **kiln_transformative + kept-but-flagged metadata** (2026-07-17) -- 4 Bullseye
  Alchemy rows excluded as `kiln_transformative`; `reactive:true` (15 rows) and
  `iridized:true` (162 shipped rows) metadata added. Quarantine now 150 total;
  library 1332 -> 1182.
- [→] **Scale audit** (in progress, scale-audit / task #18) -- Bullseye macro-shot
  real_world-footprint correction + iridescent transmission-shot pick rule (keys off
  the new `iridized:true` flag). Blocked on CTO flag-list export.
- [ ] **CTO flag list + VLM judge pass** -- apply the CTO's audit-UI flag export and
  a judge pass over the flagged products.
- [ ] **Image hosting** -- resolve catalog-image hosting/CDN for the shipped registry
  (`VITE_SWATCH_CDN_URL`).
- [ ] **Final review** -- CTO sign-off on the consolidated library before merge.
