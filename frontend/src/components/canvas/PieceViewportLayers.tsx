import { partitionPieces } from "../../editor/geometry/partitionPieces";
import { Children, isValidElement, type ComponentProps } from "react";
import { Layer } from "react-konva";
import { ViewportGroup } from "../../editor/viewport/viewportStore";

/** Preserve source order while isolating one selected piece's repaint. */
export function PieceViewportLayers({
  children,
  activeId,
  followingWithActive = false,
  overlay,
  disabled = false,
  ...viewportProps
}: ComponentProps<typeof ViewportGroup> & {
  activeId?: string;
  followingWithActive?: boolean;
  overlay?: React.ReactNode;
  disabled?: boolean;
}) {
  const nodes = Children.toArray(children);
  const index =
    activeId && !disabled
      ? nodes.findIndex(
          (node) =>
            isValidElement<{ piece?: { id: string }; handleOnly?: boolean }>(
              node,
            ) &&
            node.props.piece?.id === activeId &&
            !node.props.handleOnly,
        )
      : -1;
  const buckets = partitionPieces(nodes, index, followingWithActive);
  return (
    <>
      {buckets.map(([key, nodes], index) => (
        <Layer key={key} listening={viewportProps.listening}>
          <ViewportGroup {...viewportProps}>{nodes}</ViewportGroup>
          {index === buckets.length - 1 && overlay}
        </Layer>
      ))}
    </>
  );
}
