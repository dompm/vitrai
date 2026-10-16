import { useRef, useCallback } from "react";
/** Stable handler identity with the latest committed render's editing context. */
export function useEvent<T extends (...args: never[]) => unknown>(
  handler: T,
): T {
  const ref = useRef(handler);
  ref.current = handler;
  return useCallback(
    ((...args: Parameters<T>) => ref.current(...args)) as T,
    [],
  );
}
