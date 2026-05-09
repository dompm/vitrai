// Abstraction over three SAM inference backends:
//   "server"  – existing HTTP API (Modal cloud GPU or local CPU via LOCAL_SAM=true)
//   "webgpu"  – Transformers.js running sam-vit-base in-browser (WebGPU / WASM fallback)

import { encodeImage, segment as httpSegment, autoSegment as httpAutoSegment } from "./api";
import type { BoundingBox, Crop } from "./types";
import type { WorkerInMsg, WorkerOutMsg } from "./samWorker";

// ─── Interface ────────────────────────────────────────────────────────────────

export type BackendType = "server" | "webgpu";

export interface SamBackend {
  readonly type: BackendType;
  readonly supportsAutoSegment: boolean;
  encode(imageUrl: string): Promise<string>;
  segment(
    imageId: string,
    box?: BoundingBox,
    points?: { x: number; y: number; label: number }[],
  ): Promise<[number, number][]>;
  autoSegment(imageId: string, crop?: Crop): Promise<[number, number][][]>;
}

// ─── Server backend (HTTP) ────────────────────────────────────────────────────

class ServerSamBackend implements SamBackend {
  readonly type = "server" as const;
  readonly supportsAutoSegment = true;

  encode(imageUrl: string) {
    return encodeImage(imageUrl);
  }

  segment(imageId: string, box?: BoundingBox, points?: { x: number; y: number; label: number }[]) {
    return httpSegment(imageId, box, points);
  }

  autoSegment(imageId: string, crop?: Crop) {
    return httpAutoSegment(imageId, crop);
  }
}

// ─── WebGPU backend (Transformers.js worker) ──────────────────────────────────

class WebGPUSamBackend implements SamBackend {
  readonly type = "webgpu" as const;
  readonly supportsAutoSegment = false;

  private worker: Worker;
  private readyPromise: Promise<string>; // resolves to the device used
  private pending = new Map<string, { resolve: (v: unknown) => void; reject: (e: Error) => void }>();
  private onStatusChange: (s: string) => void;

  constructor(onStatusChange: (s: string) => void) {
    this.onStatusChange = onStatusChange;
    this.worker = new Worker(new URL("./samWorker.ts", import.meta.url), { type: "module" });

    let resolveReady!: (device: string) => void;
    let rejectReady!: (e: Error) => void;
    this.readyPromise = new Promise<string>((res, rej) => {
      resolveReady = res;
      rejectReady = rej;
    });

    this.worker.onmessage = (e: MessageEvent<WorkerOutMsg>) => {
      const msg = e.data;
      if (msg.type === "ready") {
        onStatusChange(`WebGPU ready (${msg.device})`);
        resolveReady(msg.device);
      } else if (msg.type === "status") {
        onStatusChange(msg.text);
      } else {
        const p = this.pending.get(msg.id);
        if (!p) return;
        this.pending.delete(msg.id);
        if (msg.type === "encode:done") p.resolve(msg.sessionId);
        else if (msg.type === "segment:done") p.resolve(msg.polygon);
        else p.reject(new Error(msg.error));
      }
    };

    this.worker.onerror = (e) => {
      rejectReady(new Error(e.message));
    };
  }

  private send<T>(msg: WorkerInMsg): Promise<T> {
    return this.readyPromise.then(
      () =>
        new Promise<T>((resolve, reject) => {
          this.pending.set(msg.id, { resolve: resolve as (v: unknown) => void, reject });
          this.worker.postMessage(msg);
        }),
    );
  }

  encode(imageUrl: string): Promise<string> {
    return this.send<string>({ type: "encode", id: crypto.randomUUID(), imageUrl });
  }

  async segment(
    imageId: string,
    box?: BoundingBox,
    points?: { x: number; y: number; label: number }[],
  ): Promise<[number, number][]> {
    return this.send<[number, number][]>({
      type: "segment",
      id: crypto.randomUUID(),
      sessionId: imageId,
      box: box ? [box.x1, box.y1, box.x2, box.y2] : undefined,
      points: points?.map((p) => [p.x, p.y, p.label]),
    });
  }

  autoSegment(): Promise<[number, number][][]> {
    return Promise.reject(new Error("auto_segment not supported in WebGPU mode"));
  }

  terminate() {
    this.worker.terminate();
  }
}

// ─── Factory & cache ──────────────────────────────────────────────────────────

const cache: Partial<Record<BackendType, SamBackend>> = {};

export function getBackend(
  type: BackendType,
  onStatusChange: (s: string) => void = () => {},
): SamBackend {
  if (!cache[type]) {
    if (type === "server") {
      cache[type] = new ServerSamBackend();
    } else {
      cache[type] = new WebGPUSamBackend(onStatusChange);
    }
  }
  return cache[type]!;
}
