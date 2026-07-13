import * as ort from "onnxruntime-web/webgpu";
import { maskToPolygon as extractMaskPolygon, smoothMaskLogits } from './utils/maskContour';
// Self-host the ORT wasm binary (the .mjs loader is embedded in the webgpu
// bundle). Vite emits the file as a same-origin asset, so segmentation no
// longer depends on a third-party CDN being reachable, and the JS/wasm
// versions can never drift apart. The relative node_modules path is needed
// because the package's exports map doesn't expose ./dist/*.
import ortWasmUrl from "../node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.jsep.wasm?url";

// onnxruntime-web's WASM backend can spawn Emscripten pthread workers using
// this module's own URL when its preferred worker script isn't reachable.
// Those workers would re-run our init() and hijack self.onmessage from the
// pthread runtime, breaking ORT and triggering duplicate model loads.
const isPthread = (self as { name?: string }).name === 'em-pthread';

if (!isPthread) {
  // numThreads stays 1 on the WebGPU path (the EP doesn't need threads, and
  // this keeps ORT from spawning pthread workers needlessly); the wasm
  // fallback raises it in detectExecutionProviders().
  ort.env.wasm.numThreads = 1;
  ort.env.wasm.wasmPaths = { wasm: new URL(ortWasmUrl, self.location.href).href };
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
// Keep smoothing stable in model-input coordinates even if a model variant
// returns a decoder mask other than the usual 256×256.
const MASK_SMOOTHING_SIGMA_INPUT_PX = 6;

// ─── Types ────────────────────────────────────────────────────────────────────

export type WorkerInMsg =
  | { type: 'encode';      id: string; imageUrl: string }
  | { type: 'segment';     id: string; sessionId: string;
      box?: [number, number, number, number];
      points?: [number, number, number][] }
  | { type: 'autoSegment'; id: string; sessionId: string };

export type SamDevice = 'webgpu' | 'wasm';

/** i18n keys (resolved on the main thread — workers can't use i18next). */
export type SamStatusKey =
  | 'samStatusInit'
  | 'samStatusLoadingDecoder'
  | 'samStatusCompilingDecoder'
  | 'samStatusLoadingEncoder'
  | 'samStatusCompilingEncoder';

export type WorkerOutMsg =
  | { type: 'ready';            device: SamDevice }
  | { type: 'init:error';       error: string }
  | { type: 'status';           key: SamStatusKey }
  | { type: 'progress';         fraction: number }
  | { type: 'encode:done';      id: string; sessionId: string }
  | { type: 'encode:error';     id: string; error: string }
  | { type: 'segment:done';     id: string; polygon: [number, number][];
      debugMask?: { bitmap: ImageBitmap; width: number; height: number } }
  | { type: 'segment:error';    id: string; error: string }
  | { type: 'autoSegment:done'; id: string; polygons: [number, number][][] }
  | { type: 'autoSegment:error';id: string; error: string };

// ─── State ────────────────────────────────────────────────────────────────────

interface CachedEmbed {
  origW: number; origH: number;
  scale: number; padX: number; padY: number;
  encoderOut: Record<string, ort.Tensor>;
}

interface SerializedTensor {
  type: string;
  dims: number[];
  data: ArrayBuffer;
}

interface SerializedCachedEmbed {
  origW: number;
  origH: number;
  scale: number;
  padX: number;
  padY: number;
  encoderOut: Record<string, SerializedTensor>;
}

let encoderSession: ort.InferenceSession | null = null;
let decoderSession: ort.InferenceSession | null = null;
const cache = new Map<string, CachedEmbed>();
let initStarted = false;

// ─── Init ─────────────────────────────────────────────────────────────────────

const downloadProgress = new Map<string, { loaded: number; total: number }>();

function reportProgress() {
  let loaded = 0;
  let total = 0;
  for (const stats of downloadProgress.values()) {
    loaded += stats.loaded;
    total += stats.total;
  }
  if (total > 0) {
    post({ type: 'progress', fraction: loaded / total });
  }
}

async function fetchCached(url: string, filename: string): Promise<ArrayBuffer> {
  let guessTotal = 4000000; // default for .onnx
  if (filename.endsWith('.onnx_data')) {
    guessTotal = filename.includes('encoder') ? 305000000 : 21000000;
  }
  if (!downloadProgress.has(filename)) {
    downloadProgress.set(filename, { loaded: 0, total: guessTotal });
  }

  try {
    const root = await navigator.storage.getDirectory();
    try {
      const handle = await root.getFileHandle(filename);
      const file = await handle.getFile();
      console.log(`[SAM Worker] Loading ${filename} from OPFS cache...`);
      const buf = await file.arrayBuffer();
      downloadProgress.set(filename, { loaded: buf.byteLength, total: buf.byteLength });
      reportProgress();
      return buf;
    } catch {
      console.log(`[SAM Worker] Fetching ${filename} from ${url}...`);
      const res = await fetch(url);
      if (!res.ok) throw new Error(`Fetch failed: ${res.statusText}`);
      
      const contentLength = res.headers.get('Content-Length');
      // If we don't know the exact size, we can guess or use 0. But we know approximate sizes:
      // decoder: 4MB + 15MB = 19MB, encoder: 4MB + 30MB = 34MB. Let's just use what's provided.
      const total = contentLength ? parseInt(contentLength, 10) : (filename.includes('encoder') ? 30000000 : 15000000);
      let loaded = 0;
      
      downloadProgress.set(filename, { loaded, total });
      reportProgress();

      if (!res.body) {
        const buf = await res.arrayBuffer();
        downloadProgress.set(filename, { loaded: buf.byteLength, total: buf.byteLength });
        reportProgress();
        return buf;
      }

      const reader = res.body.getReader();
      const chunks: Uint8Array[] = [];
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        if (value) {
          chunks.push(value);
          loaded += value.length;
          // `total` is a guess when Content-Length is missing; never let the
          // reported fraction hit/exceed 1 while bytes are still streaming.
          downloadProgress.set(filename, { loaded, total: Math.max(total, loaded + 1) });
          reportProgress();
        }
      }
      // The true size is known now — replace the guessed total so the
      // aggregate fraction can actually reach 1 (and never overshoots it).
      downloadProgress.set(filename, { loaded, total: loaded });
      reportProgress();

      let position = 0;
      const buf = new Uint8Array(loaded);
      for (const chunk of chunks) {
        buf.set(chunk, position);
        position += chunk.length;
      }

      // Save to cache for next time — best-effort: a failed cache write must
      // not throw away the bytes we just downloaded.
      try {
        const handle = await root.getFileHandle(filename, { create: true });
        const writable = await (handle as any).createWritable();
        await writable.write(buf);
        await writable.close();
        console.log(`[SAM Worker] Saved ${filename} to OPFS cache.`);
      } catch (cacheErr) {
        console.warn(`[SAM Worker] Could not cache ${filename} in OPFS:`, cacheErr);
      }

      return buf.buffer;
    }
  } catch (err) {
    console.warn(`[SAM Worker] Cache failed for ${filename}, falling back to network:`, err);
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Fetch failed for ${filename}: ${res.status} ${res.statusText}`);
    const buf = await res.arrayBuffer();
    downloadProgress.set(filename, { loaded: buf.byteLength, total: buf.byteLength });
    reportProgress();
    return buf;
  }
}

// ─── IndexedDB Caching ────────────────────────────────────────────────────────

function serializeTensor(tensor: ort.Tensor): SerializedTensor {
  const data = (tensor.data as ArrayBufferView).buffer.slice(
    (tensor.data as ArrayBufferView).byteOffset,
    (tensor.data as ArrayBufferView).byteOffset + (tensor.data as ArrayBufferView).byteLength
  ) as ArrayBuffer;
  return {
    type: tensor.type,
    dims: [...tensor.dims],
    data
  };
}

function deserializeTensor(s: SerializedTensor): ort.Tensor {
  let typedArray: any;
  if (s.type === 'float32') {
    typedArray = new Float32Array(s.data);
  } else if (s.type === 'int32') {
    typedArray = new Int32Array(s.data);
  } else {
    throw new Error(`Unsupported tensor type for deserialization: ${s.type}`);
  }
  return new ort.Tensor(s.type, typedArray, s.dims);
}

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('vitraux-sam-cache', 1);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains('encodings')) {
        db.createObjectStore('encodings');
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function getEmbedFromDB(imageUrl: string): Promise<CachedEmbed | null> {
  try {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction('encodings', 'readonly');
      const store = tx.objectStore('encodings');
      const req = store.get(imageUrl);
      req.onsuccess = () => {
        const val = req.result as SerializedCachedEmbed | undefined;
        if (!val) {
          resolve(null);
          return;
        }
        try {
          const encoderOut: Record<string, ort.Tensor> = {};
          for (const key of Object.keys(val.encoderOut)) {
            encoderOut[key] = deserializeTensor(val.encoderOut[key]);
          }
          resolve({
            origW: val.origW,
            origH: val.origH,
            scale: val.scale,
            padX: val.padX,
            padY: val.padY,
            encoderOut
          });
        } catch (e) {
          console.warn('[SAM Worker] Failed to deserialize cached embed:', e);
          resolve(null);
        }
      };
      req.onerror = () => reject(req.error);
    });
  } catch (err) {
    console.warn('[SAM Worker] IndexedDB read failed:', err);
    return null;
  }
}

async function saveEmbedToDB(imageUrl: string, embed: CachedEmbed): Promise<void> {
  try {
    const db = await openDB();
    const encoderOut: Record<string, SerializedTensor> = {};
    for (const key of Object.keys(embed.encoderOut)) {
      encoderOut[key] = serializeTensor(embed.encoderOut[key]);
    }
    const serialized: SerializedCachedEmbed = {
      origW: embed.origW,
      origH: embed.origH,
      scale: embed.scale,
      padX: embed.padX,
      padY: embed.padY,
      encoderOut
    };
    return new Promise((resolve, reject) => {
      const tx = db.transaction('encodings', 'readwrite');
      const store = tx.objectStore('encodings');
      const req = store.put(serialized, imageUrl);
      req.onsuccess = () => resolve();
      req.onerror = () => reject(req.error);
    });
  } catch (err) {
    console.warn('[SAM Worker] IndexedDB write failed:', err);
  }
}

// ─── Lazy Model Init ──────────────────────────────────────────────────────────

let initDecoderStarted = false;
let initEncoderStarted = false;

// Probe for a usable WebGPU adapter (in this worker — page-level support is
// not enough) instead of assuming it. Previously the worker always reported
// device 'webgpu' even when ORT silently fell back to single-threaded wasm.
let detectedDevice: 'webgpu' | 'wasm' = 'wasm';
let epPromise: Promise<ort.InferenceSession.ExecutionProviderConfig[]> | null = null;
function detectExecutionProviders(): Promise<ort.InferenceSession.ExecutionProviderConfig[]> {
  if (!epPromise) {
    epPromise = (async () => {
      try {
        const gpu = (navigator as { gpu?: { requestAdapter(): Promise<unknown | null> } }).gpu;
        const adapter = gpu ? await gpu.requestAdapter() : null;
        if (adapter) {
          detectedDevice = 'webgpu';
          return ['webgpu', 'wasm'] as ort.InferenceSession.ExecutionProviderConfig[];
        }
      } catch {
        // No usable adapter — fall through to wasm.
      }
      detectedDevice = 'wasm';
      // Single-threaded CPU inference of the ~300 MB encoder is unusably
      // slow, and the site is cross-origin isolated precisely so threaded
      // wasm works — use it. (em-pthread workers are guarded at module top.)
      ort.env.wasm.numThreads = Math.max(1, Math.min(navigator.hardwareConcurrency || 1, 8));
      return ['wasm'] as ort.InferenceSession.ExecutionProviderConfig[];
    })();
  }
  return epPromise;
}
let decoderReadyPromise: Promise<void> | null = null;
let encoderReadyPromise: Promise<void> | null = null;

async function initDecoder() {
  if (decoderSession) return;
  if (initDecoderStarted) {
    await decoderReadyPromise;
    return;
  }
  initDecoderStarted = true;
  let resolveReady!: () => void;
  let rejectReady!: (e: Error) => void;
  decoderReadyPromise = new Promise<void>((res, rej) => {
    resolveReady = res;
    rejectReady = rej;
  });

  try {
    post({ type: 'status', key: 'samStatusLoadingDecoder' });
    const [decModel, decData] = await Promise.all([
      fetchCached(DECODER_URL, 'sam2_base_decoder.onnx'),
      fetchCached(DECODER_DATA_URL, 'sam2_base_decoder.onnx_data'),
    ]);

    post({ type: 'status', key: 'samStatusCompilingDecoder' });
    const ep = await detectExecutionProviders();
    decoderSession = await ort.InferenceSession.create(new Uint8Array(decModel), {
      executionProviders: ep,
      externalData: [{
        data: new Uint8Array(decData),
        path: 'prompt_encoder_mask_decoder.onnx_data'
      }]
    });
    resolveReady();
  } catch (err) {
    console.error("[SAM Worker] Decoder initialization failed:", err);
    rejectReady(err instanceof Error ? err : new Error(String(err)));
    throw err;
  }
}

// Shared fetch of the encoder model files. Deduplicated so the post-init
// background warm-up and the first encode can't download the ~309 MB twice
// concurrently.
let encoderFetchPromise: Promise<[ArrayBuffer, ArrayBuffer]> | null = null;
function fetchEncoderModels(): Promise<[ArrayBuffer, ArrayBuffer]> {
  if (!encoderFetchPromise) {
    const p = Promise.all([
      fetchCached(ENCODER_URL, 'sam2_base_encoder.onnx'),
      fetchCached(ENCODER_DATA_URL, 'sam2_base_encoder.onnx_data'),
    ]);
    // On failure allow a later retry, but never clobber a newer attempt.
    p.catch(() => { if (encoderFetchPromise === p) encoderFetchPromise = null; });
    encoderFetchPromise = p;
  }
  return encoderFetchPromise;
}

async function initEncoder() {
  if (encoderSession) return;
  if (initEncoderStarted) {
    await encoderReadyPromise;
    return;
  }
  initEncoderStarted = true;
  let resolveReady!: () => void;
  let rejectReady!: (e: Error) => void;
  encoderReadyPromise = new Promise<void>((res, rej) => {
    resolveReady = res;
    rejectReady = rej;
  });

  try {
    post({ type: 'status', key: 'samStatusLoadingEncoder' });
    const [encModel, encData] = await fetchEncoderModels();

    post({ type: 'status', key: 'samStatusCompilingEncoder' });
    const ep = await detectExecutionProviders();
    encoderSession = await ort.InferenceSession.create(new Uint8Array(encModel), {
      executionProviders: ep,
      externalData: [{
        data: new Uint8Array(encData),
        path: 'vision_encoder.onnx_data'
      }]
    });
    // Session owns its copies now; release the raw buffers.
    encoderFetchPromise = null;
    resolveReady();
  } catch (err) {
    console.error("[SAM Worker] Encoder initialization failed:", err);
    rejectReady(err instanceof Error ? err : new Error(String(err)));
    throw err;
  }
}

async function fileExistsInCache(filename: string): Promise<boolean> {
  try {
    const root = await navigator.storage.getDirectory();
    await root.getFileHandle(filename);
    return true;
  } catch {
    return false;
  }
}

// Background warm-up of the encoder download right after init. Without this,
// the first encode triggered a second ~309 MB download after the progress UI
// had already reported 100% for the (much smaller) decoder — looking like the
// model was downloading twice.
async function warmEncoderCache() {
  try {
    await fetchEncoderModels();
    // If no encode has claimed the buffers yet, drop them — they're in the
    // OPFS cache now and the first encode will read them from disk instead
    // of pinning ~300 MB in worker memory indefinitely.
    if (!initEncoderStarted) encoderFetchPromise = null;
  } catch (err) {
    console.warn('[SAM Worker] Encoder warm-up failed (will retry on first segment):', err);
    // Don't leave unfinished entries stalling the progress bar below 100%.
    downloadProgress.delete('sam2_base_encoder.onnx');
    downloadProgress.delete('sam2_base_encoder.onnx_data');
    reportProgress();
  }
}

async function init() {
  if (initStarted) return;
  initStarted = true;
  try {
    post({ type: 'status', key: 'samStatusInit' });
    // On a first run, register the encoder files in the progress accounting
    // before the decoder downloads, so the reported fraction covers the full
    // first-run download instead of completing after the decoder and
    // restarting for the encoder.
    if (!(await fileExistsInCache('sam2_base_encoder.onnx_data'))) {
      if (!downloadProgress.has('sam2_base_encoder.onnx')) {
        downloadProgress.set('sam2_base_encoder.onnx', { loaded: 0, total: 4000000 });
      }
      if (!downloadProgress.has('sam2_base_encoder.onnx_data')) {
        downloadProgress.set('sam2_base_encoder.onnx_data', { loaded: 0, total: 305000000 });
      }
    }
    await initDecoder();
    post({ type: 'ready', device: detectedDevice });
    void warmEncoderCache();
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

  const dbCached = await getEmbedFromDB(imageUrl);
  if (dbCached) {
    cache.set(imageUrl, dbCached);
    post({ type: 'encode:done', id, sessionId: imageUrl });
    return;
  }

  await initEncoder();

  const { tensor, origW, origH, scale, padX, padY } = await loadAndPreprocess(imageUrl);
  const encoderOut = await encoderSession!.run({ pixel_values: tensor });

  const embed: CachedEmbed = { origW, origH, scale, padX, padY, encoderOut };
  cache.set(imageUrl, embed);
  await saveEmbedToDB(imageUrl, embed);

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

  const { scale, padX, padY, origW, origH, encoderOut } = cached;

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

    const smoothingSigma = MASK_SMOOTHING_SIGMA_INPUT_PX * Math.max(W, H) / INPUT_SIZE;
    const regularizedMask = smoothMaskLogits(maskData, W, H, smoothingSigma);
    const upsampled = bilinearUpsample(regularizedMask, W, H, INPUT_SIZE, INPUT_SIZE);

    const polygon = extractMaskPolygon(upsampled, INPUT_SIZE, INPUT_SIZE, {
      inputSize: INPUT_SIZE, scale, padX, padY, origW, origH,
      threshold: MASK_THRESHOLD,
    });

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

function computeCentroid(pts: [number, number][]): { x: number; y: number } {
  let xs = 0, ys = 0;
  for (const [x, y] of pts) {
    xs += x;
    ys += y;
  }
  return { x: xs / pts.length, y: ys / pts.length };
}

async function autoSegment(id: string, sessionId: string) {
  const cached = cache.get(sessionId);
  if (!cached) {
    console.error("[SAM Worker] No cached session found for autoSegment:", sessionId);
    post({ type: 'autoSegment:error', id, error: `No session: ${sessionId}` });
    return;
  }

  const { scale, padX, padY, encoderOut, origW, origH } = cached;
  const newW = origW * scale;
  const newH = origH * scale;

  const polygons: [number, number][][] = [];
  const gridCount = 8;

  try {
    for (let i = 1; i <= gridCount; i++) {
      for (let j = 1; j <= gridCount; j++) {
        const px = (i / (gridCount + 1)) * newW;
        const py = (j / (gridCount + 1)) * newH;

        const pointCoords = new ort.Tensor('float32', new Float32Array([px, py]), [1, 1, 1, 2]);
        const pointLabels = new ort.Tensor('int64', new BigInt64Array([1n]), [1, 1, 1]);
        const boxTensor = new ort.Tensor('float32', new Float32Array([0, 0, 0, 0]), [1, 1, 4]);

        const decoderInputs: Record<string, ort.Tensor> = {
          ...encoderOut,
          input_points:    pointCoords,
          input_labels:    pointLabels,
          input_boxes:     boxTensor,
        };

        const decoderOut = await decoderSession!.run(decoderInputs);
        const masksTensor = decoderOut['pred_masks'];
        const iouTensor = decoderOut['iou_scores'];

        if (!masksTensor || !iouTensor) continue;

        const iou = Array.from(iouTensor.data as Float32Array);
        const bestIdx = iou.indexOf(Math.max(...iou));
        const score = iou[bestIdx];

        if (score > 0.85) {
          const dims = masksTensor.dims;
          const H = dims[dims.length - 2];
          const W = dims[dims.length - 1];
          const planeSize = H * W;
          const maskData = (masksTensor.data as Float32Array).slice(bestIdx * planeSize, (bestIdx + 1) * planeSize);
          
          const smoothingSigma = MASK_SMOOTHING_SIGMA_INPUT_PX * Math.max(W, H) / INPUT_SIZE;
          const regularizedMask = smoothMaskLogits(maskData, W, H, smoothingSigma);
          const upsampled = bilinearUpsample(regularizedMask, W, H, INPUT_SIZE, INPUT_SIZE);
          const polygon = extractMaskPolygon(upsampled, INPUT_SIZE, INPUT_SIZE, {
            inputSize: INPUT_SIZE, scale, padX, padY, origW, origH,
            threshold: MASK_THRESHOLD,
          });

          if (polygon.length >= 3) {
            const centroid = computeCentroid(polygon);
            let isDuplicate = false;
            for (const poly of polygons) {
              const c = computeCentroid(poly);
              if (Math.hypot(c.x - centroid.x, c.y - centroid.y) < 25) {
                isDuplicate = true;
                break;
              }
            }
            if (!isDuplicate) {
              polygons.push(polygon);
            }
          }
        }
      }
    }
    post({ type: 'autoSegment:done', id, polygons });
  } catch (err) {
    console.error("[SAM Worker] autoSegment failed:", err);
    post({ type: 'autoSegment:error', id, error: String(err) });
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


// ─── Messaging ────────────────────────────────────────────────────────────────

function post(msg: WorkerOutMsg) { self.postMessage(msg); }

if (!isPthread) {
  self.onmessage = async (e: MessageEvent<WorkerInMsg>) => {
    const msg = e.data;
    try {
      if (msg.type === 'encode')            await encode(msg.id, msg.imageUrl);
      else if (msg.type === 'segment')      await segment(msg.id, msg.sessionId, msg.box, msg.points);
      else if (msg.type === 'autoSegment')  await autoSegment(msg.id, msg.sessionId);
    } catch (err) {
      const error = err instanceof Error ? err.message : String(err);
      if (msg.type === 'encode')            post({ type: 'encode:error', id: msg.id, error });
      else if (msg.type === 'segment')      post({ type: 'segment:error', id: msg.id, error });
      else if (msg.type === 'autoSegment')  post({ type: 'autoSegment:error', id: msg.id, error });
    }
  };

  init().catch(err => post({ type: 'init:error', error: String(err) }));
}
