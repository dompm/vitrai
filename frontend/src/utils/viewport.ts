export function toImageCoords(
  ptr: { x: number; y: number },
  pan: { x: number; y: number },
  effectiveScale: number,
) {
  return {
    x: (ptr.x - pan.x) / effectiveScale,
    y: (ptr.y - pan.y) / effectiveScale,
  };
}

export function toScreenCoords(
  imgX: number,
  imgY: number,
  pan: { x: number; y: number },
  effectiveScale: number,
) {
  return {
    x: imgX * effectiveScale + pan.x,
    y: imgY * effectiveScale + pan.y,
  };
}
