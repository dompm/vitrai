import { spawn } from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const TARGET_URL = process.env.SCREENSHOT_URL || 'http://127.0.0.1:5173';
const parsedUrl = new URL(TARGET_URL);
const PORT = parsedUrl.port || '5173';
const OUTPUT_DIR = path.resolve(__dirname, '../../docs/assets');

fs.mkdirSync(OUTPUT_DIR, { recursive: true });

let viteProcess = null;

function checkServer(url) {
  return new Promise((resolve) => {
    http.get(url, (res) => {
      resolve(res.statusCode === 200);
    }).on('error', () => resolve(false));
  });
}

async function ensureServer() {
  const isUp = await checkServer(TARGET_URL);
  if (isUp) {
    console.log(`Using existing server at ${TARGET_URL}`);
    return;
  }

  console.log(`No server found at ${TARGET_URL}. Starting Vite dev server on port ${PORT}...`);
  const frontendDir = path.resolve(__dirname, '..');
  viteProcess = spawn('pnpm', ['exec', 'vite', '--port', PORT, '--host', '127.0.0.1'], {
    cwd: frontendDir,
    stdio: 'inherit',
  });

  const start = Date.now();
  while (Date.now() - start < 30000) {
    if (await checkServer(TARGET_URL)) {
      console.log(`Vite server ready at ${TARGET_URL}`);
      return;
    }
    await new Promise(r => setTimeout(r, 300));
  }
  throw new Error(`Failed to start Vite server at ${TARGET_URL} within 30s`);
}

function cleanupServer() {
  if (viteProcess) {
    console.log('Stopping spawned Vite server...');
    viteProcess.kill('SIGTERM');
    viteProcess = null;
  }
}

async function waitForAssetsLoaded(page) {
  await page.waitForLoadState('networkidle');
  await page.evaluate(async () => {
    const images = Array.from(document.querySelectorAll('img'));
    await Promise.all(images.map(img => {
      if (img.complete) return Promise.resolve();
      return new Promise(resolve => {
        img.onload = resolve;
        img.onerror = resolve;
      });
    }));
  });
  await new Promise(r => setTimeout(r, 1000));
}

/**
 * Cohesive 9-pane 3-color geometric stained glass window panel (800x800, centered at [100..900, 100..900])
 */
function createHeroWindowProject(solderWidthMM = 4.5) {
  return {
    version: 1,
    name: 'Stained Glass Panel',
    solderWidthMM,
    solderColor: 'black',
    patternImageUrl: '',
    patternWidth: 1000,
    patternHeight: 1000,
    patternCrop: { top: 0, left: 0, bottom: 0, right: 0 },
    patternScale: { pxPerUnit: 100, unit: 'in', line: { x1: 0, y1: 0, x2: 100, y2: 0 } },
    pieces: [
      // 4 Outer Border Frame Trapezoids (Cobalt Blue - sheet-1)
      {
        id: 'frame-top',
        label: 'Frame Top',
        polygon: [[100, 100], [900, 100], [780, 220], [220, 220]],
        glassSheetId: 'sheet-1',
        transform: { x: 500, y: 160, rotation: 0, scale: 0.45 },
      },
      {
        id: 'frame-right',
        label: 'Frame Right',
        polygon: [[900, 100], [900, 900], [780, 780], [780, 220]],
        glassSheetId: 'sheet-1',
        transform: { x: 500, y: 400, rotation: 0, scale: 0.45 },
      },
      {
        id: 'frame-bottom',
        label: 'Frame Bottom',
        polygon: [[900, 900], [100, 900], [220, 780], [780, 780]],
        glassSheetId: 'sheet-1',
        transform: { x: 500, y: 600, rotation: 0, scale: 0.45 },
      },
      {
        id: 'frame-left',
        label: 'Frame Left',
        polygon: [[100, 900], [100, 100], [220, 220], [220, 780]],
        glassSheetId: 'sheet-1',
        transform: { x: 200, y: 400, rotation: 0, scale: 0.45 },
      },
      // Central Diamond (Amber Glass - sheet-2)
      {
        id: 'center-diamond',
        label: 'Center Diamond',
        polygon: [[500, 320], [680, 500], [500, 680], [320, 500]],
        glassSheetId: 'sheet-2',
        transform: { x: 400, y: 400, rotation: 0, scale: 0.45 },
      },
      // 4 Inner Corner Panes (Emerald Green - sheet-3)
      {
        id: 'corner-top-left',
        label: 'Top-Left Corner',
        polygon: [[220, 220], [500, 220], [500, 320], [320, 500], [220, 500]],
        glassSheetId: 'sheet-3',
        transform: { x: 250, y: 250, rotation: 0, scale: 1.0 },
      },
      {
        id: 'corner-top-right',
        label: 'Top-Right Corner',
        polygon: [[500, 220], [780, 220], [780, 500], [680, 500], [500, 320]],
        glassSheetId: 'sheet-3',
        transform: { x: 550, y: 250, rotation: 0, scale: 1.0 },
      },
      {
        id: 'corner-bottom-right',
        label: 'Bottom-Right Corner',
        polygon: [[780, 500], [780, 780], [500, 780], [500, 680], [680, 500]],
        glassSheetId: 'sheet-3',
        transform: { x: 550, y: 550, rotation: 0, scale: 1.0 },
      },
      {
        id: 'corner-bottom-left',
        label: 'Bottom-Left Corner',
        polygon: [[500, 780], [220, 780], [220, 500], [320, 500], [500, 680]],
        glassSheetId: 'sheet-3',
        transform: { x: 250, y: 550, rotation: 0, scale: 1.0 },
      },
    ],
    sheets: [
      {
        id: 'sheet-1',
        label: 'Cobalt Blue Glass',
        imageUrl: '/assets/glass/blue.jpg',
        crop: { top: 0, left: 0, bottom: 0, right: 0 },
        scale: { pxPerUnit: 800 / 12, unit: 'in', line: { x1: 0, y1: 400, x2: 800, y2: 400 } },
        naturalWidth: 800,
        naturalHeight: 800,
        swatch: '#1e88e5',
      },
      {
        id: 'sheet-2',
        label: 'Amber Orange Glass',
        imageUrl: '/assets/glass/orange.jpg',
        crop: { top: 0, left: 0, bottom: 0, right: 0 },
        scale: { pxPerUnit: 800 / 12, unit: 'in', line: { x1: 0, y1: 400, x2: 800, y2: 400 } },
        naturalWidth: 800,
        naturalHeight: 800,
        swatch: '#fb8c00',
      },
      {
        id: 'sheet-3',
        label: 'Emerald Green Glass',
        imageUrl: '/assets/glass/green.jpg',
        crop: { top: 0, left: 0, bottom: 0, right: 0 },
        scale: { pxPerUnit: 100, unit: 'in', line: { x1: 0, y1: 400, x2: 800, y2: 400 } },
        naturalWidth: 800,
        naturalHeight: 800,
        swatch: '#4caf50',
      },
    ],
  };
}

async function loadProjectIntoPage(page, project) {
  await page.evaluate(async (p) => {
    const { saveToOPFS } = await import('/src/storage/opfs.ts');
    await saveToOPFS(p, p.name);
    localStorage.setItem('vitraux-last-project', p.name);
    localStorage.setItem('vitrai-tutorial-state', JSON.stringify({ completed: true, step: null, activeTrackId: null }));
  }, project);

  await page.reload();
  await waitForAssetsLoaded(page);

  const statusText = await page.locator('.status-bar').innerText().catch(() => '');
  if (statusText.includes('0 pieces')) {
    const tmpFile = path.join(OUTPUT_DIR, 'tmp-project-load.json');
    fs.writeFileSync(tmpFile, JSON.stringify(project));
    const fileInput = page.locator('input[type="file"][accept*="json"]').first();
    if (await fileInput.count() > 0) {
      await fileInput.setInputFiles(tmpFile);
      await new Promise(r => setTimeout(r, 800));
    }
    fs.unlinkSync(tmpFile);
  }
}

async function main() {
  try {
    await ensureServer();

    const chromePath = process.env.CHROMIUM_PATH ||
      (fs.existsSync('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
        ? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
        : undefined);

    const launchOptions = {
      headless: true,
      args: ['--enable-unsafe-swiftshader'],
      ...(chromePath ? { executablePath: chromePath } : {}),
    };

    const browser = await chromium.launch(launchOptions);

    // ------------------------------------------------------------------------
    // SCREENSHOT 1: docs/assets/readme-hero.png
    // ------------------------------------------------------------------------
    console.log('\n--- Generating Screenshot 1: readme-hero.png ---');
    {
      const context = await browser.newContext({
        viewport: { width: 1440, height: 900 },
        deviceScaleFactor: 2,
        locale: 'en-US',
      });
      const page = await context.newPage();
      await page.goto(TARGET_URL);

      const heroProject = createHeroWindowProject(4.5);
      await loadProjectIntoPage(page, heroProject);

      // Select Emerald Green Glass tab so Smart Pack packs the 4 green corner pieces cleanly
      await page.evaluate(() => {
        const tab = Array.from(document.querySelectorAll('.sheet-tab')).find(el => el.textContent.includes('Emerald Green'));
        if (tab) tab.click();
      });
      await new Promise(r => setTimeout(r, 200));

      // Run Smart Pack
      const packBtn = page.locator('[data-tutorial-target="smart-pack-button"]');
      if (await packBtn.isVisible()) {
        await packBtn.click();
        await new Promise(r => setTimeout(r, 300));
        const startPackingBtn = page.locator('[data-tutorial-target="start-packing"]');
        if (await startPackingBtn.isVisible()) {
          await startPackingBtn.click();
          await new Promise(r => setTimeout(r, 1200));
        }
      }

      await page.keyboard.press('Escape');
      await new Promise(r => setTimeout(r, 300));

      const sheetCanvas = page.locator('[data-tutorial-panel="glass"] .canvas-well');
      if (await sheetCanvas.isVisible()) {
        const box = await sheetCanvas.boundingBox();
        if (box) {
          await page.mouse.click(box.x + box.width * 0.4, box.y + box.height * 0.4);
        }
      }

      await waitForAssetsLoaded(page);

      const status = await page.locator('.status-bar').innerText().catch(() => '');
      console.log('Hero Status Bar:', status);

      const heroPath = path.join(OUTPUT_DIR, 'readme-hero.png');
      await page.screenshot({ path: heroPath, fullPage: false });
      console.log(`Saved ${heroPath} (${fs.statSync(heroPath).size} bytes)`);
      await context.close();
    }

    // ------------------------------------------------------------------------
    // SCREENSHOT 2: docs/assets/readme-tracing.png
    // ------------------------------------------------------------------------
    console.log('\n--- Generating Screenshot 2: readme-tracing.png ---');
    {
      const context = await browser.newContext({
        viewport: { width: 1440, height: 900 },
        deviceScaleFactor: 2,
        locale: 'en-US',
      });
      const page = await context.newPage();
      await page.goto(TARGET_URL);

      const scaleConfig = { pxPerUnit: 1300 / 12, unit: 'in', line: { x1: 758, y1: 768, x2: 2058, y2: 768 } };

      const tracingProject = {
        version: 1,
        name: 'Orange Pattern Project',
        patternImageUrl: '/assets/orange-pattern.jpg',
        patternWidth: 3072,
        patternHeight: 4080,
        patternCrop: { top: 0, left: 0, bottom: 0, right: 0 },
        patternScale: { pxPerUnit: 216, unit: 'in', line: { x1: 758, y1: 768, x2: 2058, y2: 768 } },
        pieces: [
          {
            id: 'orange-body',
            label: 'Orange Body',
            polygon: [[1474, 1446], [1956, 1968], [2526, 2227], [2494, 2411], [2267, 2717], [2120, 2849], [1869, 2972], [1434, 2980], [1155, 2845], [916, 2558], [845, 2367], [1076, 2020], [1175, 1614]],
            glassSheetId: 'sheet-2',
            transform: { x: 1400, y: 768, rotation: 0, scale: 0.5 },
          },
          {
            id: 'top-right-leaf',
            label: 'Top-Right Leaf',
            polygon: [[1514, 1375], [1940, 1311], [2303, 1367], [2510, 1478], [2705, 1713], [2913, 2092], [2913, 2140], [2460, 2197], [2072, 2021], [1821, 1821]],
            glassSheetId: 'sheet-1',
            transform: { x: 1350, y: 650, rotation: 0, scale: 0.5 },
          },
          {
            id: 'left-leaf',
            label: 'Left Leaf',
            polygon: [[398, 2112], [410, 2056], [558, 1972], [713, 1829], [996, 1387], [1084, 1406], [1167, 1578], [1055, 2051], [852, 2356], [769, 2367], [422, 2729], [398, 2685]],
            glassSheetId: 'sheet-1',
            transform: { x: 950, y: 650, rotation: 0, scale: 0.5 },
          },
          {
            id: 'upper-left-leaf',
            label: 'Upper-Left Leaf',
            polygon: [[128, 2148], [139, 2020], [207, 1813], [426, 1355], [590, 1231], [849, 1144], [972, 1032], [1040, 1040], [1056, 1112], [1013, 1386], [970, 1428], [680, 1829], [558, 1972], [410, 2056], [398, 2112]],
            glassSheetId: 'sheet-1',
            transform: { x: 1400, y: 1050, rotation: 0, scale: 0.5 },
          },
        ],
        sheets: [
          {
            id: 'sheet-1',
            label: 'Verde Light Green Glass',
            imageUrl: '/assets/green.jpg',
            crop: { top: 0, left: 0, bottom: 0, right: 0 },
            scale: scaleConfig,
            naturalWidth: 2816,
            naturalHeight: 1536,
            swatch: '#a5d6a7',
          },
          {
            id: 'sheet-2',
            label: 'Amber Orange Glass',
            imageUrl: '/assets/orange.jpg',
            crop: { top: 0, left: 0, bottom: 0, right: 0 },
            scale: scaleConfig,
            naturalWidth: 2816,
            naturalHeight: 1536,
            swatch: '#fb8c00',
          },
        ],
      };

      await loadProjectIntoPage(page, tracingProject);

      // Select orange piece on pattern canvas
      const patternCanvas = page.locator('[data-tutorial-panel="pattern"] .canvas-well');
      if (await patternCanvas.isVisible()) {
        const box = await patternCanvas.boundingBox();
        if (box) {
          await page.mouse.click(box.x + box.width * 0.58, box.y + box.height * 0.55);
        }
      }

      await waitForAssetsLoaded(page);

      const status = await page.locator('.status-bar').innerText().catch(() => '');
      console.log('Tracing Status Bar:', status);

      const tracingPath = path.join(OUTPUT_DIR, 'readme-tracing.png');
      await page.screenshot({ path: tracingPath, fullPage: false });
      console.log(`Saved ${tracingPath} (${fs.statSync(tracingPath).size} bytes)`);
      await context.close();
    }

    // ------------------------------------------------------------------------
    // SCREENSHOT 3: docs/assets/readme-lamp.png
    // ------------------------------------------------------------------------
    console.log('\n--- Generating Screenshot 3: readme-lamp.png ---');
    {
      const context = await browser.newContext({
        viewport: { width: 1440, height: 900 },
        deviceScaleFactor: 2,
        locale: 'en-US',
      });
      const page = await context.newPage();
      await page.goto(TARGET_URL);

      const lampProject = await page.evaluate(async () => {
        const { computeUnrolledLamp, replicatePointToFacet } = await import('/src/utils/lampGeometry.ts');

        const lampConfig = {
          facetCount: 6,
          profilePoints: [
            { r: 45, y: 0 },
            { r: 95, y: 55 },
            { r: 135, y: 145 },
            { r: 145, y: 195 },
          ],
          activeTierIndex: 0,
        };

        const unrolled = computeUnrolledLamp(lampConfig);
        const strip = unrolled.strips[0];
        const N = 6;

        const pieces = [];

        // Fill the top 2 tiers (12 pieces total) and leave the 3rd bottom tier empty
        // so the 2D-to-3D wireframe mapping is clearly visible.
        for (let tierIdx = 0; tierIdx < 2; tierIdx++) {
          const tier = strip.tiers[tierIdx];
          const poly = [
            [strip.centerX - tier.topChord / 2, tier.topY],
            [strip.centerX + tier.topChord / 2, tier.topY],
            [strip.centerX + tier.botChord / 2, tier.botY],
            [strip.centerX - tier.botChord / 2, tier.botY],
          ];
          const sheetId = tierIdx === 0 ? 'sheet-1' : tierIdx === 1 ? 'sheet-2' : 'sheet-3';
          const group = `sym-group-${tierIdx}`;

          for (let j = 0; j < N; j++) {
            const newPoly = poly.map(([px, py]) => replicatePointToFacet(px, py, 0, j, unrolled, N));
            const col = j % 3;
            const row = Math.floor(j / 3);
            const transform = { x: 150 + col * 250, y: 260 + row * 280, rotation: 0, scale: 1.65 };

            pieces.push({
              id: `lamp-t${tierIdx}-f${j}`,
              label: `Tier ${tierIdx + 1} Facet ${j + 1}`,
              polygon: newPoly,
              glassSheetId: sheetId,
              tierIndex: tierIdx,
              facetIndex: j,
              symmetryGroupId: group,
              transform,
            });
          }
        }

        return {
          version: 1,
          name: '3D Lamp Project',
          projectType: 'lamp',
          lampConfig,
          patternImageUrl: '',
          patternWidth: unrolled.width,
          patternHeight: unrolled.height,
          patternCrop: { top: 0, left: 0, bottom: 0, right: 0 },
          patternScale: { pxPerUnit: 40, unit: 'in', line: { x1: 0, y1: 0, x2: 100, y2: 0 } },
          pieces,
          sheets: [
            {
              id: 'sheet-1',
              label: 'Amber Cathedral Glass',
              imageUrl: '/assets/glass/orange.jpg',
              crop: { top: 0, left: 0, bottom: 0, right: 0 },
              scale: { pxPerUnit: 800 / 12, unit: 'in', line: { x1: 0, y1: 400, x2: 800, y2: 400 } },
              naturalWidth: 800,
              naturalHeight: 800,
              swatch: '#fb8c00',
            },
            {
              id: 'sheet-2',
              label: 'Cobalt Blue Glass',
              imageUrl: '/assets/glass/blue.jpg',
              crop: { top: 0, left: 0, bottom: 0, right: 0 },
              scale: { pxPerUnit: 800 / 12, unit: 'in', line: { x1: 0, y1: 400, x2: 800, y2: 400 } },
              naturalWidth: 800,
              naturalHeight: 800,
              swatch: '#1e88e5',
            },
            {
              id: 'sheet-3',
              label: 'Verde Green Glass',
              imageUrl: '/assets/glass/green.jpg',
              crop: { top: 0, left: 0, bottom: 0, right: 0 },
              scale: { pxPerUnit: 800 / 12, unit: 'in', line: { x1: 0, y1: 400, x2: 800, y2: 400 } },
              naturalWidth: 800,
              naturalHeight: 800,
              swatch: '#4caf50',
            },
          ],
        };
      });

      await loadProjectIntoPage(page, lampProject);

      // Select active sheet to sheet-2 (Cobalt Blue)
      await page.evaluate(() => {
        // Select Cobalt Blue tab if present in tabs
        const tab = Array.from(document.querySelectorAll('.sheet-tab')).find(el => el.textContent.includes('Cobalt Blue'));
        if (tab) tab.click();
      });

      // Click Fit in pattern panel
      const fitBtn = page.locator('[data-tutorial-panel="pattern"] .viewport-fit-button');
      if (await fitBtn.isVisible()) {
        await fitBtn.click();
        await new Promise(r => setTimeout(r, 300));
      }

      // Turn on Symmetry button if present
      const symBtn = page.locator('[data-tutorial-target="lamp-symmetry-button"]');
      if (await symBtn.isVisible()) {
        const pressed = await symBtn.getAttribute('aria-pressed');
        if (pressed !== 'true') await symBtn.click();
      }

      // Drag and zoom in 3D preview
      const lamp3d = page.locator('[data-tutorial-target="lamp-3d-preview"]');
      if (await lamp3d.isVisible()) {
        const box = await lamp3d.boundingBox();
        if (box) {
          const startX = box.x + box.width * 0.5;
          const startY = box.y + box.height * 0.5;
          await page.mouse.move(startX, startY);
          await page.mouse.down();
          await page.mouse.move(startX + 90, startY - 40, { steps: 15 });
          await page.mouse.up();
          await new Promise(r => setTimeout(r, 200));
          await page.mouse.move(startX, startY);
          await page.mouse.wheel(0, -350);
          await new Promise(r => setTimeout(r, 300));
        }
      }

      await waitForAssetsLoaded(page);

      const status = await page.locator('.status-bar').innerText().catch(() => '');
      console.log('Lamp Status Bar:', status);

      const lampPath = path.join(OUTPUT_DIR, 'readme-lamp.png');
      await page.screenshot({ path: lampPath, fullPage: false });
      console.log(`Saved ${lampPath} (${fs.statSync(lampPath).size} bytes)`);
      await context.close();
    }

    // ------------------------------------------------------------------------
    // SCREENSHOT 4: docs/assets/readme-fabrication.png
    // ------------------------------------------------------------------------
    console.log('\n--- Generating Screenshot 4: readme-fabrication.png ---');
    {
      const context = await browser.newContext({
        viewport: { width: 1440, height: 900 },
        deviceScaleFactor: 2,
        locale: 'en-US',
      });
      const page = await context.newPage();
      await page.goto(TARGET_URL);

      const fabProject = createHeroWindowProject(5.5);
      await loadProjectIntoPage(page, fabProject);

      // Select Emerald Green Glass tab so the right panel is visually distinct from readme-hero.png
      await page.evaluate(() => {
        const tab = Array.from(document.querySelectorAll('.sheet-tab')).find(el => el.textContent.includes('Emerald Green'));
        if (tab) tab.click();
      });
      await new Promise(r => setTimeout(r, 200));

      // Run Smart Pack
      const packBtn = page.locator('[data-tutorial-target="smart-pack-button"]');
      if (await packBtn.isVisible()) {
        await packBtn.click();
        await new Promise(r => setTimeout(r, 300));
        const startPackingBtn = page.locator('[data-tutorial-target="start-packing"]');
        if (await startPackingBtn.isVisible()) {
          await startPackingBtn.click();
          await new Promise(r => setTimeout(r, 1200));
        }
      }

      await page.keyboard.press('Escape');
      await new Promise(r => setTimeout(r, 300));

      const solderBtn = page.locator('[data-tutorial-target="solder-settings"]');
      if (await solderBtn.isVisible()) {
        await solderBtn.click();
        await new Promise(r => setTimeout(r, 300));
      }

      await waitForAssetsLoaded(page);

      const status = await page.locator('.status-bar').innerText().catch(() => '');
      console.log('Fab Status Bar:', status);

      const fabPath = path.join(OUTPUT_DIR, 'readme-fabrication.png');
      await page.screenshot({ path: fabPath, fullPage: false });
      console.log(`Saved ${fabPath} (${fs.statSync(fabPath).size} bytes)`);
      await context.close();
    }

    await browser.close();
    console.log('\nSUCCESS! All 4 screenshots generated.');
  } finally {
    cleanupServer();
  }
}

main().catch(err => {
  console.error('FAILED to generate screenshots:', err);
  cleanupServer();
  process.exit(1);
});
