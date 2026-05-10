import type { BoundingBox } from "./types";
import type { WorkerInMsg, WorkerOutMsg } from "./samWorker";

export type SegmentResult = {
  polygon: [number, number][];
  debugMask?: { bitmap: ImageBitmap; width: number; height: number };
};

export class SamWorkerBackend {
  private worker: Worker;
  private readyPromise: Promise<string>;
  private pending = new Map<string, { resolve: (v: unknown) => void; reject: (e: Error) => void }>();
  onDebugMask: (m: { bitmap: ImageBitmap; width: number; height: number }) => void = () => {};

  constructor(onStatusChange: (s: string) => void = () => {}) {
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
        else if (msg.type === "segment:done") {
          if (msg.debugMask) this.onDebugMask(msg.debugMask);
          p.resolve({ polygon: msg.polygon, debugMask: msg.debugMask });
        }
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

  segment(
    imageId: string,
    box?: BoundingBox,
    points?: { x: number; y: number; label: number }[],
  ): Promise<SegmentResult> {
    return this.send<SegmentResult>({
      type: "segment",
      id: crypto.randomUUID(),
      sessionId: imageId,
      box: box ? [box.x1, box.y1, box.x2, box.y2] : undefined,
      points: points?.map((p) => [p.x, p.y, p.label]),
    });
  }
}

declare global { interface Window { __samBackend?: SamWorkerBackend } }

export function getSamBackend(onStatusChange: (s: string) => void = () => {}): SamWorkerBackend {
  if (!window.__samBackend) window.__samBackend = new SamWorkerBackend(onStatusChange);
  return window.__samBackend;
}
