export type BrowseGroup = 'everyday' | 'character' | 'specialty';
export interface BrowseGlass {
  id: string;
  manufacturer: string;
  base_sku: string;
  name: string;
  color_family?: string;
  browse?: { version: number; group: BrowseGroup; style: string; color: string; family: string; reason: string };
}

const GROUPS = ['everyday', 'character', 'specialty', 'unclassified'];
// Repeated blend slots give ordinary multicolor sheets room alongside solid colors.
const PALETTE = ['Red', 'Other', 'Orange', 'Yellow', 'Other', 'Green', 'Blue', 'Other', 'Purple', 'Pink', 'Brown', 'Monochrome', 'Clear'];
const compare = (a: string, b: string) => a.localeCompare(b, 'en', { numeric: true });

/** Order the entire matching set: familiar materials first, then balanced palette rounds.
 * Family counts defer near-duplicate variants; style and brand counts spread the range.
 * Filters run before this function, so every filtered view gets the same treatment.
 * Unknown future entries remain available after explicitly classified materials.
 */
export function recommendedGlass<T extends BrowseGlass>(items: readonly T[]): T[] {
  const output: T[] = [];
  for (const group of GROUPS) {
    const remaining = items.filter(x => (x.browse?.group ?? 'unclassified') === group);
    const families = new Map<string, number>();
    const styles = new Map<string, number>();
    const brands = new Map<string, number>();
    const count = (map: Map<string, number>, key: string) => map.get(key) ?? 0;
    const colorOf = (x: T) => x.browse?.color ?? x.color_family ?? 'Unknown';
    const family = (x: T) => x.browse?.family ?? x.id;
    const style = (x: T) => x.browse?.style ?? 'unknown';
    const bump = (map: Map<string, number>, key: string) => map.set(key, count(map, key) + 1);
    while (remaining.length) {
      // Include any new color families without silently dropping future catalog records.
      const colors = [...PALETTE, ...[...new Set(remaining.map(colorOf))].filter(c => !PALETTE.includes(c)).sort(compare)];
      for (const color of colors) {
        const candidates = remaining.filter(x => colorOf(x) === color);
        candidates.sort((a, b) =>
          count(families, family(a)) - count(families, family(b)) ||
          count(styles, style(a)) - count(styles, style(b)) ||
          count(brands, a.manufacturer) - count(brands, b.manufacturer) ||
          // Prefer standard rolled thickness to thin variants within otherwise equal choices.
          Number(/thin.rolled/i.test(a.name)) - Number(/thin.rolled/i.test(b.name)) ||
          compare(a.base_sku, b.base_sku) || compare(a.id, b.id));
        const pick = candidates[0];
        if (!pick) continue;
        output.push(pick);
        remaining.splice(remaining.indexOf(pick), 1);
        bump(families, family(pick)); bump(styles, style(pick)); bump(brands, pick.manufacturer);
      }
    }
  }
  return output;
}
