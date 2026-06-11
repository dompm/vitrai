import { AutoProcessor, AutoModelForImageTextToText, RawImage } from '@huggingface/transformers';
import type { GlassMaterialParams } from './types';
import { parseVlmChoices, VLM_CATEGORY_PROMPT, VLM_SURFACE_PROMPT } from './utils/glassMaterial';

// Single switch point for the estimation model. Weights are streamed from the
// HF CDN on first use and cached by transformers.js in the browser Cache API.
export const VLM_MODEL_ID = 'onnx-community/Qwen3-VL-2B-Instruct-ONNX';
const VLM_DTYPE = 'q4f16';

// ─── Types ────────────────────────────────────────────────────────────────────

export type VlmInMsg =
  | { type: 'estimate'; id: string; bitmap: ImageBitmap };

export type VlmOutMsg =
  | { type: 'status'; text: string }
  | { type: 'progress'; fraction: number }
  | { type: 'estimate:done'; id: string; raw: string; params: GlassMaterialParams }
  | { type: 'estimate:error'; id: string; error: string };

function post(msg: VlmOutMsg) { self.postMessage(msg); }

// ─── Lazy model init ──────────────────────────────────────────────────────────

// transformers.js typings are too loose for the multimodal processor call
// chain, so the session objects are kept as `any`.
let processor: any = null;
let model: any = null;
let loadPromise: Promise<void> | null = null;

const downloadProgress = new Map<string, { loaded: number; total: number }>();

function onFileProgress(p: { status: string; file?: string; loaded?: number; total?: number }) {
  if (p.status !== 'progress' || !p.file) return;
  downloadProgress.set(p.file, { loaded: p.loaded ?? 0, total: p.total ?? 0 });
  let loaded = 0;
  let total = 0;
  for (const stats of downloadProgress.values()) {
    loaded += stats.loaded;
    total += stats.total;
  }
  if (total > 0) post({ type: 'progress', fraction: loaded / total });
}

async function ensureLoaded(): Promise<void> {
  if (processor && model) return;
  if (!loadPromise) {
    loadPromise = (async () => {
      if (!('gpu' in navigator)) {
        throw new Error('no-webgpu');
      }
      post({ type: 'status', text: 'loading' });
      processor = await AutoProcessor.from_pretrained(VLM_MODEL_ID, {
        progress_callback: onFileProgress,
      });
      model = await AutoModelForImageTextToText.from_pretrained(VLM_MODEL_ID, {
        device: 'webgpu',
        dtype: VLM_DTYPE,
        progress_callback: onFileProgress,
      });
      post({ type: 'progress', fraction: 1 });
    })().catch(err => {
      // Allow a retry after a failed download.
      loadPromise = null;
      processor = null;
      model = null;
      throw err;
    });
  }
  await loadPromise;
}

// ─── Estimate ─────────────────────────────────────────────────────────────────

async function ask(image: RawImage, question: string): Promise<string> {
  const conversation = [
    { role: 'user', content: [{ type: 'image' }, { type: 'text', text: question }] },
  ];
  const prompt = processor.apply_chat_template(conversation, { add_generation_prompt: true });
  const inputs = await processor(prompt, image);
  const outputs = await model.generate({
    ...inputs,
    max_new_tokens: 6,
    do_sample: false,
  });
  const decoded: string[] = processor.batch_decode(
    outputs.slice(null, [inputs.input_ids.dims.at(-1), null]),
    { skip_special_tokens: true },
  );
  return decoded[0] ?? '';
}

async function estimate(id: string, bitmap: ImageBitmap) {
  await ensureLoaded();
  post({ type: 'status', text: 'analyzing' });

  const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
  canvas.getContext('2d')!.drawImage(bitmap, 0, 0);
  bitmap.close();
  const image = await RawImage.fromCanvas(canvas);

  const categoryAnswer = await ask(image, VLM_CATEGORY_PROMPT);
  const surfaceAnswer = await ask(image, VLM_SURFACE_PROMPT);
  const raw = `category=${categoryAnswer} surface=${surfaceAnswer}`;
  console.log('[VLM Worker] Answers:', raw);
  post({ type: 'estimate:done', id, raw, params: parseVlmChoices(categoryAnswer, surfaceAnswer) });
}

// ─── Messaging ────────────────────────────────────────────────────────────────

self.onmessage = async (e: MessageEvent<VlmInMsg>) => {
  const msg = e.data;
  if (msg.type !== 'estimate') return;
  try {
    await estimate(msg.id, msg.bitmap);
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err);
    console.error('[VLM Worker] Estimate failed:', err);
    post({ type: 'estimate:error', id: msg.id, error });
  }
};
