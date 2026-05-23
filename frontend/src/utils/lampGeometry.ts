import type { LampConfig } from '../types';

export interface UnrolledLamp {
  width: number;
  height: number;
  // Closed polygon outline of the unrolled lamp surface, in pattern coords.
  outline: [number, number][];
  // Slanted seams between adjacent facets within a tier.
  facetSeams: { x1: number; y1: number; x2: number; y2: number }[];
  // Horizontal seams between adjacent tiers.
  tierSeams: { x1: number; y1: number; x2: number; y2: number }[];
}

const PAD = 40;

export function computeUnrolledLamp(config: LampConfig | undefined | null): UnrolledLamp {
  if (!config || config.profilePoints.length < 2 || config.facetCount < 3) {
    return { width: 800, height: 600, outline: [], facetSeams: [], tierSeams: [] };
  }

  const { facetCount: N, profilePoints } = config;
  const sinPiN = Math.sin(Math.PI / N);

  // Tier-by-tier slant heights and unrolled widths (top/bottom).
  const tierSlants: number[] = [];
  const tierWidths: { top: number; bot: number }[] = [];
  for (let t = 0; t < profilePoints.length - 1; t++) {
    const top = profilePoints[t];
    const bot = profilePoints[t + 1];
    const dy = bot.y - top.y;
    const dr = bot.r - top.r;
    tierSlants.push(Math.hypot(dr, dy));
    tierWidths.push({ top: 2 * N * top.r * sinPiN, bot: 2 * N * bot.r * sinPiN });
  }

  const maxWidth = Math.max(...tierWidths.flatMap(t => [t.top, t.bot]));
  const totalHeight = tierSlants.reduce((a, b) => a + b, 0);

  const width = maxWidth + 2 * PAD;
  const height = totalHeight + 2 * PAD;
  const cx = width / 2;

  // Polygon outline: top edge, down the right through every tier, bottom edge, up the left.
  const outline: [number, number][] = [];
  let y = PAD;
  outline.push([cx - tierWidths[0].top / 2, y]);
  outline.push([cx + tierWidths[0].top / 2, y]);
  for (let t = 0; t < tierWidths.length; t++) {
    y += tierSlants[t];
    outline.push([cx + tierWidths[t].bot / 2, y]);
  }
  outline.push([cx - tierWidths[tierWidths.length - 1].bot / 2, y]);
  for (let t = tierWidths.length - 1; t >= 0; t--) {
    y -= tierSlants[t];
    outline.push([cx - tierWidths[t].top / 2, y]);
  }

  // Facet seams — N-1 slanted lines per tier.
  const facetSeams: UnrolledLamp['facetSeams'] = [];
  let topY = PAD;
  for (let t = 0; t < tierWidths.length; t++) {
    const botY = topY + tierSlants[t];
    const topChord = tierWidths[t].top / N;
    const botChord = tierWidths[t].bot / N;
    const topLeft = cx - tierWidths[t].top / 2;
    const botLeft = cx - tierWidths[t].bot / 2;
    for (let i = 1; i < N; i++) {
      facetSeams.push({
        x1: topLeft + i * topChord,
        y1: topY,
        x2: botLeft + i * botChord,
        y2: botY,
      });
    }
    topY = botY;
  }

  // Tier seams — horizontal lines at internal tier boundaries (no edge seam at top/bottom).
  const tierSeams: UnrolledLamp['tierSeams'] = [];
  let cumY = PAD;
  for (let t = 0; t < tierWidths.length - 1; t++) {
    cumY += tierSlants[t];
    tierSeams.push({
      x1: cx - tierWidths[t].bot / 2,
      y1: cumY,
      x2: cx + tierWidths[t].bot / 2,
      y2: cumY,
    });
  }

  return { width, height, outline, facetSeams, tierSeams };
}
