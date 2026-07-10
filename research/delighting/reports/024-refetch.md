# 024 — Targeted re-fetch: recovering the report 019 test-fire-tile losses

Branch `research/delighting-024`. Script in `../corpus/{refetch_contaminated,
refetch_contact_sheet}.py`, artifacts in `../results/corpus/{refetch_manifest.json,
refetch_before_after_contact_sheet.jpg}`. Executes report 019's Patch #1 (the
"image-pick guard") as a one-off targeted recovery — `build_swatch_library.py`
was **not** modified, and `glass_swatch_registry.json` was **not** edited (see
Hand-off below). New images live in the MAIN checkout's `catalog_images/` as
`<id>-v2.jpg`, alongside the original contaminated files, which are left in
place.

## TL;DR

- **Target list (report 019's smoking-gun taxonomy, joined off `swatch_quarantine.json`
  + the registry): 14 registered Bullseye images** — the non-iridescent Reactive
  trio (Cloud Opalescent / Ice Transparent / Red Reactive, 2 size variants each = 6)
  plus the full Alchemy line (2 colorways × 2 sizes × iridescent-or-not = 8).
- **7/14 recovered, 7/14 unrecoverable — genuinely, not from a lenient bar.** Every
  recovered image was eyeballed at full resolution before being written; two of the
  automated flagger's "clean" picks turned out to be a second crop of the *same*
  before/after demo tile (the two rectangles merge into one non-frame-filling blob
  and dodge the `test_fire_tiles` heuristic) and were manually overridden back to
  unrecoverable. Two more recovered picks are accepted **with a caveat**: a real
  photo of the product sheet with a small 4-tile reaction-demo insert in one corner,
  not a pure clean sheet.
- **The pattern is almost entirely "does Shopify even have a real sheet photo,"
  not "did the flagger pick correctly."** All 4 *iridescent* Alchemy variants have
  4 live product images (a full-sheet shot exists at position 4) and all 4 recovered
  clean. All 5 pure `no_candidate_passed_flagger` unrecoverables, plus the 2
  human-overridden ones, are *non-iridescent* products with only 2 live images —
  both of which are test-fire/demo shots. There is no real sheet photo to recover
  for these 7 SKUs on Bullseye's current storefront; recording them as
  unrecoverable is correct, not a script failure.
- **Clean corpus (report 021's `clean_manifest.json`) regains coverage:
  1,274 → 1,281** (+7): Bullseye 510 → 517, cathedral-clear 800 → 805 (+5),
  opalescent 272 → 274 (+2). Oceanside/Youghiogheny/Wissmach/wispy/dark-opaque
  unchanged (out of scope — this recovery only touches the 14 Bullseye
  reactive/Alchemy targets).
- **019 Patch #1 validated in practice, with one refinement.** The proposed guard
  ("if `images[0]` is flagged, retry with the next image") works for most of the
  14, but this run shows it isn't sufficient on its own: a same-photo re-crop can
  slip past the cheap image heuristic, so any productionized version of Patch #1
  needs either the name-based blocklist as a second gate on *every* candidate
  (not just position 0) or a human/VLM review step — the same conclusion 019 §3
  already reached about `product_on_white`, now confirmed for a second failure
  mode on the same heuristic.
- **Registry integration is out of scope and handed off**, per the task's write
  policy — `glass_swatch_registry.json` is not touched. `refetch_manifest.json` is
  the bridge artifact. (While tracing the scraper's dedup logic to build the
  target list, found that `build_swatch_library.py` already has a
  `-v2`-preferring hook wired in at its dedup step — see Hand-off note below.)

## 1. Target list

Report 019 (§1–2) hand-verified that report 019's automatic flagger's
`test_fire_tiles`/`reaction_demo_line` reason codes correctly capture 14
registered Bullseye images: the scraper's `images[0]` rule picked a fired
reaction-test-tile photo instead of the sheet for the non-iridescent Reactive
line (Cloud Opalescent, Ice Transparent, Red Reactive — 2 size variants each)
and for the entire Alchemy line (Clear Silver→Gold / Silver→Bronze, 2 sizes,
iridescent-or-not). `refetch_contaminated.py`'s `build_target_list()` derives
this same 14 programmatically — joins `swatch_quarantine.json` items
(`id != null`, `manufacturer == Bullseye`, reason ∈
`{test_fire_tiles, reaction_demo_line}`) against the registry, then applies
019's exact name taxonomy (`reactive` in name and `iridescent` not in name,
OR `alchemy` in name) — rather than a hand-typed id list, so a future
quarantine re-run stays in sync with this script's scope.

Confirmed n=14 exactly matches report 019's count. Their on-disk size-variant
duplicates (`ffull`/`fhalf`, byte-identical to the registered `f1010` file,
per report 021 §1) exist but are unregistered orphans outside the registry —
019/021's hash-dedup already treats them as the same photo as their
registered sibling, so recovering the registered `f1010` id is sufficient;
the orphans are not separately re-fetched.

## 2. Fetch + automated pick

`refetch_contaminated.py` pages `https://shop.bullseyeglass.com/products.json`
(same store, same `User-Agent` convention as `build_swatch_library.py`,
1 req/s, cached to disk so re-runs don't re-hit the store), matches each
target's `base_sku` against the live catalog, downloads **every** image on
the matched product page (not just position 0), and runs report 019's
`audit_flagger.analyze_image` + `flag_signals` on each candidate. Per the
task's instruction, only the image-heuristic `test_fire_tiles` reason
rejects a candidate — the name-based `reaction_demo_line`/
`composite_streamer_line` codes describe the *product line*, not the
specific photo, and would reject every image of a target product identically
if used as a per-image filter. Winner = the last (highest-position)
surviving candidate, matching 019's own finding that the real sheet sits at
position 2+ once the lead test-fire photo is skipped.

Automated result: **9/14 "recovered."**

## 3. Human verification catches two automated false negatives

Task step 5 required eyeballing every recovered image before accepting it —
not a formality here. Two of the automated "winners" are not sheets:

- **`bullseye-0010160030f1010`** (Alchemy Clear Silver to Bronze,
  non-iridescent, double-rolled) and **`bullseye-0010160050f1010`** (same
  colorway, thin-rolled) each have only 2 live images, and **both are the
  same before/after fired-tile demo** — one a tight crop on the two
  adjoining rectangles, one zoomed out. In the tight crop the two rectangles
  sit close enough together that `analyze_image`'s connected-component pass
  merges them into a single blob that doesn't fill the frame — this dodges
  `TF_BLOBS_LO<=n_blobs<=TF_BLOBS_HI` in a subtly wrong way (the merged blob
  reads as one non-frame-filling foreground object) and lands in the weaker
  `product_on_white` bucket instead of `test_fire_tiles`. The automated
  picker took position 1 as a "clean" winner; it is not a sheet at all —
  neither of this product's 2 images is.

  These two are hand-verified, hard-coded overrides in the script
  (`MANUAL_REVIEW`, `verdict: "reject"`) with the reasoning inline as code
  comments, not a silent exclusion — moved to `unrecoverable` with
  `reason: "human_verification_rejected_automated_pick"`.

- **`bullseye-0000090030f1010`** and **`bullseye-0000090050f1010`**
  (Reactive Cloud Opalescent, both sizes) picked a real photo of the actual
  product sheet — edge-to-edge glass, consistent rounded corners across the
  whole frame — but it also contains a small 4-tile reaction-demo insert
  confined to the upper-left corner (~15% of the frame). This is a
  materially different, better photo than the pure test-fire lead image it
  replaces, but it isn't a pure clean sheet either. Accepted, with an
  explicit `human_verification_caveat` string carried through to
  `refetch_manifest.json` and the clean-manifest row's
  `report_024_provenance`, following report 021 §5's precedent
  (accept-with-caveat over silent accept or blanket exclude for borderline
  real-corpus photography). A center-crop color/texture extractor (as used
  by `appearance_stats.py`) would not touch the corner insert.

All other picks (5 of 7 recovered) were confirmed clean on inspection with no
caveat needed.

## 4. Recovered / unrecoverable

| id | name | result | position picked / n images | flagger verdict | note |
|---|---|---|---:|---|---|
| `bullseye-0000090030f1010` | Reactive Cloud Opalescent, Double-rolled 3mm | **recovered** | 2/2 | clean | caveat: corner demo insert |
| `bullseye-0000090050f1010` | Reactive Cloud Opalescent, Thin-rolled 2mm | **recovered** | 2/2 | clean | caveat: corner demo insert |
| `bullseye-0010090030f1010` | Reactive Ice Transparent, Double-rolled 3mm | unrecoverable | — | both images test-fire | only 2 images, no sheet exists |
| `bullseye-0010090050f1010` | Reactive Ice Transparent, Thin-rolled 2mm | **recovered** | 2/2 | clean | — |
| `bullseye-0010150030f1010` | Alchemy Silver→Gold, Double-rolled 3mm | unrecoverable | — | both images test-fire | only 2 images, no sheet exists |
| `bullseye-0010150031f1010` | Alchemy Silver→Gold, Double-rolled, Iridescent | **recovered** | 4/4 | product_on_white | full-sheet iridescent photo |
| `bullseye-0010150050f1010` | Alchemy Silver→Gold, Thin-rolled 2mm | unrecoverable | — | both images test-fire | only 2 images, no sheet exists |
| `bullseye-0010150051f1010` | Alchemy Silver→Gold, Thin-rolled, Iridescent | **recovered** | 4/4 | product_on_white | full-sheet iridescent photo |
| `bullseye-0010160030f1010` | Alchemy Silver→Bronze, Double-rolled 3mm | unrecoverable | — | human-override reject | automated pick was the same demo, re-cropped |
| `bullseye-0010160031f1010` | Alchemy Silver→Bronze, Double-rolled, Iridescent | **recovered** | 4/4 | product_on_white | full-sheet iridescent photo |
| `bullseye-0010160050f1010` | Alchemy Silver→Bronze, Thin-rolled 2mm | unrecoverable | — | human-override reject | automated pick was the same demo, re-cropped |
| `bullseye-0010160051f1010` | Alchemy Silver→Bronze, Thin-rolled, Iridescent | **recovered** | 4/4 | product_on_white | full-sheet iridescent photo |
| `bullseye-0010190030f1010` | Red Reactive Clear Transparent, Double-rolled 3mm | unrecoverable | — | both images test-fire | only 2 images, no sheet exists |
| `bullseye-0010190050f1010` | Red Reactive Clear Transparent, Thin-rolled 2mm | unrecoverable | — | both images test-fire | only 2 images, no sheet exists |

**7 recovered, 7 unrecoverable.** Full detail (per-candidate signals, product
URLs, image lists): `../results/corpus/refetch_manifest.json`.

## 5. Visual verification

`refetch_before_after_contact_sheet.jpg` (committed, downscaled, 820×3716,
14 rows — old contaminated pick on the left, new `-v2` fetch or a red
"UNRECOVERABLE" placeholder on the right, quarantine reason codes printed per
row): `../results/corpus/refetch_before_after_contact_sheet.jpg`. I looked at
every tile myself (not just the two overrides in §3): all 7 recovered tiles
are visibly flat sheet swatches (5 clean, 2 with the corner-insert caveat
called out above); all 7 unrecoverable rows show the old test-fire/demo photo
with nothing better available. No recovered tile is a repeat of a test-fire
demo.

## 6. Clean-corpus regeneration

`clean_manifest.py` (report 021) gained a Step 5: if
`results/corpus/refetch_manifest.json` exists, each `recovered` entry is
added as a new clean-manifest row, inheriting the **original** registry
row's `category`/`name` (the image changed, the SKU didn't) and reusing 015
`census.py`'s own `map_class()` for `extractor_class`/`confidence`/`rule` —
the same function that classifies every other row, so recovered rows aren't
a special downstream case. `match_kind: "recovered-v2"` and a
`report_024_provenance` block (old file, product URL, position picked,
flagger verdict, caveat text) carry traceability. No-op if the refetch
manifest doesn't exist, so `clean_manifest.py` still builds standalone.

Regenerated counts:

| | before (report 021) | after (report 024) | delta |
|---|---:|---:|---:|
| n_clean | 1,274 | **1,281** | +7 |
| Bullseye | 510 | **517** | +7 |
| Oceanside | 281 | 281 | 0 |
| Youghiogheny | 266 | 266 | 0 |
| Wissmach | 217 | 217 | 0 |
| cathedral-clear | 800 | **805** | +5 |
| opalescent | 272 | **274** | +2 |
| wispy | 163 | 163 | 0 |
| dark-opaque | 39 | 39 | 0 |

The +5/+2 class split matches the recovered set exactly: the 2 Reactive
Cloud Opalescent recoveries are `Opalescent` category (→ `opalescent`
extractor class); the other 5 (Reactive Ice, the 3 iridescent Alchemy pairs)
are `Cathedral` category (→ `cathedral-clear`). All 7 land at `confidence:
high` (direct category match, same as their non-recovered siblings).

## 7. 019 Patch #1, validated and refined

019 §4 proposed: "after download, run the flagger and, if the picked image
is flagged `test_fire_tiles`, retry with the product's next image." This run
is that patch, executed by hand across the 14-image target set, and it
mostly works — 5 of 7 clean recoveries are exactly this: reject position 1,
accept the first later position that passes. But §3 above shows the cheap
image heuristic alone is not sufficient as a guard: two "passing" images
were the *same* non-sheet content re-cropped, dodging `test_fire_tiles` by
accident of blob geometry. A productionized Patch #1 should not treat a
single `test_fire_tiles`-negative verdict as sufficient; either (a) require
every re-tried candidate to also clear the name-based blocklist check
(019's `flag_name`) as a second, independent gate — which would not have
caught this specific case, since both false negatives are non-iridescent
Alchemy and already fail that check on the whole product — or, more
robustly, (b) treat a same-product-different-position "clean" verdict as
provisional and require a duplicate-detection pass across the product's own
image set (crop/rescale-tolerant, not byte-hash) to catch "different crop of
the same photo" specifically, since that's the exact failure mode found
here. Out of scope to build in this recovery pass; flagged for whoever picks
up Patch #1 for real.

## 8. Hand-off

`glass_swatch_registry.json` is **not modified** by this report, per the
task's write policy — it is owned by the scraper agent. While tracing
`build_swatch_library.py`'s dedup step to build the target list (§1), found
that the scraper **already has a `-v2`-preferring hook wired into its
dedup loop**:

```python
# Prefer recovered -v2 image version from delighting-024 if present
local_img_filename = os.path.basename(item['local_image'])
base_name, ext = os.path.splitext(local_img_filename)
v2_filename = f"{base_name}-v2{ext}"
v2_path = os.path.join(IMAGE_DIR, v2_filename)
if os.path.exists(v2_path):
    item['local_image'] = f"/assets/catalog_images/{v2_filename}"
    ...
```

This means the naming convention used here (`<id>-v2.jpg`) is not incidental
— it's exactly what the scraper owner's own code already looks for. No
action needed from this report beyond leaving the 7 `-v2` files in
`catalog_images/`; the next scraper run should pick them up automatically
for the 7 recovered SKUs (and continue serving the original contaminated
image for the 7 still-unrecoverable ones, since no `-v2` file exists for
them). `refetch_manifest.json` documents exactly which SKU is which for
whoever verifies that pickup.

## Reproduction

```
cd research/delighting/corpus
python3 refetch_contaminated.py --out ../results/corpus/refetch_manifest.json
python3 refetch_contact_sheet.py
python3 clean_manifest.py        # picks up refetch_manifest.json automatically if present
```

Requires `requests`-free stdlib (`urllib`) plus `PIL`/`numpy`/`scipy` (the
project `.venv` lacked all four in this run; `/usr/bin/python3` on the dev
machine had them — see script docstring). Corpus
(`frontend/public/assets/{catalog_images,glass_swatch_registry.json}`) is
gitignored on `main`; the registry and existing catalog images were accessed
read-only via a symlink into this worktree (same convention as reports
015/019/021). The 7 recovered `-v2` JPEGs were written directly into the
MAIN checkout's `catalog_images/` (not through the symlink, not committed to
this branch — that directory is gitignored) per the task's write policy;
`glass_swatch_registry.json` in the main checkout was not touched.
