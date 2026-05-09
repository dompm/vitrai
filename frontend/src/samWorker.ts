// Web Worker: runs SAM via Transformers.js with WebGPU / WASM fallback.
// Caches image embeddings so box queries are fast after the first encode.
//
// Override model at dev-server startup:
//   VITE_SAM_MODEL=Xenova/sam-vit-large npm run dev

import {
  SamModel,
  AutoProcessor,
  RawImage,
  env,
} from "@huggingface/transformers";

const MODEL_ID: string = import.meta.env.VITE_SAM_MODEL ?? "Xenova/sam-vit-base";

env.allowLocalModels = false;

// ─── Types ────────────────────────────────────────────────────────────────────

export type WorkerInMsg =
  | { type: "encode"; id: string; imageUrl: string }
  | { type: "segment"; id: string; sessionId: string; box?: [number, number, number, number]; points?: [number, number, number][] };

export type WorkerOutMsg =
  | { type: "ready"; device: string }
  | { type: "status"; text: string }
  | { type: "encode:done"; id: string; sessionId: string }
  | { type: "encode:error"; id: string; error: string }
  | { type: "segment:done"; id: string; polygon: [number, number][] }
  | { type: "segment:error"; id: string; error: string };

// ─── State ────────────────────────────────────────────────────────────────────

interface CachedSession {
  image: RawImage;
  imageInputs: Record<string, unknown>;
  imageEmbeddings: Record<string, unknown>;
}

let model: InstanceType<typeof SamModel> | null = null;
let processor: Awaited<ReturnType<typeof AutoProcessor.from_pretrained>> | null = null;
let activeDevice = "webgpu";

const sessions = new Map<string, CachedSession>();

// ─── Init ─────────────────────────────────────────────────────────────────────

async function init() {
  post({ type: "status", text: "Downloading model…" });

  try {
    [processor, model] = await Promise.all([
      AutoProcessor.from_pretrained(MODEL_ID),
      SamModel.from_pretrained(MODEL_ID, {
        device: "webgpu",
        dtype: {
          vision_encoder: "fp32",
          prompt_encoder_mask_decoder: "fp32",
        },
      } as Parameters<typeof SamModel.from_pretrained>[1]),
    ]);
    activeDevice = "webgpu";
  } catch {
    post({ type: "status", text: "WebGPU unavailable, falling back to WASM…" });
    [processor, model] = await Promise.all([
      AutoProcessor.from_pretrained(MODEL_ID),
      SamModel.from_pretrained(MODEL_ID, { device: "wasm" } as Parameters<typeof SamModel.from_pretrained>[1]),
    ]);
    activeDevice = "wasm";
  }

  post({ type: "ready", device: activeDevice });
}

// ─── Encode ───────────────────────────────────────────────────────────────────

async function encode(id: string, imageUrl: string) {
  // Session key = URL (stable within a page load; data URLs are deterministic)
  const sessionId = imageUrl;

  if (sessions.has(sessionId)) {
    post({ type: "encode:done", id, sessionId });
    return;
  }

  const image = await RawImage.fromURL(imageUrl);
  const imageInputs = await processor!(image) as Record<string, unknown>;
  const imageEmbeddings = await (model as any).get_image_embeddings(imageInputs) as Record<string, unknown>;

  sessions.set(sessionId, { image, imageInputs, imageEmbeddings });
  post({ type: "encode:done", id, sessionId });
}

// ─── Segment ──────────────────────────────────────────────────────────────────

async function segment(
  id: string,
  sessionId: string,
  box?: [number, number, number, number],
  points?: [number, number, number][],
) {
  const cached = sessions.get(sessionId);
  if (!cached) {
    post({ type: "segment:error", id, error: `Session not found: ${sessionId}` });
    return;
  }

  const { image, imageInputs, imageEmbeddings } = cached;

  // Build prompt inputs
  const promptOpts: Record<string, unknown> = {};
  if (box) promptOpts.input_boxes = [[[box[0], box[1], box[2], box[3]]]];
  if (points && points.length > 0) {
    promptOpts.input_points = [points.map(([x, y]) => [x, y])];
    promptOpts.input_labels = [points.map(([, , l]) => l)];
  }

  const processed = await processor!(image, promptOpts) as Record<string, unknown>;

  const outputs = await (model as any)({
    ...imageEmbeddings,
    input_boxes: processed.input_boxes,
    ...(processed.input_points ? { input_points: processed.input_points } : {}),
    ...(processed.input_labels ? { input_labels: processed.input_labels } : {}),
  });

  const masks: unknown = await (processor as any).post_process_masks(
    outputs.pred_masks,
    (imageInputs as any).original_sizes,
    (imageInputs as any).reshaped_input_sizes,
  );

  // masks[0]: Tensor [num_masks, H, W]
  const maskTensor = (masks as any)[0];
  const maskData: Float32Array = maskTensor.data;
  const dims: number[] = maskTensor.dims;
  const H = dims[dims.length - 2];
  const W = dims[dims.length - 1];

  const polygon = maskToPolygon(maskData, W, H);
  post({ type: "segment:done", id, polygon });
}

// ─── Mask → polygon ───────────────────────────────────────────────────────────

function maskToPolygon(data: Float32Array, width: number, height: number): [number, number][] {
  const get = (x: number, y: number): boolean =>
    x >= 0 && x < width && y >= 0 && y < height && data[y * width + x] > 0;

  // Find topmost-leftmost foreground pixel
  let sx = -1, sy = -1;
  outer: for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      if (get(x, y)) { sx = x; sy = y; break outer; }
    }
  }
  if (sx === -1) return [];

  // Moore neighbor contour tracing (8-connectivity)
  // Direction order: E, SE, S, SW, W, NW, N, NE
  const ddx = [1, 1, 0, -1, -1, -1, 0, 1];
  const ddy = [0, 1, 1, 1, 0, -1, -1, -1];

  const contour: [number, number][] = [[sx, sy]];
  let cx = sx, cy = sy, dir = 7; // start looking NE (arrived from N)

  for (let i = 0; i < width * height * 4; i++) {
    let moved = false;
    for (let d = 0; d < 8; d++) {
      const nd = (dir + d) % 8;
      const nx = cx + ddx[nd], ny = cy + ddy[nd];
      if (get(nx, ny)) {
        cx = nx; cy = ny;
        if (cx === sx && cy === sy && contour.length > 2) {
          return douglasPeucker(contour, Math.max(2, contour.length * 0.005));
        }
        contour.push([cx, cy]);
        dir = (nd + 5) % 8;
        moved = true;
        break;
      }
    }
    if (!moved) break;
  }

  return douglasPeucker(contour, Math.max(2, contour.length * 0.005));
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
    const l = douglasPeucker(pts.slice(0, idx + 1), eps);
    const r = douglasPeucker(pts.slice(idx), eps);
    return [...l.slice(0, -1), ...r];
  }
  return [pts[0], pts[pts.length - 1]];
}

// ─── Messaging ────────────────────────────────────────────────────────────────

function post(msg: WorkerOutMsg) {
  self.postMessage(msg);
}

self.onmessage = async (e: MessageEvent<WorkerInMsg>) => {
  const msg = e.data;
  try {
    if (msg.type === "encode") {
      await encode(msg.id, msg.imageUrl);
    } else if (msg.type === "segment") {
      await segment(msg.id, msg.sessionId, msg.box, msg.points);
    }
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err);
    if (msg.type === "encode") post({ type: "encode:error", id: msg.id, error });
    else if (msg.type === "segment") post({ type: "segment:error", id: msg.id, error });
  }
};

init().catch((err) => {
  post({ type: "status", text: `Init failed: ${err}` });
});
