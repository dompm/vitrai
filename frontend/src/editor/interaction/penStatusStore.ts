import { useSyncExternalStore } from 'react';

export interface PenStatus {
  coords: { x: number; y: number } | null;
  lastPoint: { x: number; y: number } | null;
}
const EMPTY: PenStatus = { coords: null, lastPoint: null };

export class PenStatusStore {
  private snapshot = EMPTY;
  private listeners = new Set<() => void>();
  getSnapshot = () => this.snapshot;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => this.listeners.delete(listener); };
  update(status: PenStatus) { this.snapshot = status; this.listeners.forEach(listener => listener()); }
}
export const usePenStatus = (store: PenStatusStore) => useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
