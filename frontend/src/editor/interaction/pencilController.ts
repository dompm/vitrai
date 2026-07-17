import { useSyncExternalStore } from 'react';
import { createRafScheduler } from './rafScheduler';

export interface PencilSnapshot {
  flatPoints: readonly number[];
  version: number;
}

const EMPTY_SNAPSHOT: PencilSnapshot = { flatPoints: [], version: 0 };

export class PencilController {
  private tuples: [number, number][] = [];
  private flat: number[] = [];
  private snapshot = EMPTY_SNAPSHOT;
  private listeners = new Set<() => void>();
  private scheduler = createRafScheduler();

  getSnapshot = () => this.snapshot;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  start(point: [number, number]) {
    this.tuples = [point];
    this.flat = [point[0], point[1]];
    this.publish();
  }

  capture(point: [number, number]) {
    if (this.tuples.length === 0) return;
    this.tuples.push(point);
    this.flat.push(point[0], point[1]);
    this.scheduler.schedule(() => this.publish());
  }

  finish(): [number, number][] {
    this.scheduler.flush();
    const points = this.tuples;
    this.clear();
    return points;
  }

  clear() {
    this.scheduler.cancel();
    this.tuples = [];
    this.flat = [];
    this.publish();
  }

  get rawPointCount() {
    return this.tuples.length;
  }

  private publish() {
    this.snapshot = { flatPoints: this.flat.slice(), version: this.snapshot.version + 1 };
    this.listeners.forEach(listener => listener());
  }
}

export function usePencilSnapshot(controller: PencilController) {
  return useSyncExternalStore(controller.subscribe, controller.getSnapshot, () => EMPTY_SNAPSHOT);
}
