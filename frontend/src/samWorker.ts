import * as ort from "onnxruntime-web";

// onnxruntime-web's WASM backend can spawn Emscripten pthread workers using
// this module's own URL when its preferred worker script isn't reachable.
// Those workers would re-run our init() and hijack self.onmessage from the
// pthread runtime, breaking ORT and triggering duplicate model loads.
const isPthread = (self as { name?: string }).name === 'em-pthread';

if (!isPthread) {
  // Disable WASM threading entirely — WebGPU EP doesn't need threads, and
  // this keeps ORT from spawning pthread workers in the first place.
  ort.env.wasm.numThreads = 1;
  ort.env.wasm.wasmPaths = 'https://cdn.jsdelivr.net/npm/onnxruntime-web@1.19.2/dist/';
}

const HF = 'https://huggingface.co/onnx-community/sam2.1-hiera-base-plus-ONNX/resolve/main/onnx';
const ENCODER_URL = `${HF}/vision_encoder.onnx`;
const ENCODER_DATA_URL = `${HF}/vision_encoder.onnx_data`;
const DECODER_URL = `${HF}/prompt_encoder_mask_decoder.onnx`;
const DECODER_DATA_URL = `${HF}/prompt_encoder_mask_decoder.onnx_data`;

const INPUT_SIZE = 1024;
const MEAN = [0.485, 0.456, 0.406];
const STD  = [0.229, 0.224, 0.225];
const MASK_THRESHOLD = 0;

// ─── Types ────────────────────────────────────────────────────────────────────

export type WorkerInMsg =
  | { type: 'encode';  id: string; imageUrl: string }
  | { type: 'segment'; id: string; sessionId: string;
      box?: [number, number, number, number];
      points?: [number, number, number][] };

export type WorkerOutMsg =
  | { type: 'ready';        device: string }
  | { type: 'init:error';   error: string }
  | { type: 'status';       text: string }
  | { type: 'encode:done';  id: string; sessionId: string }
  | { type: 'encode:error'; id: string; error: string }
  | { type: 'segment:done'; id: string; polygon: [number, number][];
      debugMask?: { bitmap: ImageBitmap; width: number; height: number } }
  | { type: 'segment:error';id: string; error: string };

// ─── State ────────────────────────────────────────────────────────────────────

interface CachedEmbed {
  origW: number; origH: number;
  scale: number; padX: number; padY: number;
  encoderOut: Record<string, ort.Tensor>;
}

let encoderSession: ort.InferenceSession | null = null;
let decoderSession: ort.InferenceSession | null = null;
const cache = new Map<string, CachedEmbed>();
let initStarted = false;

// ─── Init ─────────────────────────────────────────────────────────────────────

async function fetchCached(url: string, filename: string): Promise<ArrayBuffer> {
  try {
    const root = await navigator.storage.getDirectory();
    try {
      const handle = await root.getFileHandle(filename);
      const file = await handle.getFile();
      console.log(`[SAM Worker] Loading ${filename} from OPFS cache...`);
      return await file.arrayBuffer();
    } catch {
      console.log(`[SAM Worker] Fetching ${filename} from ${url}...`);
      const res = await fetch(url);
      if (!res.ok) throw new Error(`Fetch failed: ${res.statusText}`);
      const buf = await res.arrayBuffer();

      // Save to cache for next time
      const handle = await root.getFileHandle(filename, { create: true });
      const writable = await (handle as any).createWritable();
      await writable.write(buf);
      await writable.close();
      console.log(`[SAM Worker] Saved ${filename} to OPFS cache.`);
      return buf;
    }
  } catch (err) {
    console.warn(`[SAM Worker] Cache failed for ${filename}, falling back to network:`, err);
    const res = await fetch(url);
    return await res.arrayBuffer();
  }
}

async function init() {
  if (initStarted) return;
  initStarted = true;
  try {
    post({ type: 'status', text: 'Initializing SAM2 models…' });

    // Load models (concurrently if possible, but OPFS might be serial)
    const [encModel, encData, decModel, decData] = await Promise.all([
      fetchCached(ENCODER_URL, 'sam2_base_encoder.onnx'),
      fetchCached(ENCODER_DATA_URL, 'sam2_base_encoder.onnx_data'),
      fetchCached(DECODER_URL, 'sam2_base_decoder.onnx'),
      fetchCached(DECODER_DATA_URL, 'sam2_base_decoder.onnx_data'),
    ]);

    const ep: ort.InferenceSession.ExecutionProviderConfig[] = ['webgpu', 'wasm'];

    encoderSession = await ort.InferenceSession.create(new Uint8Array(encModel), {
      executionProviders: ep,
      externalData: [{
        data: new Uint8Array(encData),
        path: 'vision_encoder.onnx_data'
      }]
    });

    decoderSession = await ort.InferenceSession.create(new Uint8Array(decModel), {
      executionProviders: ep,
      externalData: [{
        data: new Uint8Array(decData),
        path: 'prompt_encoder_mask_decoder.onnx_data'
      }]
    });

    post({ type: 'ready', device: 'webgpu' });
  } catch (err) {
    console.error("[SAM Worker] Initialization failed:", err);
    const error = err instanceof Error ? `${err.message}\n${err.stack ?? ''}` : String(err);
    post({ type: 'init:error', error });
  }
}

// ─── Preprocessing ────────────────────────────────────────────────────────────

async function loadAndPreprocess(imageUrl: string): Promise<{
  tensor: ort.Tensor; origW: number; origH: number;
  scale: number; padX: number; padY: number;
}> {
  const blob = await fetch(imageUrl).then(r => r.blob());
  const bitmap = await createImageBitmap(blob);
  const { width: origW, height: origH } = bitmap;

  // Calculate letterbox scale and padding (preserve aspect ratio)
  const scale = Math.min(INPUT_SIZE / origW, INPUT_SIZE / origH);
  const newW = Math.round(origW * scale);
  const newH = Math.round(origH * scale);
  const padX = 0; // Standard SAM-style is top-left padding
  const padY = 0;

  const canvas = new OffscreenCanvas(INPUT_SIZE, INPUT_SIZE);
  const ctx = canvas.getContext('2d')!;

  // Fill background with zeros (black)
  ctx.fillStyle = 'black';
  ctx.fillRect(0, 0, INPUT_SIZE, INPUT_SIZE);

  // Draw resized image
  ctx.drawImage(bitmap, padX, padY, newW, newH);
  const { data } = ctx.getImageData(0, 0, INPUT_SIZE, INPUT_SIZE);

  const float = new Float32Array(3 * INPUT_SIZE * INPUT_SIZE);
  for (let i = 0; i < INPUT_SIZE * INPUT_SIZE; i++) {
    float[0 * INPUT_SIZE * INPUT_SIZE + i] = (data[i * 4    ] / 255 - MEAN[0]) / STD[0];
    float[1 * INPUT_SIZE * INPUT_SIZE + i] = (data[i * 4 + 1] / 255 - MEAN[1]) / STD[1];
    float[2 * INPUT_SIZE * INPUT_SIZE + i] = (data[i * 4 + 2] / 255 - MEAN[2]) / STD[2];
  }

  return {
    tensor: new ort.Tensor('float32', float, [1, 3, INPUT_SIZE, INPUT_SIZE]),
    origW, origH, scale, padX, padY
  };
}

// ─── Encode ───────────────────────────────────────────────────────────────────

async function encode(id: string, imageUrl: string) {
  if (cache.has(imageUrl)) {
    post({ type: 'encode:done', id, sessionId: imageUrl });
    return;
  }

  const { tensor, origW, origH, scale, padX, padY } = await loadAndPreprocess(imageUrl);
  const encoderOut = await encoderSession!.run({ pixel_values: tensor });

  cache.set(imageUrl, { origW, origH, scale, padX, padY, encoderOut });
  post({ type: 'encode:done', id, sessionId: imageUrl });
}

// ─── Segment ──────────────────────────────────────────────────────────────────

async function segment(
  id: string,
  sessionId: string,
  box?: [number, number, number, number],
  points?: [number, number, number][],
) {
  const cached = cache.get(sessionId);
  if (!cached) {
    console.error("[SAM Worker] No cached session found for:", sessionId);
    post({ type: 'segment:error', id, error: `No session: ${sessionId}` });
    return;
  }

  const { scale, padX, padY, encoderOut } = cached;

  const coords: number[] = [];
  const labels: number[] = [];

  if (points) {
    for (const [x, y, l] of points) {
      coords.push(x * scale + padX, y * scale + padY);
      labels.push(l);
    }
  }
  
  if (coords.length === 0) {
    coords.push(0, 0);
    labels.push(-1);
  }

  const N = coords.length / 2;
  const pointCoords = new ort.Tensor('float32', new Float32Array(coords), [1, 1, N, 2]);
  const pointLabels = new ort.Tensor('int64',   new BigInt64Array(labels.map(BigInt)), [1, 1, N]);

  // Handle box tensor
  let boxTensor: ort.Tensor | undefined;
  if (box) {
    boxTensor = new ort.Tensor('float32', new Float32Array([
      box[0] * scale + padX, box[1] * scale + padY,
      box[2] * scale + padX, box[3] * scale + padY
    ]), [1, 1, 4]);
  } else {
    boxTensor = new ort.Tensor('float32', new Float32Array([0, 0, 0, 0]), [1, 1, 4]);
  }

  const decoderInputs: Record<string, ort.Tensor> = {
    ...encoderOut,
    input_points:    pointCoords,
    input_labels:    pointLabels,
    input_boxes:     boxTensor,
  };

  try {
    const decoderOut = await decoderSession!.run(decoderInputs);
    const masksTensor = decoderOut['pred_masks'];
    const iouTensor = decoderOut['iou_scores'];

    if (!masksTensor) {
      throw new Error(`No mask output. Keys: ${Object.keys(decoderOut).join(', ')}`);
    }

    const dims = masksTensor.dims;
    const H = dims[dims.length - 2];
    const W = dims[dims.length - 1];
    const numMasks = dims[dims.length - 3] ?? 1;
    const planeSize = H * W;

    let bestIdx = 0;
    if (numMasks > 1 && iouTensor) {
      const iou = Array.from(iouTensor.data as Float32Array);
      bestIdx = iou.indexOf(Math.max(...iou));
    }

    const maskData = (masksTensor.data as Float32Array)
      .slice(bestIdx * planeSize, (bestIdx + 1) * planeSize);

    const upsampled = bilinearUpsample(maskData, W, H, INPUT_SIZE, INPUT_SIZE);

    const polygon = maskToPolygon(upsampled, INPUT_SIZE, INPUT_SIZE, scale, padX, padY);

    // Debug overlay: paint upsampled mask as a semi-transparent bitmap.
    const debugCanvas = new OffscreenCanvas(INPUT_SIZE, INPUT_SIZE);
    const dctx = debugCanvas.getContext('2d')!;
    const imgData = dctx.createImageData(INPUT_SIZE, INPUT_SIZE);
    for (let i = 0; i < INPUT_SIZE * INPUT_SIZE; i++) {
      if (upsampled[i] > MASK_THRESHOLD) {
        imgData.data[i * 4 + 0] = 59;
        imgData.data[i * 4 + 1] = 130;
        imgData.data[i * 4 + 2] = 246;
        imgData.data[i * 4 + 3] = 60;
      }
    }
    dctx.putImageData(imgData, 0, 0);
    const debugBitmap = debugCanvas.transferToImageBitmap();
    const displayW = INPUT_SIZE / scale;
    const displayH = INPUT_SIZE / scale;

    self.postMessage(
      { type: 'segment:done', id, polygon,
        debugMask: { bitmap: debugBitmap, width: displayW, height: displayH } },
      { transfer: [debugBitmap] },
    );
  } catch (err) {
    console.error("[SAM Worker] Decoder run failed:", err);
    throw err;
  }
}

// ─── Bilinear upsample of mask logits ────────────────────────────────────────

function bilinearUpsample(
  src: Float32Array, srcW: number, srcH: number, dstW: number, dstH: number,
): Float32Array {
  const dst = new Float32Array(dstW * dstH);
  const sx = (srcW - 1) / (dstW - 1);
  const sy = (srcH - 1) / (dstH - 1);
  for (let y = 0; y < dstH; y++) {
    const fy = y * sy;
    const y0 = Math.floor(fy);
    const y1 = Math.min(srcH - 1, y0 + 1);
    const wy = fy - y0;
    for (let x = 0; x < dstW; x++) {
      const fx = x * sx;
      const x0 = Math.floor(fx);
      const x1 = Math.min(srcW - 1, x0 + 1);
      const wx = fx - x0;
      const v00 = src[y0 * srcW + x0];
      const v10 = src[y0 * srcW + x1];
      const v01 = src[y1 * srcW + x0];
      const v11 = src[y1 * srcW + x1];
      const v0 = v00 * (1 - wx) + v10 * wx;
      const v1 = v01 * (1 - wx) + v11 * wx;
      dst[y * dstW + x] = v0 * (1 - wy) + v1 * wy;
    }
  }
  return dst;
}

// ─── Mask → polygon ───────────────────────────────────────────────────────────

function maskToPolygon(
  data: Float32Array, W: number, H: number,
  scale: number, padX: number, padY: number,
): [number, number][] {
  const get = (x: number, y: number): boolean =>
    x >= 0 && x < W && y >= 0 && y < H && data[y * W + x] > MASK_THRESHOLD;

  // Mask is 256x256, representing the 1024x1024 preprocessed space.
  // To map back to original: ((maskCoord * (1024/256)) - pad) / scale
  const toOrigX = (mx: number) => (mx * (INPUT_SIZE / W) - padX) / scale;
  const toOrigY = (my: number) => (my * (INPUT_SIZE / H) - padY) / scale;

  const visited = new Uint8Array(W * H);
  let bestPts: [number, number][] = [];

  // Directions in clockwise order
  const dx = [0, 1, 1, 1, 0, -1, -1, -1];
  const dy = [-1, -1, 0, 1, 1, 1, 0, -1];

  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const idx = y * W + x;
      if (data[idx] > MASK_THRESHOLD && !visited[idx]) {
        // Found a potential new island! Trace it.
        const currentPts: [number, number][] = [];
        let cx = x, cy = y;
        let prevX = x, prevY = y - 1;
        let firstX = x, firstY = y;

        for (let i = 0; i < W * H; i++) {
          currentPts.push([toOrigX(cx), toOrigY(cy)]);
          visited[cy * W + cx] = 1; // Mark as visited
          
          let startDir = 0;
          for (let d = 0; d < 8; d++) {
            if (cx + dx[d] === prevX && cy + dy[d] === prevY) {
              startDir = (d + 1) % 8;
              break;
            }
          }

          let foundNext = false;
          for (let d = 0; d < 8; d++) {
            const dir = (startDir + d) % 8;
            const nx = cx + dx[dir], ny = cy + dy[dir];
            if (get(nx, ny)) {
              prevX = cx; prevY = cy;
              cx = nx; cy = ny;
              foundNext = true;
              break;
            }
          }

          if (!foundNext || (cx === firstX && cy === firstY)) break;
        }

        // Is this the biggest island we've seen?
        if (currentPts.length > bestPts.length) {
          bestPts = currentPts;
        }
      }
    }
  }

  if (bestPts.length < 3) return bestPts;

  // Calculate perimeter for dynamic simplification (matching Modal's 0.005 * arcLength)
  let perimeter = 0;
  for (let i = 0; i < bestPts.length; i++) {
    const p1 = bestPts[i];
    const p2 = bestPts[(i + 1) % bestPts.length];
    perimeter += Math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2);
  }

  const dynamicEps = Math.max(2.0, perimeter * 0.005);
  return douglasPeucker(bestPts, dynamicEps);
}

function douglasPeucker(pts: [number, number][], eps: number): [number, number][] {
  if (pts.length <= 2) return pts;
  const [x1, y1] = pts[0], [x2, y2] = pts[pts.length - 1];
  const len = Math.hypot(x2 - x1, y2 - y1);
  let maxD = 0, idx = 0;
  for (let i = 1; i < pts.length - 1; i++) {
    const [px, py] = pts[i];
    const d = len < 1e-10
      ? Math.hypot(px - x1, py - y1)
      : Math.abs((y2 - y1) * px - (x2 - x1) * py + x2 * y1 - y2 * x1) / len;
    if (d > maxD) { maxD = d; idx = i; }
  }
  if (maxD > eps) {
    return [...douglasPeucker(pts.slice(0, idx + 1), eps).slice(0, -1),
            ...douglasPeucker(pts.slice(idx), eps)];
  }
  return [pts[0], pts[pts.length - 1]];
}

// ─── Messaging ────────────────────────────────────────────────────────────────

function post(msg: WorkerOutMsg) { self.postMessage(msg); }

if (!isPthread) {
  self.onmessage = async (e: MessageEvent<WorkerInMsg>) => {
    const msg = e.data;
    try {
      if (msg.type === 'encode')       await encode(msg.id, msg.imageUrl);
      else if (msg.type === 'segment') await segment(msg.id, msg.sessionId, msg.box, msg.points);
    } catch (err) {
      const error = err instanceof Error ? err.message : String(err);
      if (msg.type === 'encode')       post({ type: 'encode:error', id: msg.id, error });
      else if (msg.type === 'segment') post({ type: 'segment:error', id: msg.id, error });
    }
  };

  init().catch(err => post({ type: 'init:error', error: String(err) }));
}
