# Report 011 - Artist review prototype

Date: 2026-07-09. Prototype:
`prototypes/material-v2-artist-demo.html`.

## 0. TL;DR

I made a small artist-facing prototype for the Material-v2 direction.

It is not a product screen and not a scientific benchmark. It is a lunch-table
artifact: three render panes that let a stained glass artist compare:

1. copied upload pixels with capture shadow/background baked in;
2. `T,h` material relighting;
3. relief/normal relighting with background warping and glints.

The point is to invite artist feedback before we accidentally optimize the
research toward a technically clean but emotionally flat glass preview.

## 1. Why this exists

The core product promise is not "estimate maps." The promise is:

> A stained glass artist can see what a chosen sheet will feel like in the
> finished work.

Report 010 argued that `T,h` is probably too small a material representation
because it has no place for relief, lensing, or surface sparkle. This prototype
turns that argument into something an artist can judge without knowing the
research.

If she says the v2 pane feels more like real glass, that supports the
height/normal track. If she says it feels plastic, fake, over-textured, or
unhelpful for choosing sheets, that is equally valuable.

## 2. Prototype design

The HTML file is standalone and procedural. It does not need the app server.

Controls:

- glass type: amber cathedral, green cathedral, wispy white, blue streaky, dark
  opaque;
- preview background: lead/studio, shop window, work bench, warm lamp;
- relief;
- haze;
- glints;
- light angle;
- shuffle seed.

It includes a small notes panel with artist-read checkboxes:

- looks like real glass;
- still feels flat;
- too plastic/glossy;
- texture too busy;
- would help choose a sheet.

These are deliberately taste-level, not metric-level.

## 3. What I would show her

I would avoid explaining the neural model or the material channels at first.

Show the same glass in three panes and ask:

1. Which one would make you more confident choosing this sheet?
2. What looks fake?
3. What is missing from the glass you buy and cut?
4. Does the relief help, or does it make the sheet feel synthetic?
5. Would you want this control exposed, or should Vitrai choose it for you?

Then I would reveal that the third pane comes from a richer material
representation. The order matters: first taste, then explanation.

## 4. Research implications

Artist feedback can change the high-risk track in four ways:

- **Relief strength.** If subtle relief wins, the app should bias toward
  conservative lensing and only push glints in inspection modes.
- **Glass-class priors.** If she expects cathedral, wispy, and streaky sheets to
  behave differently, class conditioning is not just a model crutch; it matches
  artist perception.
- **Preview backgrounds.** If she cares most about seeing glass over lead lines,
  the product metric should weight lead/contrast backgrounds more heavily. If
  she cares about natural window light, the metric should include that too.
- **Taste over reconstruction.** A plausible relief prior may be product-good
  even when it is not the exact physical surface from the uploaded photo.

That last point is important. A strict inverse-rendering paper wants the true
height map. Vitrai may only need a stable, plausible, class-correct surface that
helps the artist imagine the finished panel.

## 5. Risks

- The demo uses procedural materials, not real uploaded sheets.
- It can overstate the v2 idea because the relief is authored cleanly.
- It can understate the v2 idea because it is a cheap 2D screen-space renderer,
  not Blender/Cycles or the future app shader.
- One artist's taste is not the market.

So the readout should be directional:

> Does relief/lensing belong in the product target?

Not:

> Did we tune the final renderer?

## 6. Verification

Done:

- Inline JavaScript parse check with the bundled Node runtime.
- Static check that the key controls/canvases exist.

Not done:

- Browser screenshot verification. The bundled Playwright package is present,
  but the Chromium binary is not installed in this environment.

