- **Documentation:** Preserve non-obvious current constraints, intent, and recurring failure boundaries that code, types, or tests do not make clear. Prefer executable contracts over prose copies. Put necessary rationale beside the relevant code or task guidance. Remove obsolete guidance rather than accumulating decision history. Do not narrate code, repeat typed signatures, or preserve working plans as permanent documentation.

- **PR descriptions:** Lead with 2–3 narrative sentences explaining context and intent for a reviewer who knows the system but hasn't seen the code. Avoid line-by-line diff narration. Cover: gap addressed, key tradeoff accepted, and explicit non-goals. Include before/after visual captures if UI/output changed.

- **Real tests over mocks:** Prefer integration tests against real infrastructure/containers. Limit mocks to external third-party services or legitimately hard-to-reproduce failure states; never mock internal boundaries or datastores just to keep tests green.

- **Design Vocabulary:** Tactile craft atelier — warm gallery stone and paper surfaces, deep espresso-charcoal ink, and burnished brass accents, pairing editorial serif headings with quiet, high-density studio controls. Work canvases act as a low-saturation gallery matboard so the stained glass itself carries the color and visual weight.
