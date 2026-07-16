export interface RafScheduler {
  schedule(task: () => void): void;
  flush(): void;
  cancel(): void;
}

export function createRafScheduler(): RafScheduler {
  let frame: number | null = null;
  let pending: (() => void) | null = null;
  const run = () => {
    frame = null;
    const task = pending;
    pending = null;
    task?.();
  };
  return {
    schedule(task) {
      pending = task;
      if (frame === null) frame = requestAnimationFrame(run);
    },
    flush() {
      if (frame !== null) cancelAnimationFrame(frame);
      run();
    },
    cancel() {
      if (frame !== null) cancelAnimationFrame(frame);
      frame = null;
      pending = null;
    },
  };
}
