// Run with Vite listening on TUTORIAL_URL (default http://127.0.0.1:5173).
// SAM is deferred deterministically here; also exercise real SAM manually before release.
import assert from 'node:assert/strict';
import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true, args: ['--enable-unsafe-swiftshader'],
  ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}),
});
const url = process.env.TUTORIAL_URL || 'http://127.0.0.1:5173';
const contexts = [];
const errors = [];
async function fresh(track, viewport = { width: 1440, height: 1000 }) {
  const context = await browser.newContext({ viewport, locale: 'en-US' });
  contexts.push(context);
  await context.addInitScript(() => {
    window.__samBackend = {
      encode: async () => 'smoke-test-image',
      segment: () => new Promise(resolve => {
        window.__finishTutorialSegmentation = () => resolve({ polygon: [[1000, 1600], [2300, 2200], [1500, 2800]] });
      }),
    };
  });
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(url);
  await page.getByRole('button', { name: new RegExp(track) }).click();
  await page.getByRole('button', { name: 'Start Guide', exact: true }).click();
  return page;
}
const step = (page, id) => page.locator(`[data-tutorial-step="${id}"]`).waitFor();
const tool = (page, id, panel = 'pattern') => page.locator(`[data-tutorial-panel="${panel}"] [data-tool-id="${id}"]`).click();
async function ring(page, selector) {
  // Wait for a frame after layout / ResizeObserver / animation updates.
  await page.waitForFunction(selector => {
    const target = document.querySelector(selector), ring = document.querySelector('.tutorial-spotlight-pulse');
    if (!target || !ring) return false;
    const a = target.getBoundingClientRect(), b = ring.getBoundingClientRect();
    return Math.abs(b.x - (a.x - 4)) < 1 && Math.abs(b.y - (a.y - 4)) < 1 &&
      Math.abs(b.width - (a.width + 8)) < 1 && Math.abs(b.height - (a.height + 8)) < 1;
  }, selector);
}
async function point(page, x, y, width = 1000, height = 1000) {
  const box = await page.locator('[data-tutorial-panel="pattern"] .canvas-well').boundingBox();
  const scale = Math.min(box.width / width, box.height / height);
  return [box.x + (box.width - width * scale) / 2 + x * scale,
    box.y + (box.height - height * scale) / 2 + y * scale];
}
async function clickPoint(page, x, y, w, h) { await page.mouse.click(...await point(page, x, y, w, h)); }
async function draw(page, points, w, h) {
  for (const [x, y] of points) await clickPoint(page, x, y, w, h);
  await page.keyboard.press('Enter');
}
try {
  const vector = await fresh('Draw from Scratch');
  await step(vector, 'vector-blank-canvas');
  await ring(vector, '[data-tutorial-panel="pattern"] [data-tool-id="pen"]');
  await tool(vector, 'pen');
  await step(vector, 'vector-draw-shape');
  // Deliberately ignore the suggested triangle. Handles must follow the user's shape.
  await draw(vector, [[200, 200], [550, 200], [550, 550], [200, 550]]);
  await step(vector, 'vector-snap-angles');
  await tool(vector, 'select');
  await step(vector, 'vector-curve-edge');
  await vector.mouse.move(...await point(vector, 375, 200));
  await vector.mouse.down();
  await vector.mouse.move(...await point(vector, 375, 120), { steps: 12 });
  await vector.mouse.up();
  await vector.getByRole('button', { name: 'Continue', exact: true }).click();
  await step(vector, 'vector-assign-glass');
  await ring(vector, '[data-tutorial-target="piece-glass-select"]');
  await vector.locator('[data-tutorial-target="piece-glass-select"]').selectOption('default-sheet-2');
  await step(vector, 'vector-position-texture');
  // The UI deliberately delays its saving indicator to avoid flicker. Wait for
  // durable OPFS data, rather than mistaking the previous Saved label for a flush.
  const saveDeadline = Date.now() + 10000;
  while (!await vector.evaluate(async () => {
    const { loadProjectFromOPFS } = await import('/src/storage/opfs.ts');
    const saved = await loadProjectFromOPFS('Tutorial');
    const state = JSON.parse(localStorage.getItem('vitrai-tutorial-state'));
    return saved?.pieces.some(p => p.id === state.pieceId && p.glassSheetId === 'default-sheet-2');
  })) {
    assert.ok(Date.now() < saveDeadline, 'Practice piece should persist before reload');
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  await vector.reload();
  await step(vector, 'vector-position-texture');
  await vector.getByRole('button', { name: 'Select my piece', exact: true }).click();
  await ring(vector, '[data-tutorial-panel="glass"] .canvas-well');
  await vector.getByRole('button', { name: 'Texture placed', exact: true }).click();
  await vector.getByRole('button', { name: 'Try Another Guide', exact: true }).waitFor();
  console.log('PASS drawing: arbitrary shape, curves, assignment, reload recovery, completion');

  const lamp = await fresh('Create a 3D Lamp', { width: 1280, height: 800 });
  await lamp.locator('[data-tutorial-target="lamp-profile-button"]').click();
  await step(lamp, 'lamp-edit-profile');
  await ring(lamp, '[data-tutorial-target="lamp-profile-editor"]');
  await lamp.getByRole('button', { name: 'Cancel', exact: true }).click();
  await step(lamp, 'lamp-profile-intro');
  await lamp.locator('[data-tutorial-target="lamp-profile-button"]').click();
  await lamp.getByRole('button', { name: 'Save', exact: true }).click();
  await step(lamp, 'lamp-symmetry');
  await ring(lamp, '[data-tutorial-target="lamp-symmetry-button"]');
  await lamp.locator('[data-tutorial-target="lamp-symmetry-button"]').click();
  await step(lamp, 'lamp-choose-pen');
  await tool(lamp, 'pen');
  await step(lamp, 'lamp-draw-facet');
  const shape = await lamp.evaluate(async () => {
    const { computeUnrolledLamp } = await import('/src/utils/lampGeometry.ts');
    const layout = computeUnrolledLamp({ facetCount: 6, profilePoints: [{ r: 50, y: 0 }, { r: 100, y: 80 }, { r: 100, y: 140 }], activeTierIndex: 0 });
    const strip = layout.strips[0], tier = strip.tiers[0];
    const half = Math.min(tier.topChord, tier.botChord) * .3;
    const top = tier.topY + (tier.botY - tier.topY) * .2;
    return { width: layout.width, height: layout.height, points: [[strip.centerX - half, top], [strip.centerX + half, top], [strip.centerX, tier.topY + (tier.botY - tier.topY) * .8]] };
  });
  await draw(lamp, shape.points, shape.width, shape.height);
  await step(lamp, 'lamp-preview-3d');
  assert.match(await lamp.locator('.status-bar').innerText(), /6 pieces/);
  await ring(lamp, '[data-tutorial-target="lamp-3d-preview"]');
  await lamp.getByRole('button', { name: 'Complete guide', exact: true }).click();
  console.log('PASS lamp: editor target, Cancel vs Save, symmetry BEFORE drawing, six pieces');

  const cutting = await fresh('Prepare for Cutting');
  await step(cutting, 'fab-smart-pack');
  await cutting.locator('[data-tutorial-target="smart-pack-button"]').click();
  await ring(cutting, '[data-tutorial-target="start-packing"]');
  await cutting.locator('[data-tutorial-target="start-packing"]').click();
  await step(cutting, 'fab-solder-thickness');
  assert.equal(await cutting.getByRole('button', { name: 'Continue', exact: true }).isEnabled(), false);
  await cutting.locator('[data-tutorial-target="solder-settings"]').click();
  await ring(cutting, '[data-tutorial-target="solder-slider"]');
  await cutting.locator('[data-tutorial-target="solder-slider"]').fill('6');
  await cutting.locator('[data-tutorial-target="solder-settings"]').click();
  await cutting.getByRole('button', { name: 'Continue', exact: true }).click();
  await step(cutting, 'fab-print-layout');
  const popupPromise = cutting.waitForEvent('popup');
  await cutting.locator('[data-tutorial-target="print-button"]').click();
  const popup = await popupPromise;
  await popup.waitForLoadState('domcontentloaded');
  assert.equal(await popup.locator('.page').count(), 1);
  await popup.close();
  await cutting.getByRole('button', { name: 'Complete guide', exact: true }).click();
  console.log('PASS cutting: popover targets, successful nesting, solder slider, physical print size');

  const tracing = await fresh('Trace from a Photo');
  await step(tracing, 'calibrate-pattern');
  await tool(tracing, 'measure');
  await tool(tracing, 'measure');
  await step(tracing, 'cut-first-piece');
  await tool(tracing, 'box');
  await tracing.mouse.move(...await point(tracing, 924, 1487, 3072, 4080));
  await tracing.mouse.down();
  await tracing.mouse.move(...await point(tracing, 2505, 2999, 3072, 4080), { steps: 12 });
  await tracing.mouse.up();
  await tracing.waitForFunction(() => typeof window.__finishTutorialSegmentation === 'function');
  await step(tracing, 'cut-first-piece'); // Must not progress on the temporary rectangular placeholder.
  await tracing.evaluate(() => window.__finishTutorialSegmentation());
  await step(tracing, 'refine-first-piece');
  await tracing.getByRole('button', { name: 'Looks good — continue', exact: true }).click();
  await step(tracing, 'assign-first-glass');
  await tracing.locator('[data-tutorial-target="piece-glass-select"]').selectOption('sheet-2');
  await step(tracing, 'position-first-texture');
  await tracing.getByRole('button', { name: 'Texture placed', exact: true }).click();
  console.log('PASS tracing: pending inference gate, user accepts outline, complete one-piece workflow');

  assert.deepEqual(errors, [], 'No browser runtime errors');
} catch (error) {
  for (const context of contexts) for (const p of context.pages()) console.error('FAILURE UI', await p.locator('body').innerText(), await p.evaluate(() => ({...localStorage})));
  throw error;
} finally {
  await Promise.all(contexts.map(context => context.close()));
  await browser.close();
}
