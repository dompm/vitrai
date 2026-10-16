import { act, create } from 'react-test-renderer';
import { beforeEach, describe, expect, it, vi } from 'vitest';
vi.mock('react-konva', () => ({ Group: ({ children }: { children: React.ReactNode }) => <>{children}</> }));
import { ViewportGroup, ViewportStore, ViewportSubscriber, useViewportEffectiveScale } from '../viewport/viewportStore';

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

  it('updates a viewport group without recreating stable expensive canvas children', () => {
    const store = new ViewportStore();
    const expensivePieceRender = vi.fn();
    function ExpensivePiece() { expensivePieceRender(); return <span>piece</span>; }
    const stablePiece = <ExpensivePiece />;
    act(() => { create(<ViewportGroup store={store}>{stablePiece}</ViewportGroup>); });
    for (let event = 0; event < 100; event += 1) store.update({ pan: { x: event, y: event } });
    act(() => { frame?.(0); });
    expect(expensivePieceRender).toHaveBeenCalledTimes(1);
  });

  it('does not rerender scale-aware pieces while panning', () => {
    const store = new ViewportStore();
    const pieceRender = vi.fn();
    function ScaleAwarePiece() {
      const effectiveScale = useViewportEffectiveScale(store);
      pieceRender(effectiveScale);
      return <span>piece</span>;
    }
    const stablePiece = <ScaleAwarePiece />;
    act(() => { create(<ViewportGroup store={store}>{stablePiece}</ViewportGroup>); });

    for (let event = 0; event < 100; event += 1) store.update({ pan: { x: event, y: event } });
    act(() => { frame?.(0); });
    expect(pieceRender).toHaveBeenCalledTimes(1);

    store.update({ effectiveScale: 2 });
    act(() => { frame?.(16); });
    expect(pieceRender).toHaveBeenCalledTimes(2);
    expect(pieceRender).toHaveBeenLastCalledWith(2);
  });
});
