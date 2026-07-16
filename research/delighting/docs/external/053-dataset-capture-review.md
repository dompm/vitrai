<!--
Independent-agent review of the synthetic-dataset pipeline at trunk commit 8c8877a,
commissioned by the CTO, received 2026-07-16. The lead independently verified its five
concrete code claims against trunk before adopting it (see reports/053-deployment-capture-
realism.md §context). Reproduced verbatim below; the lab's response is report 053.
-->

# External dataset-capture review (CTO-commissioned, trunk @ 8c8877a)

The main thing missing is not another glass recipe. It's a faithful model of the deployment capture process.
Cropping solves segmentation, but it does not remove the transmitted background, reflections, shadows, white balance, HDR processing, blur, or exposure errors. A model could score beautifully on this synthetic set while mostly learning "Blender glass grammar."
I reviewed the branch at 8c8877a.

## Must fix before scaling

### Model actual phone processing
The loader currently adds exposure, signal-dependent noise, gamma variation, and JPEG recompression. That is a good start, but much narrower than a modern phone pipeline: automatic white balance, local HDR/tone mapping, sharpening halos, denoising, saturation shifts, per-channel clipping, lens shading, chromatic aberration, motion/defocus blur, rescaling and HEIC/JPEG conversion are absent. See the current camera augmentation.
I would implement several complete, device-like pipelines rather than independently randomizing effects. The correlations matter: low light tends to mean stronger denoising, sharpening and local tone mapping together.

### Use finite-depth backgrounds and mixed front/back lighting
The main scene uses an HDRI background at infinity and, by default, an effectively black camera-side environment. Real sheets are photographed against windows, trees, shelves, light tables and walls at radically different distances. Background distance controls how strongly relief refracts it.
Add explicit textured geometry behind the glass at perhaps 10 cm, 50 cm, 2 m and "infinity," with depth discontinuities. Also make front-side room illumination and reflections part of the normal distribution—not an opt-in stress test. The white-marker self-emission workaround is a useful warning sign: the scene lacks enough front illumination to render ordinary white paint naturally. See scene construction and material lighting.

### Simulate the crop workflow itself
Right now the glass is intentionally made to fill the frame, while training receives random local creates two problems:
Real crops will contain perspective, imperfect trimming and sometimes a small border.
Local 512-pixel crops remove the whole-sheet context needed to infer broad illumination gradients and hotspots.
Render a wider scene, then synthetically apply the same crop UI users will use: imperfect 0–5% padding/trimming, variable tilt and scale, and optionally four-corner rectification. Train with both the full cropped sheet and local detail patches.

### Strengthen the holdout
seed % 5 == 0 prevents exact material-identity leakage, but train and test still share the same procedural recipes, shader, HDRI selection logic and phone augmentation. That mainly measures interpolation within the generator.
Reserve entire:
- texture-generator families;
- glass taxa;
- HDRIs and background scenes;
- camera-pipeline presets;
- capture geometries.
The final gate should be untouched real phone captures from intended users. Synthetic identity holdout remains useful, but it is not a sim-to-real test.

### Use real pairs during training, not only evaluation
You already have 145 screened cross-capture pairs across 64 products, although the branch correctly documents their brand and storefront-style biases. See the real-pairs dataset.
That is probably more valuable now than another 10,000 synthetic samples. Use train-side pairs for a registered consistency loss or clean-reference adaptation, while keeping the frozen products untouched. I would additionally collect 50–100 cropped photos from actual intended users and phone models solely as an untuned deployment audit.

## Concrete branch issues
The shadow caster is still a blurred arrangement of rectangles representing fingers, and every generated identity receives a shadow/no-shadow pair. Training therefore sees shadows about 50% of the time, with a highly recognizable shape grammar. See the hand mask. Use varied silhouettes and deployment-informed prevalence.
The large-scale launcher does not expose or forward the generator's production options: --gt-b, --gt-aov, --no-tex-dump, --eec, or --specular. A 20k run through render_farm.py would silently omit important supervision and use the larger storage path.
--count 5 still means "the original first five recipes," not coverage of the current 17. It is now a stale validation shortcut.
σ_s is supervised but still not scored by the foundation evaluation. Since the oracle study says it is the dominant missing relighting term, it needs its own held-out metric and structured-background relight score.
Material coverage still lacks iridized/dichroic glass—the branch's own scan estimated it as the largest missing taxon—plus crackle, dew/dimple, reactive-cell and drapery families. Current confetti geometry is also still visibly procedural. These matter, but I rank them below capture-domain realism unless those families dominate your users' uploads.

## What I would do next
Do not render 20k yet. Make a roughly 1k-image "deployment pilot" with:
- complete phone-pipeline presets;
- finite-distance backgrounds;
- mixed front/back illumination and reflections;
- realistic crop perturbations;
- full-sheet plus detail-patch training;
- generator/HDRI/camera-family holdouts.
Train once, then evaluate zero-shot on untouched cropped phone photos and the real cross-capture pairs. Only scale if it improves registered consistency without flattening texture and its confidence reliably identifies clear-glass failures.
The short version: you have invested deeply in glass physics and material taxonomy. The weak side is now the camera, the scene around the glass, and the bridge to actual user captures.
