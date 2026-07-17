import { useEffect, useState, useMemo } from 'react';
import type { Scale } from '../types';

const COLOR_FAMILIES = [
  { id: 'All', label: 'All Colors', colorStyle: 'linear-gradient(135deg, #ff4500, #ffd700, #32cd32, #00bfff, #da70d6)' },
  { id: 'Red', label: 'Red', colorStyle: '#e63946' },
  { id: 'Orange', label: 'Orange', colorStyle: '#f4a261' },
  { id: 'Yellow', label: 'Yellow', colorStyle: '#e9c46a' },
  { id: 'Green', label: 'Green', colorStyle: '#2a9d8f' },
  { id: 'Blue', label: 'Blue', colorStyle: '#457b9d' },
  { id: 'Purple', label: 'Purple', colorStyle: '#8338ec' },
  { id: 'Pink', label: 'Pink', colorStyle: '#ff006e' },
  { id: 'Brown', label: 'Brown/Amber', colorStyle: '#a06a42' },
  { id: 'Monochrome', label: 'White/Black/Gray', colorStyle: 'linear-gradient(135deg, #ffffff, #888888, #111111)' },
  { id: 'Clear', label: 'Clear', colorStyle: 'rgba(255, 255, 255, 0.1)' },
  { id: 'Other', label: 'Multi/Other', colorStyle: 'linear-gradient(45deg, #f72585, #7209b7, #3f37c9, #4cc9f0)' }
];

interface SwatchItem {
  id: string;
  manufacturer: string;
  base_sku: string;
  name: string;
  category: string;
  local_image: string;
  // null = physical scale unknown (scale audit could not measure the pick; the
  // stamped value was a known-wrong full-sheet assumption). See needs_repick.
  real_world_width_in: number | null;
  real_world_height_in: number | null;
  original_width_px: number;
  original_height_px: number;
  color_family?: string;
  product_url?: string;
  front_lit?: boolean;
  lighting?: 'front-lit' | 'back-lit';
  needs_repick?: boolean;
}

// Fallback physical width when a swatch's real-world scale is unknown (null).
// Matches the Bullseye whole-sheet studio-sample long side used by the scale audit.
const UNKNOWN_SCALE_WIDTH_IN = 10;

interface Props {
  onPick: (url: string, label: string, scale: Scale) => void;
  onClose: () => void;
}

const STARTER_SKUS = [
  // 1. Red & Pinks
  'OF25072S',           // Oceanside Red Opal
  '000124-0030-F-1010', // Bullseye Red Opal
  '000301-0030-F-1010', // Bullseye Pink Opal
  
  // 2. Orange & Yellows
  '000125-0030-F-1010', // Bullseye Orange Opal
  'OF27072S',           // Oceanside Orange Opal
  'OF26072S',           // Oceanside Yellow Opal
  '000120-0030-F-1010', // Bullseye Canary Yellow Opal
  
  // 3. Greens & Forest Hues
  'OF22076S',           // Oceanside Dark Green Opal
  'OF22276S',           // Oceanside Emerald Green Opal
  '000141-0030-F-1010', // Bullseye Dark Forest Green Opal
  '000126-0030-F-1010', // Bullseye Spring Green Opal
  
  // 4. Blues & Aquas
  'OF23072S',           // Oceanside Medium Blue Opal
  '000114-0030-F-1010', // Bullseye Cobalt Blue Opal
  'OF23374S',           // Oceanside Turquoise Blue Opal
  
  // 5. Purples & Violets
  'OF24074S',           // Oceanside Lilac Opal
  '001234-0030-F-1010', // Bullseye Violet Striker Transparent
  'OF24072S',           // Oceanside Mauve Opal
  
  // 6. Clears & Neutrals (Monochrome)
  '001101-0030-F-1010', // Bullseye Clear Double-Rolled
  'OF200S',             // Oceanside Solid White Opal
  '000113-0030-F-1010', // Bullseye White Opal
  'OF1009S',            // Oceanside Solid Black Opal
  '000100-0030-F-1010'  // Bullseye Black Opal
];

const ITEMS_PER_PAGE = 40;

export function GlassLibraryDialog({ onPick, onClose }: Props) {
  const [library, setLibrary] = useState<SwatchItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [search, setSearch] = useState('');
  const [mfgFilter, setMfgFilter] = useState('All');
  const [catFilter, setCatFilter] = useState('All');
  const [colorFilter, setColorFilter] = useState('All');
  const [sortBy, setSortBy] = useState<'common' | 'sku' | 'name'>('common');
  const [visibleCount, setVisibleCount] = useState(ITEMS_PER_PAGE);

  // Fetch the registry database
  useEffect(() => {
    fetch('/assets/glass_swatch_registry.json')
      .then(res => {
        if (!res.ok) throw new Error('Failed to load swatch library JSON');
        return res.json();
      })
      .then((data: SwatchItem[]) => {
        const cdnUrl = (import.meta.env.VITE_SWATCH_CDN_URL || '').replace(/\/$/, '');
        const processed = cdnUrl
          ? data.map(item => {
              const imgPath = item.local_image.startsWith('/') ? item.local_image : `/${item.local_image}`;
              return {
                ...item,
                local_image: `${cdnUrl}${imgPath}`
              };
            })
          : data;
        setLibrary(processed);
        setLoading(false);
      })
      .catch(err => {
        // Registry JSON absent or unparsable (e.g. a clean checkout before the
        // swatch data has been fetched) -- show a clear setup message instead of
        // a silent, forever-empty library.
        console.error(err);
        setLoadError(true);
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

  // Extract all unique manufacturers and categories for filter pills
  const manufacturers = useMemo(() => {
    const set = new Set(library.map(item => item.manufacturer));
    return ['All', ...Array.from(set).sort()];
  }, [library]);

  const categories = useMemo(() => {
    const set = new Set(library.map(item => item.category));
    return ['All', ...Array.from(set).sort()];
  }, [library]);

  // Filter and Search items
  const filteredItems = useMemo(() => {
    let result = library;

    // Search filter
    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter(
        item =>
          item.name.toLowerCase().includes(q) ||
          item.base_sku.toLowerCase().includes(q) ||
          item.manufacturer.toLowerCase().includes(q)
      );
    }

    // Manufacturer filter
    if (mfgFilter !== 'All') {
      result = result.filter(item => item.manufacturer === mfgFilter);
    }

    // Category filter
    if (catFilter !== 'All') {
      result = result.filter(item => item.category === catFilter);
    }

    // Color filter
    if (colorFilter !== 'All') {
      result = result.filter(item => item.color_family === colorFilter);
    }

    return result;
  }, [library, search, mfgFilter, catFilter, colorFilter]);

  // Sort items
  const sortedItems = useMemo(() => {
    let result = [...filteredItems];
    
    if (sortBy === 'sku') {
      result.sort((a, b) => a.base_sku.localeCompare(b.base_sku));
    } else if (sortBy === 'name') {
      result.sort((a, b) => a.name.localeCompare(b.name));
    } else if (sortBy === 'common') {
      const getCommonScore = (item: SwatchItem) => {
        // Pinned Curated Starter Swatches
        const idx = STARTER_SKUS.indexOf(item.base_sku);
        if (idx !== -1) {
          return 10000 - idx;
        }

        const name = item.name.toLowerCase();
        let score = 0;
        
        // Check if the glass has multiple colors or is a blend/streaky combo
        const isMultiColor = name.includes('and') || name.includes('&') || name.includes('/') || name.includes(',') || name.includes('mix') || name.includes('blend') || name.includes('streaky') || name.includes('wispy') || name.includes('mottle') || name.includes('variegated') || name.includes('spirit');
        
        // Core baseline colors
        const coreColors = ['white', 'black', 'clear', 'red', 'blue', 'green', 'yellow', 'orange', 'amber', 'pink', 'cobalt blue', 'turquoise'];
        for (const color of coreColors) {
          if (name === color || name === `${color} opal` || name === `${color} cathedral` || name === `solid ${color} opal`) {
            score += 100;
          }
        }
        
        if (name.includes('white') || name.includes('black') || name.includes('clear')) score += 30;
        if (name.includes('red') || name.includes('blue') || name.includes('green') || name.includes('yellow') || name.includes('orange') || name.includes('amber')) score += 20;
        if (name.includes('solid')) score += 15;
        if (name.includes('opal') && !name.includes('opal-art') && !name.includes('fusers reserve')) score += 10;
        
        // Promote clean single colors, penalize complex mixtures
        if (isMultiColor) {
          score -= 40;
        } else {
          score += 15;
        }
        
        if (name.includes('stipple') || name.includes('ripple') || name.includes('granite') || name.includes('mottle') || name.includes('streaky') || name.includes('mix') || name.includes('blend')) {
          score -= 30;
        }
        if (name.includes('fusers reserve') || name.includes('opal-art') || name.includes('baroque') || name.includes('artique')) {
          score -= 30;
        }
        
        return score;
      };
      
      result.sort((a, b) => {
        const scoreA = getCommonScore(a);
        const scoreB = getCommonScore(b);
        if (scoreA !== scoreB) {
          return scoreB - scoreA;
        }
        return a.base_sku.localeCompare(b.base_sku);
      });
    }
    
    return result;
  }, [filteredItems, sortBy]);

  // Reset page size when filter changes
  useEffect(() => {
    setVisibleCount(ITEMS_PER_PAGE);
  }, [search, mfgFilter, catFilter, sortBy, colorFilter]);

  const paginatedItems = useMemo(() => {
    return sortedItems.slice(0, visibleCount);
  }, [sortedItems, visibleCount]);

  const handleSelect = (item: SwatchItem) => {
    const widthPx = item.original_width_px || 800;
    const heightPx = item.original_height_px || 800;
    
    // Calibrated Scale configuration. real_world_width_in is null when the scale
    // audit could not trust the pick's footprint; fall back to a sane default so
    // placement never divides by null.
    const widthIn = item.real_world_width_in || UNKNOWN_SCALE_WIDTH_IN;
    const scale: Scale = {
      pxPerUnit: widthPx / widthIn,
      unit: 'in',
      line: { x1: 0, y1: heightPx / 2, x2: widthPx, y2: heightPx / 2 },
    };

    const label = `[${item.manufacturer}] ${item.base_sku} ${item.name}`;
    onPick(item.local_image, label, scale);
    onClose();
  };

  return (
    <div className="glass-library-backdrop" onClick={onClose}>
      <div className="glass-library-dialog" onClick={e => e.stopPropagation()}>
        <div className="glass-library-header">
          <h2>Stained Glass Swatch Library</h2>
          <button className="glass-library-close-btn" onClick={onClose} aria-label="Close">
            &times;
          </button>
        </div>

        {/* Search & Quick Filters */}
        <div className="glass-library-controls">
          <div className="glass-library-search-row" style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
            <div className="glass-library-search-wrapper" style={{ flex: 1 }}>
              <input
                type="text"
                placeholder="Search glass name, SKU, or manufacturer..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="glass-library-search"
                autoFocus
              />
              {search && (
                <button className="glass-library-search-clear" onClick={() => setSearch('')}>
                  &times;
                </button>
              )}
            </div>
            
            <div className="glass-library-sort-wrapper" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span className="glass-library-filter-label" style={{ width: 'auto', marginBottom: 0 }}>Sort:</span>
              <select
                value={sortBy}
                onChange={e => setSortBy(e.target.value as any)}
                className="glass-library-sort-select"
                style={{
                  padding: '10px 14px',
                  border: '1px solid var(--hairline-2)',
                  borderRadius: '8px',
                  background: 'rgba(255, 255, 255, 0.05)',
                  color: 'var(--text-bright)',
                  fontSize: '13px',
                  fontFamily: 'inherit',
                  outline: 'none',
                  cursor: 'pointer'
                }}
              >
                <option value="common">Common Colors</option>
                <option value="sku">SKU (A-Z)</option>
                <option value="name">Name (A-Z)</option>
              </select>
            </div>
          </div>

          {/* Color Filter Pills */}
          <div className="glass-library-filters-section">
            <span className="glass-library-filter-label">Color:</span>
            <div className="glass-library-filter-pills">
              {COLOR_FAMILIES.map(col => (
                <button
                  key={col.id}
                  className={`glass-library-pill ${colorFilter === col.id ? 'active' : ''}`}
                  onClick={() => setColorFilter(col.id)}
                  style={{ display: 'inline-flex', alignItems: 'center' }}
                >
                  <span
                    style={{
                      display: 'inline-block',
                      width: '10px',
                      height: '10px',
                      borderRadius: '50%',
                      marginRight: '6px',
                      background: col.colorStyle,
                      border: col.id === 'Clear' ? '1px dashed rgba(255, 255, 255, 0.6)' : '1px solid rgba(255, 255, 255, 0.25)',
                      flexShrink: 0
                    }}
                  />
                  {col.label}
                </button>
              ))}
            </div>
          </div>

          {/* Manufacturer Filter Pills */}
          <div className="glass-library-filters-section">
            <span className="glass-library-filter-label">Brand:</span>
            <div className="glass-library-filter-pills">
              {manufacturers.map(mfg => (
                <button
                  key={mfg}
                  className={`glass-library-pill ${mfgFilter === mfg ? 'active' : ''}`}
                  onClick={() => setMfgFilter(mfg)}
                >
                  {mfg}
                </button>
              ))}
            </div>
          </div>

          {/* Category Filter Pills */}
          <div className="glass-library-filters-section">
            <span className="glass-library-filter-label">Type:</span>
            <div className="glass-library-filter-pills">
              {categories.map(cat => (
                <button
                  key={cat}
                  className={`glass-library-pill ${catFilter === cat ? 'active' : ''}`}
                  onClick={() => setCatFilter(cat)}
                >
                  {cat}
                </button>
              ))}
            </div>
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
          ) : loadError || library.length === 0 ? (
            <div className="glass-library-empty">
              <p>Glass library data not present.</p>
              <p className="glass-library-empty-hint">
                Run <code>python3 scripts/build_swatch_library.py</code> from the repo root to fetch
                the swatch registry and catalog images (see the Glass swatch library section in the README).
              </p>
            </div>
          ) : paginatedItems.length === 0 ? (
            <div className="glass-library-empty">
              <p>No glass swatches match your criteria.</p>
            </div>
          ) : (
            <>
              <div className="glass-library-grid">
                {paginatedItems.map(item => (
                  <div
                    key={item.id}
                    className="glass-library-card"
                    onClick={() => handleSelect(item)}
                  >
                    <div className="glass-library-card-thumb-wrapper">
                      <img
                        src={item.local_image}
                        alt={item.name}
                        loading="lazy"
                        className="glass-library-card-thumb"
                        onError={e => {
                          // Catalog images are untracked local data -- on a clean
                          // checkout they 404. Show a hint instead of a broken image.
                          const wrapper = e.currentTarget.closest('.glass-library-card-thumb-wrapper');
                          if (wrapper && !wrapper.querySelector('.glass-library-thumb-missing')) {
                            e.currentTarget.style.display = 'none';
                            const note = document.createElement('div');
                            note.className = 'glass-library-thumb-missing';
                            note.textContent = 'Image not fetched — run scripts/build_swatch_library.py';
                            wrapper.prepend(note);
                          }
                        }}
                      />
                      <span className={`glass-library-badge badge-${item.manufacturer.toLowerCase()}`}>
                        {item.manufacturer}
                      </span>
                      {(item.lighting === 'front-lit' || item.front_lit) && (
                        <span className="glass-library-front-lit-badge" title="Front-lit surface photo. May not match transmissive backlight color.">
                          ⚠️ Front-Lit
                        </span>
                      )}
                    </div>
                    <div className="glass-library-card-details">
                      <div className="glass-library-card-sku">
                        <span>{item.base_sku}</span>
                        {item.product_url && (
                          <a
                            href={item.product_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="glass-library-product-link"
                            onClick={(e) => e.stopPropagation()}
                            title={item.manufacturer === 'Bullseye' ? 'View on Bullseye Glass (Manufacturer)' : 'View on Stained Glass Express (Source Catalog)'}
                          >
                            🔗
                          </a>
                        )}
                      </div>
                      <div className="glass-library-card-name" title={item.name}>
                        {item.name}
                      </div>
                      <div className="glass-library-card-footer">
                        <span className="glass-library-card-cat">{item.category}</span>
                        <span className="glass-library-card-scale">
                          {item.real_world_width_in
                            ? `${item.real_world_width_in}"×${item.real_world_height_in}"`
                            : 'scale TBD'}
                        </span>
                      </div>
                    </div>
                  </div>
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
