import { create } from "react-test-renderer";
import { describe, expect, it, vi } from "vitest";
vi.mock("react-konva", () => ({
  Layer: ({ children }: { children: React.ReactNode }) => (
    <section>{children}</section>
  ),
}));
vi.mock("../viewport/viewportStore", () => ({
  ViewportGroup: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));
import { PieceViewportLayers } from "../../components/canvas/PieceViewportLayers";
import type { ViewportStore } from "../viewport/viewportStore";
import { partitionPieces } from "../geometry/partitionPieces";
function Piece({ piece }: { piece: { id: string } }) {
  return <span>{piece.id}</span>;
}
describe("selected-piece drawing ranges", () => {
  it("preserves contiguous paint order for every selection position", () => {
    for (let count = 1; count <= 50; count++) {
      const nodes = Array.from({ length: count }, (_, index) => index);
      for (let index = -1; index < count; index++)
        for (const following of [false, true]) {
          const parts = partitionPieces(nodes, index, following);
          expect(parts.flatMap(([, nodes]) => nodes)).toEqual(nodes);
          expect(parts.length).toBeLessThanOrEqual(3);
        }
    }
  });
  it("isolates the selected piece without moving neighbors above or below it", () => {
    const nodes = ["a", "b", "c"].map((id) => (
      <Piece key={id} piece={{ id }} />
    ));
    const tree = create(
      <PieceViewportLayers store={{} as ViewportStore} activeId="b">
        {nodes}
      </PieceViewportLayers>,
    );
    expect(
      tree.root
        .findAllByType("section")
        .map((layer) =>
          layer.findAllByType("span").map((span) => span.children[0]),
        ),
    ).toEqual([["a"], ["b"], ["c"]]);
    tree.update(
      <PieceViewportLayers store={{} as ViewportStore} activeId="b" disabled>
        {nodes}
      </PieceViewportLayers>,
    );
    expect(tree.root.findAllByType("section")).toHaveLength(1);
    tree.unmount();
  });
  it("keeps handles after active content and screen overlays on the final drawing surface", () => {
    const nodes = ["a", "b", "c"].map((id) => (
      <Piece key={id} piece={{ id }} />
    ));
    const tree = create(
      <PieceViewportLayers
        store={{} as ViewportStore}
        activeId="b"
        followingWithActive
        overlay={<p>guides</p>}
      >
        {nodes}
      </PieceViewportLayers>,
    );
    const layers = tree.root.findAllByType("section");
    expect(
      layers.map((layer) =>
        layer.findAllByType("span").map((span) => span.children[0]),
      ),
    ).toEqual([["a"], ["b", "c"]]);
    expect(layers[0].findAllByType("p")).toHaveLength(0);
    expect(layers[1].findAllByType("p")).toHaveLength(1);
    tree.unmount();
  });
});
