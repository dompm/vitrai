# Testing Guide

Vitrai uses Vitest for unit/geometry testing and Playwright for deterministic browser regression checks.

## Unit Tests

Unit tests cover vector math, snapping algorithms, lamp unrolling geometry, and state stores.

```bash
cd frontend
pnpm test
```

To run a specific test suite:
```bash
pnpm test src/editor/__tests__/penSnapIndex.test.ts
```

## Type Checking

```bash
cd frontend
pnpm typecheck
```

## Tutorial Regression Checks (Chromium)

Vitrai includes a deterministic end-to-end browser suite that verifies all four onboarding tracks (Draw from Scratch, Trace from a Photo, Create a 3D Lamp, and Prepare for Cutting), popovers, highlight geometry, reload durability, and 1:1 printing.

1. Install the Playwright Chromium browser:
   ```bash
   cd frontend
   pnpm exec playwright install chromium
   ```

2. Start the development server in one terminal:
   ```bash
   pnpm dev
   ```

3. Run the tutorial test suite in another terminal:
   ```bash
   pnpm test:tutorial
   ```

### Custom URL

By default, the runner targets `http://127.0.0.1:5173`. To test a remote or staging preview:
```bash
TUTORIAL_URL="https://your-preview.pages.dev" pnpm test:tutorial
```

> **Note:** The smoke test deterministically mocks the SAM2 ONNX runtime backend to avoid downloading the ~100MB model in CI. When modifying AI tracing, also manually verify tracing with real inference.

## Regenerating README Screenshots

After UI changes, regenerate the `docs/assets/readme-*.png` screenshots with:

```bash
cd frontend
pnpm screenshots:readme
```

