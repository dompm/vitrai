# Glass swatch library — ownership

The glass-library work (scraper, picker integration, registry, library UI) is
owned by the **research lead** (reassigned by the maintainer, 2026-07-11).

## Key files

| File | Role | Tracked? |
|---|---|---|
| `scripts/build_swatch_library.py` | Scraper/build pipeline (picker-scored image selection, crops, calibration, dedup, overrides, diff report) | yes |
| `scripts/swatch_picker.py`, `scripts/audit_flagger.py` | Vendored research modules (delighting reports 035 / 019 — provenance in file headers) | yes |
| `frontend/public/assets/glass_swatch_registry.json` | The registry the app reads at runtime | **yes (committed)** |
| `frontend/public/assets/catalog_images/` | Swatch photos (~548 MB) | no (gitignored; fetch via the build script) |
| `frontend/src/components/GlassLibraryDialog.tsx` | Library UI (search/filter/pick, empty-state, front-lit badge) | yes |
| `docs/library-picker-rebuild/report.md` | 036 rebuild before/after report + contact sheet | yes |

## Decision log (ownership cleanup, 2026-07-12)

Closing the findings of `glass-library-integration-review.md` (integration review
+ addenda):

1. **CI restored** — `.github/workflows/ci.yml` is back, byte-identical to the
   pre-deletion version on `main` (pnpm 10 / node 22 / `pnpm install
   --frozen-lockfile && pnpm build` in `frontend/`). If the library feature ever
   breaks CI, fix the feature or extend CI — never delete the workflow.
2. **Clean-checkout resilience** — the registry JSON is committed; the images
   stay untracked. The dialog shows an explicit setup message when the registry
   is missing and an "image not fetched" note per thumbnail when images 404,
   instead of a silent empty grid. Data setup is documented in the README
   ("Glass swatch library data").
3. **Reactive Cloud (Bullseye 000009-0030/-0050): KEEP+crop** — re-included
   using the adjudicated clean crop, x:[650,1200] y:[0,1200] of the 1200×1200
   `-v2` image (review Addendum; adjudication recorded in the research trunk's
   `research/delighting/results/corpus/refetch_manifest.json` `recovered`
   entries). The crop excludes the reaction-demo tile corner insert entirely;
   both crops visually verified tile-free. The former blanket
   `is_reactive_cloud` drop rule is replaced by `REACTIVE_CLOUD_CROP_OVERRIDE`
   in the build script.
4. **White-on-white picker false positives** — Opaque White (000013-0030) and
   silver-gray Cascade (002249-CA37) are restored via the explicit, commented
   `WHITE_ON_WHITE_OVERRIDE` per-SKU list. The picker floor (0.45) was NOT
   lowered globally; the underlying pale-sheet blind spot is a research-side
   follow-up (extend the pale-sheet credit to intermediate `fg_frac` when the
   foreground is itself near-white).
5. **Review leftovers** — the two duplicate-photo dedup escapees
   (`oceanside-of76f`/`-6x12`, `youghiogheny-yskysp`/`-6x12`) are resolved by
   the `_strip_query` image-URL dedup pass from the 036 rebuild. Registry
   entries carry a `lighting` field (`front-lit`/`back-lit`, from report
   015/019 per-manufacturer priors: Oceanside `*irid*` SKUs, Youghiogheny
   dark-opaque/stipple lines); the dialog badges `front-lit` entries with a
   warning that they are surface shots, not transmissive color.

## Regenerating the data

```bash
pip install requests Pillow
python3 scripts/build_swatch_library.py
```

Idempotent and incremental — see the README section and the script's own
comments (stability rule, picker floor, manual overrides) before changing
selection behavior.
