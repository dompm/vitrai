import type { GlassMaterialParams } from './types';
import type { VlmInMsg, VlmOutMsg } from './vlmWorker';

// Downscale uploads before transferring to the worker — the vision encoder
// works at low resolution anyway and this caps GPU memory.
const MAX_IMAGE_DIM = 448;

// The loaded model holds 1-2 GB of GPU memory, so the worker is torn down
// after a short idle period. Weights stay in the browser Cache API; the next
// estimate only re-pays session setup.
const IDLE_TIMEOUT_MS = 30_000;

export interface GlassEstimator {
  /** WebGPU is required — a 2B decoder on wasm is unusably slow. */
  isAvailable(): boolean;
  estimate(imageDataUrl: string): Promise<GlassMaterialParams>;
  onProgress: (fraction: number) => void;
  onStatus: (text: string) => void;
  disposeNow(): void;
}

class LocalVlmEstimator implements GlassEstimator {
  private worker: Worker | null = null;
  private pending = new Map<string, { resolve: (p: GlassMaterialParams) => void; reject: (e: Error) => void }>();
  private idleTimer: ReturnType<typeof setTimeout> | null = null;
  private queue: Promise<unknown> = Promise.resolve();
  onProgress: (fraction: number) => void = () => {};
  onStatus: (text: string) => void = () => {};

  isAvailable(): boolean {
    return typeof navigator !== 'undefined' && 'gpu' in navigator;
  }

  estimate(imageDataUrl: string): Promise<GlassMaterialParams> {
    // Serialize concurrent calls — the worker runs one generation at a time.
    const run = this.queue.then(() => this.estimateOne(imageDataUrl));
    this.queue = run.catch(() => {});
    return run;
  }

  disposeNow(): void {
    if (this.idleTimer) { clearTimeout(this.idleTimer); this.idleTimer = null; }
    this.worker?.terminate();
    this.worker = null;
    const err = new Error('disposed');
    this.pending.forEach(p => p.reject(err));
    this.pending.clear();
  }

  private async estimateOne(imageDataUrl: string): Promise<GlassMaterialParams> {
    if (!this.isAvailable()) throw new Error('no-webgpu');
    if (this.idleTimer) { clearTimeout(this.idleTimer); this.idleTimer = null; }

    const blob = await fetch(imageDataUrl).then(r => r.blob());
    const probe = await createImageBitmap(blob);
    const scale = Math.min(1, MAX_IMAGE_DIM / Math.max(probe.width, probe.height));
    const bitmap = scale < 1
      ? await createImageBitmap(blob, {
          resizeWidth: Math.round(probe.width * scale),
          resizeHeight: Math.round(probe.height * scale),
          resizeQuality: 'high',
        })
      : probe;
    if (bitmap !== probe) probe.close();

    const worker = this.ensureWorker();
    const id = crypto.randomUUID();
    try {
      return await new Promise<GlassMaterialParams>((resolve, reject) => {
        this.pending.set(id, { resolve, reject });
        const msg: VlmInMsg = { type: 'estimate', id, bitmap };
        worker.postMessage(msg, [bitmap]);
      });
    } finally {
      this.scheduleIdleDispose();
    }
  }

  private ensureWorker(): Worker {
    if (this.worker) return this.worker;
    const worker = new Worker(new URL('./vlmWorker.ts', import.meta.url), { type: 'module' });
    worker.onmessage = (e: MessageEvent<VlmOutMsg>) => {
      const msg = e.data;
      if (msg.type === 'status') {
        this.onStatus(msg.text);
      } else if (msg.type === 'progress') {
        this.onProgress(msg.fraction);
      } else {
        const p = this.pending.get(msg.id);
        if (!p) return;
        this.pending.delete(msg.id);
        if (msg.type === 'estimate:done') p.resolve(msg.params);
        else p.reject(new Error(msg.error));
      }
    };
    worker.onerror = (e) => {
      const err = new Error(e.message || 'VLM worker crashed');
      this.pending.forEach(p => p.reject(err));
      this.pending.clear();
      worker.terminate();
      if (this.worker === worker) this.worker = null;
    };
    this.worker = worker;
    return worker;
  }

  private scheduleIdleDispose() {
    if (this.idleTimer) clearTimeout(this.idleTimer);
    this.idleTimer = setTimeout(() => {
      if (this.pending.size === 0) this.disposeNow();
    }, IDLE_TIMEOUT_MS);
  }
}

declare global { interface Window { __glassEstimator?: GlassEstimator } }

export function getGlassEstimator(): GlassEstimator {
  if (!window.__glassEstimator) {
    window.__glassEstimator = new LocalVlmEstimator();
  }
  return window.__glassEstimator;
}
