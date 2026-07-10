# Report 019 - Luma quotient falsifies the weak neural cleanup

Date: 2026-07-10. Code: `luma_quotient_prior.py`.

## 0. TL;DR

I sanity-checked report 018's luma-only neural cleaner against a deterministic
representation:

```text
logY = smooth_logY + detail_logY
output = input * exp(-alpha * (smooth_logY - median_smooth_logY))
```

It preserves uploaded chroma/hue and high-frequency relief. It only removes a
smooth brightness field.

On the real tutorial suncatcher, this simple quotient beats both neural cleaners.
That is not a product conclusion. It is a research warning: the neural model in
reports 017-018 was spending capacity rediscovering a low-frequency quotient,
not learning the hard glass physics.

## 1. Result

Real suncatcher position sensitivity:

| condition | mean dE | luminance CV | hue std deg |
|---|---:|---:|---:|
| raw | 8.98 | 0.407 | 1.5 |
| fixed `T/h` | 10.12 | 0.318 | 1.7 |
| luma quotient `alpha=0.25` | 8.30 | 0.255 | 1.7 |
| luma quotient `alpha=0.50` | 6.42 | 0.189 | 1.7 |
| luma quotient `alpha=0.75` | 4.68 | 0.120 | 1.7 |
| luma quotient `alpha=1.00` | 3.18 | 0.056 | 1.7 |
| hand sheet prior | 1.90 | 0.060 | 0.3 |

Neural comparison after fixed `T/h`:

| model | mean dE | luminance CV | hue std deg |
|---|---:|---:|---:|
| luma neural | 9.34 | 0.291 | 1.7 |
| RGB smooth neural | 9.24 | 0.261 | 2.1 |
| luma quotient `alpha=1.00` | 3.18 | 0.056 | 1.7 |

The hand sheet prior still wins dE because it also collapses chroma variation.
The quotient keeps the uploaded color field and removes only smooth brightness
variation, so it cannot solve true chroma/background disentanglement.

## 2. Research read

The quotient is a baseline that the neural track now has to beat.

It says:

- broad luma cleanup is not the hard problem;
- a smooth field plus log-luminance quotient is already extremely strong on the
  tutorial cathedral sheet;
- if a network cannot beat this, it is not learning glass physics;
- the remaining hard problem is chroma/refraction/background separation.

This changes my research allocation. I should not spend more time training
catalog-only networks to remove exposure fields. The next bold work should model
the missing variables directly:

- a background/leakage layer `B(x)`;
- a refraction/displacement field from relief/normal;
- chromatic attenuation `T(x)` separate from scene color behind the glass;
- a renderer that recomposes the observed sheet and penalizes leakage entering
  the material map.

## 3. Why this matters for the neural track

The neural cleaner should not spend capacity learning a quotient. Instead:

- use the quotient as a fixed baseline in every future benchmark;
- train on rendered/paired data where background leakage has known ground truth;
- predict `T`, relief/normal, `B`, and displacement, then force them through a
  renderer;
- evaluate whether the output remains stable when pieces move across the sheet.

## 4. Bet audit consequence

This is a useful failure of Bet C as currently implemented.

I did **not** yet build the real transparent-background disentangler. I built:

```text
catalog weak supervision -> RGB/luma cleanup -> quotient baseline
```

The quotient beating the learned luma cleaner means the next attempt must be
more ambitious, not safer:

```text
rendered glass with known background + known relief -> inverse model predicts
T, normal/displacement, leakage B -> renderer recomposition loss
```

That is the version that can actually attack the thing the app cannot do today:
look at a hammered cathedral sheet over a garden/window and decide what belongs
to the glass versus what belongs behind it.

## 5. Files

- `luma_quotient_prior.py`
- `results/luma_quotient_prior/summary_table.md`
- `results/luma_quotient_prior/metrics.json`
- `results/luma_quotient_prior/sheet_contact.jpg`
