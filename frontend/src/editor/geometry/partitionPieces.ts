/** Contiguous ranges preserve exact paint order, including everything after the active node. */
export function partitionPieces<T>(
  nodes: T[],
  index: number,
  followingWithActive: boolean,
): [string, T[]][] {
  if (index < 0) return [["all", nodes]];
  return [
    ["before", nodes.slice(0, index)],
    ["active", nodes.slice(index, followingWithActive ? undefined : index + 1)],
    ...(!followingWithActive
      ? [["after", nodes.slice(index + 1)] as [string, T[]]]
      : []),
  ].filter(([, nodes]) => nodes.length) as [string, T[]][];
}
