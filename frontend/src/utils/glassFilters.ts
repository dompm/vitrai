// Update facets with scripts/classify_glass_filters.py; reviewed trade-name overrides
// keep reflections from being mistaken for additional material colors.
export interface GlassFacets {
  version: number;
  colors: string[];
  appearance: string;
  surface: string;
}
export interface FilterableGlass {
  manufacturer: string;
  name: string;
  base_sku: string;
  category: string;
  facets?: GlassFacets;
}
export interface GlassFilters {
  search: string;
  brand: string;
  color: string;
  appearance: string;
  surface: string;
}
export function matchesGlassFilters(item: FilterableGlass, filters: GlassFilters): boolean {
  const query = filters.search.trim().toLowerCase();
  return (!query || [item.name, item.base_sku, item.manufacturer, item.category].some(x => x.toLowerCase().includes(query))) &&
    (filters.brand === 'All' || item.manufacturer === filters.brand) &&
    (filters.color === 'All' || !!item.facets?.colors.includes(filters.color)) &&
    (filters.appearance === 'All' || item.facets?.appearance === filters.appearance) &&
    (filters.surface === 'All' || item.facets?.surface === filters.surface);
}
