import { act, create } from 'react-test-renderer';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ViewportStore, ViewportSubscriber } from '../viewport/viewportStore';

describe('ViewportStore', () => {
  let frame: FrameRequestCallback | null;
  beforeEach(() => {
    frame = null;
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { frame = callback; return 1; });
    vi.stubGlobal('cancelAnimationFrame', vi.fn());
  });

  it('publishes an event burst at most once per animation frame', () => {
    const store = new ViewportStore();
    const listener = vi.fn();
    store.subscribe(listener);
    for (let event = 0; event < 300; event += 1) {
      store.update({ pan: { x: event, y: event }, zoom: 1 + event / 1000 });
    }
    expect(store.getSnapshot().pan.x).toBe(299);
    expect(listener).not.toHaveBeenCalled();
    frame?.(0);
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it('rerenders only the focused subscriber, not its owning panel', () => {
    const store = new ViewportStore();
    const parentRender = vi.fn();
    const viewportRender = vi.fn();
    function OwningPanel() {
      parentRender();
      return <ViewportSubscriber store={store}>{snapshot => { viewportRender(snapshot.version); return <span>{snapshot.pan.x}</span>; }}</ViewportSubscriber>;
    }
    act(() => { create(<OwningPanel />); });
    for (let event = 0; event < 100; event += 1) store.update({ pan: { x: event, y: 0 } });
    act(() => { frame?.(0); });
    expect(parentRender).toHaveBeenCalledTimes(1);
    expect(viewportRender).toHaveBeenCalledTimes(2);
  });
});
