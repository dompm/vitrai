# Report 012 - Artist feedback readout: prettier lie risk

Date: 2026-07-09. Prototype:
`prototypes/material-v2-artist-demo.html`.

## 0. TL;DR

The artist-review subagent liked the Material-v2 direction, but flagged the
right product danger:

> Make it beautiful, but keep it honest.

Her read is that relief/normal rendering is more faithful to stained glass than
flat color transport because stained glass is surface plus light, not just tint.
But the preview becomes untrustworthy if it silently invents surface texture and
lets the artist believe it came from the actual uploaded sheet.

I updated the prototype so the v2 pane now carries a visible **Relief Source**
control and **Truth Check** badge. The current demo says "plausible prior";
"sheet-derived" is shown as the research target, not as a present capability.

## 1. What felt true

The artist's strongest positive read:

- relief/normal rendering is the right ambition;
- lighting direction matters;
- haze/translucency matters;
- preview background matters;
- glass classes should behave differently.

This supports the high-risk Material-v2 thesis from report 010: the app should
not stop at `T,h` if the product goal is a believable glass preview.

## 2. What felt fake

The main fake-risk is not "the math is wrong." It is taste and trust:

- too much glint reads as plastic/resin;
- too much procedural relief reads decorative, not sheet-specific;
- invented texture may look better than the real sheet in a way that misleads
  the artist;
- evaluating the material outside an actual panel context may overrate pretty
  standalone swatches.

This points to restraint. The renderer should probably default to subtle relief
and let inspection modes show stronger lensing/glints.

## 3. Product trust rule

The key question she would ask is:

> Is this derived from the real sheet, or invented?

That becomes a design rule:

> Vitrai may use a class-conditioned relief prior, but it should not hide that
> provenance when the prior materially changes the preview.

Possible product states:

- **Sheet-derived** - measured/inferred from the uploaded image with confidence.
- **Plausible prior** - class/style prior used because the photo does not contain
  enough evidence.
- **Artist tuned** - manual adjustment by the user.

The research model can still predict a plausible height map, but the product
should know and expose how much confidence it has.

## 4. Prototype update

`material-v2-artist-demo.html` now includes:

- `Relief Source` select with `Plausible prior`, `Artist tuned`, and disabled
  `Sheet-derived`;
- a `Truth Check` badge that repeats the active source;
- a feedback checkbox for `Needs source label`;
- notes payload now records `relief_source`.

This is intentionally small, but it changes the conversation: we are no longer
only asking "which render looks prettier?" We are asking "which render would you
trust when choosing glass?"

## 5. Research implications

Add a provenance/confidence head to the high-risk model track:

```text
T_rgb, h, height, source_shadow, source_background_leakage, relief_confidence
```

`relief_confidence` should answer whether the height map is image-supported or
mostly prior-driven. That matters because the exact same visual preview may be
acceptable in one mode and dishonest in another.

Evaluation should include:

- preview realism;
- preview consistency;
- height plausibility;
- source/provenance calibration;
- artist trust.

## 6. Bigger picture

The artist is pushing us toward a more interesting product definition:

> Better than copied pixels is not enough. Better means more faithful, more
> useful, and more legible about uncertainty.

The conservative path would be to ship a cleaner relight. The bold path is to
render actual glass behavior while telling the user which parts are measured and
which parts are inferred.
