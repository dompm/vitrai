import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PieceTransformPreviewStore } from '../interaction/pieceTransformPreviewStore';

describe('piece transform preview store', () => {
  let queuedFrame: FrameRequestCallback | null;

  beforeEach(() => {
    queuedFrame = null;
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      queuedFrame = callback;
      return 1;
    });
    vi.stubGlobal('cancelAnimationFrame', vi.fn());
  });

  it('stores newest values immediately and notifies once per frame', () => {
    const store = new PieceTransformPreviewStore();
    const listener = vi.fn();
    store.subscribe('piece', listener);
    store.schedule('piece', { x: 1, y: 2, rotation: 0, scale: 1 });
    store.schedule('piece', { x: 3, y: 4, rotation: 0, scale: 1 });
    expect(store.get('piece')?.x).toBe(3);
    expect(listener).not.toHaveBeenCalled();
    queuedFrame?.(0);
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it('flushes exact final values and clears only after matching commit', () => {
    const store = new PieceTransformPreviewStore();
    const final = { x: 8, y: 9, rotation: 1, scale: 2 };
    store.flush('piece', final);
    store.reconcile([{ id: 'piece', label: 'Piece', polygon: [], glassSheetId: '', transform: { ...final, x: 7 } }]);
    expect(store.get('piece')).toBe(final);
    store.reconcile([{ id: 'piece', label: 'Piece', polygon: [], glassSheetId: '', transform: final }]);
    expect(store.get('piece')).toBeNull();
  });

  it('publishes a group preview once per frame and one global lamp update', () => {
    const store = new PieceTransformPreviewStore();
    const firstListener = vi.fn();
    const secondListener = vi.fn();
    const globalListener = vi.fn();
    store.subscribe('first', firstListener);
    store.subscribe('second', secondListener);
    store.subscribeAll(globalListener);

    store.scheduleMany([
      { pieceId: 'first', transform: { x: 10, y: 20, rotation: 0, scale: 1 } },
      { pieceId: 'second', transform: { x: 30, y: 40, rotation: 0, scale: 1 } },
    ]);
    expect(globalListener).not.toHaveBeenCalled();
    queuedFrame?.(0);

    expect(firstListener).toHaveBeenCalledTimes(1);
    expect(secondListener).toHaveBeenCalledTimes(1);
    expect(globalListener).toHaveBeenCalledTimes(1);
    expect(store.getVersion()).toBe(1);
  });

  it('clears no-op gestures and all previews on project switch', () => {
    const store = new PieceTransformPreviewStore();
    const start = { x: 1, y: 2, rotation: 0, scale: 1 };
    store.flush('piece', start);
    store.clear('piece');
    expect(store.get('piece')).toBeNull();
    store.flush('piece', { ...start, x: 5 });
    store.flush('other', { ...start, y: 8 });
    store.cancelAll();
    expect(store.get('piece')).toBeNull();
    expect(store.get('other')).toBeNull();
  });

  it('records one durable write for a 300-event transform gesture', () => {
    const store = new PieceTransformPreviewStore();
    const commitProject = vi.fn();
    for (let event = 0; event < 300; event += 1) {
      store.schedule('piece', { x: event, y: event, rotation: 0, scale: 1 });
    }
    const final = store.get('piece');
    expect(final).not.toBeNull();
    store.flush('piece', final!);
    commitProject(final);
    expect(commitProject).toHaveBeenCalledTimes(1);
  });
});
