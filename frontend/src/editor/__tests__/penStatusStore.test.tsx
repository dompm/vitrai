import { act, create } from 'react-test-renderer';
import { describe, expect, it, vi } from 'vitest';
import { PenStatusStore, usePenStatus } from '../interaction/penStatusStore';

describe('PenStatusStore', () => {
  it('updates the focused status subscriber without rerendering its owning app', () => {
    const store = new PenStatusStore();
    const appRender = vi.fn();
    const statusRender = vi.fn();
    function Status() { const status = usePenStatus(store); statusRender(); return <span>{status.coords?.x}</span>; }
    function AppOwner() { appRender(); return <Status />; }
    act(() => { create(<AppOwner />); });
    act(() => { store.update({ coords: { x: 10, y: 20 }, lastPoint: { x: 0, y: 0 } }); });
    expect(appRender).toHaveBeenCalledTimes(1);
    expect(statusRender).toHaveBeenCalledTimes(2);
  });
});
