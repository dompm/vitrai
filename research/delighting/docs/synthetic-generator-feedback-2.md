# Generator feedback round 2 — after first ground-truth extractor eval (iteration 005)

Confirmed good: streaky-mix now renders as a genuine translucent milky sheet (physics fix holds),
cathedral-green renders correctly (the black cross is a legit leaded frame on has_frame samples),
gt_T.exr is correctly LINEAR and camera-aligned. The eval harness works.

## Priority 1 — render the missing 3 recipes, in this order
Only cathedral-green and streaky-mix exist. The recipes that answer the open questions are ALL absent:
1. **wispy-white** — the money case. Opalescent/milky glass is where de-lighting is well-posed (haze
   hides the background), and it's the real product target (the sheet the maintainer photographed).
2. **dark-opaque** — needed to confirm BOTH the absolute-T-scale question AND that the purple/magenta
   HDRI-path fix actually worked. Currently unverifiable.
3. **cathedral-amber** — completes the set.
A `--validate --count 5` run (all five recipes, flat backlight) would ALSO finally close the
long-standing coverage gap in one shot — please run that at least once and keep its per-recipe output.

## Priority 2 — help the eval separate glass from background (small)
The extractor recovers *effective* transmittance including whatever shows through the glass; gt_T is the
*intrinsic tint only* (near-flat). For clear cathedral glass against a structured HDRI (sky/grass/frame),
sharp background leaks into extracted T and inflates the error — this is inherent single-photo ambiguity,
not purely an extractor bug, but it contaminates the metric. Two cheap options (either is fine):
- Add the glass-plane's 4 projected corners (and has_frame region) to meta.json so eval can crop/mask
  frame + edges; OR
- Render a subset against a SMOOTH/diffuse background (uniform or heavily blurred HDRI) so clear-glass
  tint can be scored without background contamination.

## Priority 3 — minor
- `gt_h.exr` and `gt_mark_mask.exr` don't decode in OpenCV (the PNG versions work fine) — either drop
  the EXR variants for masks or fix the encoding; not blocking.
