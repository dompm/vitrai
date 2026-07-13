import { useSyncExternalStore } from 'react';

export interface ViewportSnapshot {
  pan: { x: number; y: number };
  zoom: number;
  displayScale: number;
  effectiveScale: number;
  isPanning: boolean;
  isPinching: boolean;
  version: number;
}

export class ViewportStore {
  private snapshot: ViewportSnapshot = {
    pan: { x: 0, y: 0 }, zoom: 1, displayScale: 1, effectiveScale: 1,
    isPanning: false, isPinching: false, version: 0,
  };
  private listeners = new Set<() => void>();
  private frame: number | null = null;

  getSnapshot = () => this.snapshot;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => this.listeners.delete(listener); };

  update(values: Partial<Omit<ViewportSnapshot, 'version'>>, immediate = false) {
    this.snapshot = { ...this.snapshot, ...values, version: this.snapshot.version + 1 };
    if (immediate) { this.flush(); return; }
    if (this.frame === null) this.frame = requestAnimationFrame(() => this.flush());
  }

  flush() {
    if (this.frame !== null) cancelAnimationFrame(this.frame);
    this.frame = null;
    this.listeners.forEach(listener => listener());
  }

  destroy() {
    if (this.frame !== null) cancelAnimationFrame(this.frame);
    this.frame = null;
    this.listeners.clear();
  }
}

export function useViewportSnapshot(store: ViewportStore) {
  return useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
}

export function ViewportSubscriber({ store, children }: { store: ViewportStore; children: (snapshot: ViewportSnapshot) => React.ReactNode }) {
  return children(useViewportSnapshot(store));
}
