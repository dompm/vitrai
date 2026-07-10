# Report 014 - Catalog-constrained sheet prior

Date: 2026-07-09. Code:
`sheet_texture_prior.py`, `catalog_texture_audit.py`.

## 0. TL;DR

Report 013 confirmed the real right-panel sheet problem: for transmissive
hammered cathedral glass, the current extractor removes smooth lighting, but
garden/window structure still leaks into `T`. A piece dragged across the sheet
therefore changes appearance by position.

I tested a bolder sheet-level prior:

> Assume a hammered cathedral sheet has one dominant physical tint; keep local
> high-frequency hammered relief, but suppress low/mid-frequency color and
> brightness structure as likely capture/background contamination.

Result on the suncatcher sheets:

| condition | position mean dE | position luminance CV | hue std deg |
|---|---:|---:|---:|
| raw copy | 8.98 | 0.407 | 1.5 |
| fixed `T/h` relit | 10.12 | 0.318 | 1.7 |
| sheet prior | **1.90** | **0.060** | **0.3** |

This is a huge consistency win, but it is not automatically a product win. It is
a plausible-material prior, not proof that we recovered the exact physical
sheet.

The new catalog audit uses 1,381 scraped manufacturer sheets as a reality check.
After tuning the detail strength against that catalog, the green prior preserves
realistic hammered texture: its high-frequency metric lands at the **50th
percentile** of Textured/Baroque catalog sheets, while its low-frequency
variation drops from the 84-90th percentile to the low 30s.

## 1. Product framing correction

The right panel in Vitrai is the glass sheet as the artist would buy it. It is
not the leaded/came assembled panel. Piece outlines may appear on the sheet for
placement, but lead lines belong to the left assembled preview.

So this experiment is specifically about the sheet material:

- does the sheet look like real purchasable glass?
- does the same sheet stay consistent when the artist drags pieces around?
- does the preview avoid baking in garden/window/photo artifacts?

The catalog images are useful because they represent real sold sheets, not
assembled panels.

## 2. Method

`sheet_texture_prior.py` starts from the fixed extractor's `relit` material:

```text
relit = T * (h + (1 - h) * 1)
```

For each sheet interior:

1. compute luminance;
2. split log-luminance into low-frequency and high-frequency components;
3. take the median sheet chroma as the physical tint;
4. reconstruct a cleaner sheet from median chroma + high-frequency luminance;
5. tune detail strength so the retained texture is catalog-plausible.

This is intentionally aggressive. It should be read as a candidate prior for
cathedral/hammered sheets, not for wispy, streaky, ring mottle, or opalescent
sheets where low-frequency color variation may be the actual material.

## 3. Catalog audit

The catalog source was provided separately in the main workspace:

- `frontend/public/assets/catalog_images/`
- `frontend/public/assets/glass_swatch_registry.json`
- `scripts/build_swatch_library.py`

The research worktree does not currently track those images, so the audit command
used the main workspace registry path:

```sh
python3 research/delighting/catalog_texture_audit.py \
  --registry /Users/dominiquepiche-meunier/Documents/vitraux/frontend/public/assets/glass_swatch_registry.json
```

Catalog distribution summary:

| category | n | lum_cv med | lowfreq_cv med | highfreq_std med |
|---|---:|---:|---:|---:|
| Cathedral | 699 | 0.221 | 0.179 | 0.094 |
| Opalescent | 356 | 0.099 | 0.078 | 0.030 |
| Wispy/Streaky | 163 | 0.412 | 0.322 | 0.223 |
| Textured/Baroque | 138 | 0.503 | 0.301 | 0.343 |
| English Muffle | 17 | 0.268 | 0.189 | 0.163 |
| Ring Mottle | 8 | 0.306 | 0.183 | 0.181 |

Suncatcher sheet conditions after tuning:

| sample | lowfreq_cv | highfreq_std | textured highfreq percentile | cathedral lowfreq percentile |
|---|---:|---:|---:|---:|
| green raw | 0.611 | 0.564 | 77% | 90% |
| green fixed `T/h` | 0.477 | 0.558 | 76% | 84% |
| green sheet prior | **0.087** | **0.341** | **50%** | **32%** |
| orange raw | 0.400 | 0.432 | 66% | 78% |
| orange fixed `T/h` | 0.258 | 0.353 | 51% | 63% |
| orange sheet prior | **0.050** | **0.216** | **21%** | **25%** |

Read:

- raw and fixed `T/h` have much more low-frequency structure than typical catalog
  cathedral sheets;
- fixed `T/h` preserves the same high-frequency relief/background detail, so it
  does not solve the see-through residual;
- the tuned prior removes the low-frequency contamination while keeping green's
  texture at a manufacturer-plausible strength;
- orange is smoother than ideal, but no longer as airbrushed as the first pass.

## 4. What this means

This is the first result that feels like a real high-risk product path for the
right glass panel:

```text
classical extractor -> sheet-level material prior -> provenance/confidence label
```

The prior makes the sheet act like a sheet again. A leaf sampled from nine
positions no longer swings wildly from dark emerald to bright garden green.

But it also deliberately discards information. If that information is a real
streak, wisp, ring mottle, or color mix, the prior would be wrong. That is why
the catalog categories matter: the operation should be class-gated and probably
learned from catalog/real examples, not applied globally.

## 5. Next high-risk move

Use the catalog as a weak material prior:

1. Embed catalog sheets by texture/color statistics and/or a small vision model.
2. Given a user photo, estimate the closest material family and whether spatial
   variation is likely material or capture/background.
3. Predict `T,h,height,relief_confidence,prior_strength`.
4. Apply a sheet-level prior only when confidence is high.
5. Show provenance: **sheet-derived**, **catalog-prior assisted**, or **artist
   tuned**.

That path directly answers the artist-subagent trust question without giving up
on a bolder render.

## 6. Files

- `sheet_texture_prior.py` - suncatcher sheet-prior experiment and metrics.
- `catalog_texture_audit.py` - catalog reality-check metrics and nearest examples.
- `results/sheet_texture_prior/summary_table.md`
- `results/sheet_texture_prior/sheet_contact.jpg`
- `results/sheet_texture_prior/position_contact_GT_PIECE_2.jpg`
- `results/catalog_texture_audit/catalog_summary.md`
- `results/catalog_texture_audit/nearest_catalog_examples.jpg`
- `results/catalog_texture_audit/metrics.json`

