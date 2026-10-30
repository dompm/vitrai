import './GlassLibraryDialog.css';
import { useEffect, useState, useMemo } from 'react';
import type { Scale } from '../types';
import { recommendedGlass, type BrowseGlass } from '../utils/glassBrowse';

import { swatchAssetUrl } from '../utils/swatchAssets';
import { matchesGlassFilters, type GlassFacets } from '../utils/glassFilters';

const COLOR_FAMILIES = [
  { id: 'All', label: 'All Colors', colorStyle: 'linear-gradient(135deg, #ff4500, #ffd700, #32cd32, #00bfff, #da70d6)' },
  { id: 'Red', label: 'Red', colorStyle: '#e63946' },
  { id: 'Orange', label: 'Orange', colorStyle: '#f4a261' },
  { id: 'Yellow', label: 'Yellow', colorStyle: '#e9c46a' },
  { id: 'Green', label: 'Green', colorStyle: '#2a9d8f' },
  { id: 'Blue', label: 'Blue', colorStyle: '#457b9d' },
  { id: 'Purple', label: 'Purple', colorStyle: '#8338ec' },
  { id: 'Pink', label: 'Pink', colorStyle: '#ff006e' },
  { id: 'Amber', label: 'Amber', colorStyle: '#d49b32' },
  { id: 'Brown', label: 'Brown', colorStyle: '#805b3c' },
  { id: 'White', label: 'White', colorStyle: '#fff' },
  { id: 'Black', label: 'Black', colorStyle: '#222' },
  { id: 'Gray', label: 'Gray', colorStyle: '#999' },
  { id: 'Clear', label: 'Clear', colorStyle: 'transparent' }
];

interface SwatchItem extends BrowseGlass {
  id: string;
  manufacturer: string;
  base_sku: string;
  name: string;
  category: string;
  local_image: string;
  real_world_width_in: number;
  real_world_height_in: number;
  original_width_px: number;
  original_height_px: number;
  color_family?: string;
  product_url?: string;
  front_lit?: boolean;
  facets?: GlassFacets;
}

interface Props {
  onPick: (url: string, label: string, scale: Scale) => void;
  onClose: () => void;
}

const ITEMS_PER_PAGE = 40;
const APPEARANCES = [['single-color', 'Single color'], ['wispy-streaky', 'Wispy / streaky'], ['mottled', 'Mottled'], ['other-blends', 'Other blends']];
const SURFACES = [['smooth', 'Smooth'], ['lightly-textured', 'Lightly textured'], ['strongly-textured', 'Strongly textured']];

function formatDimension(value: number): string {
  return Number.isFinite(value) ? String(Math.round(value * 10) / 10) : "—";
}

export function GlassLibraryDialog({ onPick, onClose }: Props) {
  const [library, setLibrary] = useState<SwatchItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [mfgFilter, setMfgFilter] = useState('All');
  const [appearanceFilter, setAppearanceFilter] = useState('All');
  const [surfaceFilter, setSurfaceFilter] = useState('All');
  const [colorFilter, setColorFilter] = useState('All');
  const [sortBy, setSortBy] = useState<'recommended' | 'sku' | 'name'>('recommended');
  const [visibleCount, setVisibleCount] = useState(ITEMS_PER_PAGE);

  // Ship classification with the app; only image bytes come from the CDN.
  // Otherwise regenerating the committed catalog would still load stale CDN metadata.
  useEffect(() => {
    const cdnUrl = import.meta.env.VITE_SWATCH_CDN_URL || '';
    fetch(`${import.meta.env.BASE_URL}assets/glass_swatch_registry.json`)
      .then(res => {
        if (!res.ok) throw new Error('Failed to load swatch library JSON');
        return res.json();
      })
      .then((data: SwatchItem[]) => {
        const processed = cdnUrl
          ? data.map(item => {
              return {
                ...item,
                local_image: swatchAssetUrl(item.local_image, cdnUrl)
              };
            })
          : data;
        setLibrary(processed);
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        setLoading(false);
      });
  }, []);

  // Keyboard close handler
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [onClose]);

  // Extract all unique manufacturers and categories for filters
  const manufacturers = useMemo(() => {
    const set = new Set(library.map(item => item.manufacturer));
    return ['All', ...Array.from(set).sort()];
  }, [library]);

  const filteredItems = useMemo(() => library.filter(item => matchesGlassFilters(item, {
    search, brand: mfgFilter, color: colorFilter,
    appearance: appearanceFilter, surface: surfaceFilter,
  })), [library, search, mfgFilter, colorFilter, appearanceFilter, surfaceFilter]);

  // Sort items
  const sortedItems = useMemo(() => {
    let result = [...filteredItems];
    
    if (sortBy === 'sku') {
      result.sort((a, b) => a.base_sku.localeCompare(b.base_sku));
    } else if (sortBy === 'name') {
      result.sort((a, b) => a.name.localeCompare(b.name));
    } else {
      result = recommendedGlass(result);
    }

    return result;
  }, [filteredItems, sortBy]);

  // Reset page size when filter changes
  useEffect(() => {
    setVisibleCount(ITEMS_PER_PAGE);
  }, [search, mfgFilter, appearanceFilter, surfaceFilter, sortBy, colorFilter]);

  const paginatedItems = useMemo(() => {
    return sortedItems.slice(0, visibleCount);
  }, [sortedItems, visibleCount]);

  const handleSelect = (item: SwatchItem) => {
    const widthPx = item.original_width_px || 800;
    const heightPx = item.original_height_px || 800;
    
    // Calibrated Scale configuration
    const scale: Scale = {
      pxPerUnit: widthPx / item.real_world_width_in,
      unit: 'in',
      line: { x1: 0, y1: heightPx / 2, x2: widthPx, y2: heightPx / 2 },
    };

    const label = `[${item.manufacturer}] ${item.base_sku} ${item.name}`;
    // Saved/exported projects may be reopened on a different app origin.
    onPick(new URL(item.local_image, window.location.href).href, label, scale);
    onClose();
  };

  return (
    <div className="glass-library-backdrop" onClick={onClose}>
      <div className="glass-library-dialog" role="dialog" aria-modal="true" aria-labelledby="glass-library-title" onClick={e => e.stopPropagation()}>
        <div className="glass-library-header">
          <h2 id="glass-library-title">Stained Glass Swatch Library</h2>
          <button className="glass-library-close-btn" onClick={onClose} aria-label="Close">
            &times;
          </button>
        </div>

        <div className="glass-library-controls">
          <div className="glass-library-control-row">
            <label className="glass-library-search-wrapper">
              <span className="glass-library-control-label">Search</span>
              <input
                type="search"
                placeholder="Name, SKU, or brand"
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="glass-library-search"
                autoFocus
              />
            </label>
            <label className="glass-library-select-wrapper">
              <span className="glass-library-control-label">Brand</span>
              <select value={mfgFilter} onChange={e => setMfgFilter(e.target.value)}>
                {manufacturers.map(mfg => <option key={mfg} value={mfg}>{mfg === 'All' ? 'All brands' : mfg}</option>)}
              </select>
            </label>
            <label className="glass-library-select-wrapper">
              <span className="glass-library-control-label">Appearance</span>
              <select value={appearanceFilter} onChange={e => setAppearanceFilter(e.target.value)}>
                <option value="All">All appearances</option>
                {APPEARANCES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label className="glass-library-select-wrapper">
              <span className="glass-library-control-label">Surface</span>
              <select value={surfaceFilter} onChange={e => setSurfaceFilter(e.target.value)}>
                <option value="All">All surfaces</option>
                {SURFACES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label className="glass-library-select-wrapper">
              <span className="glass-library-control-label">Sort</span>
              <select value={sortBy} onChange={e => setSortBy(e.target.value as 'recommended' | 'sku' | 'name')}>
                <option value="recommended">Recommended</option>
                <option value="sku">SKU (A–Z)</option>
                <option value="name">Name (A–Z)</option>
              </select>
            </label>
          </div>
          <div className="glass-library-colors" role="group" aria-label="Filter by color">
            {COLOR_FAMILIES.map(col => (
              <button
                key={col.id}
                type="button"
                className={`glass-library-color ${colorFilter === col.id ? 'active' : ''}`}
                onClick={() => setColorFilter(col.id)}
                aria-pressed={colorFilter === col.id}
                title={col.label}
              >
                <span className="glass-library-color-dot" style={{ background: col.colorStyle }} aria-hidden="true" />
                <span>{col.label}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Results Counter */}
        <div className="glass-library-summary">
          Found {filteredItems.length} matching sheets
        </div>

        {/* Grid Display Area */}
        <div className="glass-library-body">
          {loading ? (
            <div className="glass-library-loader">
              <div className="spinner"></div>
              <p>Loading glass formulas...</p>
            </div>
          ) : paginatedItems.length === 0 ? (
            <div className="glass-library-empty">
              <p>No glass swatches match your criteria.</p>
            </div>
          ) : (
            <>
              <div className="glass-library-grid">
                {paginatedItems.map(item => (
                  <article key={item.id} className="glass-library-card">
                    <button
                      type="button"
                      className="glass-library-card-pick"
                      onClick={() => handleSelect(item)}
                      aria-label={`Use ${item.manufacturer} ${item.base_sku}: ${item.name}`}
                    >
                      <span className="glass-library-card-thumb-wrapper">
                        <img src={item.local_image} alt="" crossOrigin="anonymous" loading="lazy" className="glass-library-card-thumb" />
                      </span>
                      <span className="glass-library-card-details">
                        <span className="glass-library-card-identity">
                          <span>{item.manufacturer}</span>
                          <span className="glass-library-card-sku">{item.base_sku}</span>
                        </span>
                        <span className="glass-library-card-name" title={item.name}>{item.name}</span>
                        <span className="glass-library-card-footer">
                          <span className="glass-library-card-cat">{item.category}</span>
                          <span className="glass-library-card-scale" title="Approximate image coverage in inches">
                            ≈ {formatDimension(item.real_world_width_in)} × {formatDimension(item.real_world_height_in)} in
                          </span>
                        </span>
                      </span>
                    </button>
                    <div className="glass-library-card-links">
                      <a
                        href={`https://www.google.com/search?udm=28&q=${encodeURIComponent(`${item.manufacturer} ${item.base_sku} ${item.name} sheet glass`)}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        aria-label={`Find sellers for ${item.manufacturer} ${item.base_sku} on Google Shopping (opens new tab)`}
                      >Find sellers ↗</a>
                      {item.front_lit && <span className="glass-library-photo-note" title="Surface-lit photograph; appearance in transmitted light may differ.">Surface-lit photo</span>}
                    </div>
                  </article>
                ))}
              </div>

              {filteredItems.length > visibleCount && (
                <div className="glass-library-load-more">
                  <button
                    className="btn-primary"
                    onClick={() => setVisibleCount(prev => prev + ITEMS_PER_PAGE)}
                  >
                    Load More Swatches ({filteredItems.length - visibleCount} remaining)
                  </button>
                </div>
              )}
            </>
          )}
        </div>
        <div className="glass-library-footer" style={{
          padding: '16px 24px',
          borderTop: '1px solid var(--hairline-2)',
          textAlign: 'center',
          fontSize: '11px',
          color: 'var(--text-dim)',
          background: 'rgba(0, 0, 0, 0.1)'
        }}>
          Images &copy; by their respective manufacturers. Visit official catalogs:{' '}
          <a href="https://shop.bullseyeglass.com/" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent)', textDecoration: 'none' }}>Bullseye</a> •{' '}
          <a href="https://www.oceansideglass.com/" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent)', textDecoration: 'none' }}>Oceanside</a> •{' '}
          <a href="https://wissmachglass.com/" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent)', textDecoration: 'none' }}>Wissmach</a> •{' '}
          <a href="https://www.youghioghenyglass.com/" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent)', textDecoration: 'none' }}>Youghiogheny</a>
        </div>
      </div>
    </div>
  );
}
