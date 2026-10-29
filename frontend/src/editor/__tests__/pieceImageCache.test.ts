import { describe, expect, it, vi } from "vitest";
import { PieceImageCache } from "../interaction/pieceImageCache";
describe("piece image resources", () => {
  it("loads once per URL and preserves the decoded image across piece remounts", () => {
    const image = { src: "", onload: null } as unknown as HTMLImageElement;
    const createImage = vi.fn(() => image),
      listener = vi.fn();
    const cache = new PieceImageCache(createImage);
    expect(cache.get("sheet-a")).toBeUndefined();
    const unsubscribe = cache.subscribe("sheet-a", listener);
    image.onload!.call(image, new Event("load"));
    expect(listener).toHaveBeenCalledTimes(1);
    expect(cache.get("sheet-a")).toBe(image);
    unsubscribe();
    cache.subscribe("sheet-a", listener);
    expect(cache.get("sheet-a")).toBe(image);
    expect(createImage).toHaveBeenCalledTimes(1);
  });
  it("releases replaced URLs and ignores empty image sources", () => {
    const image = { src: "", onload: null } as unknown as HTMLImageElement;
    const createImage = vi.fn(() => image),
      cache = new PieceImageCache(createImage);
    expect(cache.get("")).toBeUndefined();
    expect(createImage).not.toHaveBeenCalled();
    cache.get("sheet-a");
    cache.retain(new Set());
    expect(image.onload).toBeNull();
    cache.get("sheet-a");
    expect(createImage).toHaveBeenCalledTimes(2);
  });
});
