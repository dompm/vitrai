import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PencilController } from '../interaction/pencilController';

describe('PencilController', () => {
  let frame: FrameRequestCallback | null;
  beforeEach(() => {
    frame = null;
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { frame = callback; return 1; });
    vi.stubGlobal('cancelAnimationFrame', vi.fn());
  });

  it('captures every raw event but publishes movement once per frame', () => {
    const controller = new PencilController();
    const listener = vi.fn();
    controller.subscribe(listener);
    controller.start([0, 0]);
    for (let i = 1; i <= 300; i += 1) controller.capture([i, i]);
    expect(controller.rawPointCount).toBe(301);
    expect(listener).toHaveBeenCalledTimes(1);
    frame?.(0);
    expect(listener).toHaveBeenCalledTimes(2);
    expect(controller.getSnapshot().flatPoints).toHaveLength(602);
    expect(controller.finish()).toHaveLength(301);
  });

  it('clears pending strokes without publishing stale scheduled work', () => {
    const controller = new PencilController();
    controller.start([1, 2]);
    controller.capture([3, 4]);
    controller.clear();
    expect(controller.rawPointCount).toBe(0);
    expect(controller.getSnapshot().flatPoints).toEqual([]);
  });
});
