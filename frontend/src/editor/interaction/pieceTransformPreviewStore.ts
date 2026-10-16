import { useSyncExternalStore } from 'react';
import type { Piece, TextureTransform } from '../../types';

const transformsEqual = (a: TextureTransform, b: TextureTransform) =>
  a.x === b.x && a.y === b.y && a.rotation === b.rotation && a.scale === b.scale;

export class PieceTransformPreviewStore {
  private previews = new Map<string, TextureTransform>();
  private listeners = new Map<string, Set<() => void>>();
  private globalListeners = new Set<() => void>();
  private scheduledIds = new Set<string>();
  private frame: number | null = null;
  private version = 0;

  get = (pieceId: string): TextureTransform | null => this.previews.get(pieceId) ?? null;
  getVersion = () => this.version;

  subscribe = (pieceId: string, listener: () => void) => {
    let listeners = this.listeners.get(pieceId);
    if (!listeners) {
      listeners = new Set();
      this.listeners.set(pieceId, listeners);
    }
    listeners.add(listener);
    return () => {
      listeners?.delete(listener);
      if (listeners?.size === 0) this.listeners.delete(pieceId);
    };
  };

  subscribeAll = (listener: () => void) => {
    this.globalListeners.add(listener);
    return () => this.globalListeners.delete(listener);
  };

  schedule(pieceId: string, transform: TextureTransform) {
    this.scheduleMany([{ pieceId, transform }]);
  }

  scheduleMany(updates: Array<{ pieceId: string; transform: TextureTransform }>) {
    if (updates.length === 0) return;
    updates.forEach(({ pieceId, transform }) => {
      this.previews.set(pieceId, transform);
      this.scheduledIds.add(pieceId);
    });
    if (this.frame !== null) return;
    this.frame = requestAnimationFrame(() => {
      this.frame = null;
      const ids = [...this.scheduledIds];
      this.scheduledIds.clear();
      if (ids.length === 0) return;
      ids.forEach(id => this.notify(id));
      this.notifyAll();
    });
  }

  flush(pieceId: string, transform: TextureTransform) {
    this.flushMany([{ pieceId, transform }]);
  }

  flushMany(updates: Array<{ pieceId: string; transform: TextureTransform }>) {
    if (updates.length === 0) return;
    updates.forEach(({ pieceId, transform }) => {
      this.previews.set(pieceId, transform);
      this.scheduledIds.delete(pieceId);
      this.notify(pieceId);
    });
    this.notifyAll();
  }

  clear(pieceId: string) {
    if (!this.previews.delete(pieceId)) return;
    this.scheduledIds.delete(pieceId);
    this.notify(pieceId);
    this.notifyAll();
  }

  reconcile(pieces: Piece[]) {
    const committed = new Map(pieces.map(piece => [piece.id, piece.transform]));
    const clearedIds: string[] = [];
    for (const [pieceId, preview] of this.previews) {
      const transform = committed.get(pieceId);
      if (!transform || transformsEqual(transform, preview)) {
        this.previews.delete(pieceId);
        this.scheduledIds.delete(pieceId);
        clearedIds.push(pieceId);
      }
    }
    clearedIds.forEach(id => this.notify(id));
    if (clearedIds.length > 0) this.notifyAll();
  }

  cancelAll() {
    if (this.frame !== null) cancelAnimationFrame(this.frame);
    this.frame = null;
    const ids = [...this.previews.keys()];
    this.previews.clear();
    this.scheduledIds.clear();
    ids.forEach(id => this.notify(id));
    if (ids.length > 0) this.notifyAll();
  }

  private notify(pieceId: string) {
    this.listeners.get(pieceId)?.forEach(listener => listener());
  }

  private notifyAll() {
    this.version += 1;
    this.globalListeners.forEach(listener => listener());
  }
}

export function usePieceTransformPreview(
  store: PieceTransformPreviewStore,
  pieceId: string,
): TextureTransform | null {
  return useSyncExternalStore(
    listener => store.subscribe(pieceId, listener),
    () => store.get(pieceId),
    () => null,
  );
}

export function usePieceTransformPreviewVersion(store: PieceTransformPreviewStore): number {
  return useSyncExternalStore(store.subscribeAll, store.getVersion, store.getVersion);
}
