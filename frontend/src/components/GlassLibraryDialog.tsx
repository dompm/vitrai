import { useEffect, useState, useMemo } from 'react';
import type { Scale } from '../types';

const COLOR_FAMILIES = [
  { id: 'All', label: 'All Colors', emoji: '🌈' },
  { id: 'Red', label: 'Red', emoji: '🔴' },
  { id: 'Orange', label: 'Orange', emoji: 'orange' },
  { id: 'Yellow', label: 'Yellow', emoji: '🟡' },
  { id: 'Green', label: 'Green', emoji: '🟢' },
  { id: 'Blue', label: 'Blue', emoji: '🔵' },
  { id: 'Purple', label: 'Purple', emoji: '🟣' },
  { id: 'Pink', label: 'Pink', emoji: '💗' },
  { id: 'Brown', label: 'Brown/Amber', emoji: '🟤' },
  { id: 'Monochrome', label: 'White/Black/Gray', emoji: '⚪' },
  { id: 'Clear', label: 'Clear', emoji: '🌐' }
];

const getColorFamily = (name: string, sku: string): string => {
  const n = name.toLowerCase();
  const s = sku.toUpperCase();
  
  if (n.includes('clear') || n.includes('crystal') || n.includes('ice') || s.includes('ICE') || s.startsWith('W800') || s.startsWith('Y800') || s.startsWith('OF100ICE')) {
    return 'Clear';
  }
  if (n.includes('white') || n.includes('black') || n.includes('gray') || n.includes('grey') || n.includes('charcoal') || n.includes('pearl') || n.includes('silver') || n.includes('opal white')) {
    return 'Monochrome';
  }
  if (n.includes('red') || n.includes('cherry') || n.includes('ruby') || n.includes('daredevil') || n.includes('grenadine') || n.includes('crimson')) {
    return 'Red';
  }
  if (n.includes('orange') || n.includes('tangerine') || n.includes('persimmon') || n.includes('coral') || n.includes('peach')) {
    return 'Orange';
  }
  if (n.includes('yellow') || n.includes('canary') || n.includes('lemon') || n.includes('marigold')) {
    return 'Yellow';
  }
  if (n.includes('green') || n.includes('lime') || n.includes('moss') || n.includes('sage') || n.includes('emerald') || n.includes('caribbean') || n.includes('aventurine green') || n.includes('pine')) {
    return 'Green';
  }
  if (n.includes('blue') || n.includes('cobalt') || n.includes('sky') || n.includes('turquoise') || n.includes('indigo') || n.includes('teal') || n.includes('ocean') || n.includes('caribbean blue') || n.includes('aqua')) {
    return 'Blue';
  }
  if (n.includes('purple') || n.includes('violet') || n.includes('plum') || n.includes('heather') || n.includes('amethyst') || n.includes('grape') || n.includes('lavender') || n.includes('lilac') || n.includes('eggplant')) {
    return 'Purple';
  }
  if (n.includes('pink') || n.includes('rose') || n.includes('fuchsia') || n.includes('cranberry') || n.includes('gold pink') || n.includes('magenta')) {
    return 'Pink';
  }
  if (n.includes('brown') || n.includes('amber') || n.includes('bronze') || n.includes('chestnut') || n.includes('chocolate') || n.includes('wood') || n.includes('gold') || n.includes('cognac') || n.includes('caramel') || n.includes('tan') || n.includes('honey')) {
    return 'Brown';
  }
  
  return 'All';
};

interface SwatchItem {
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
}

interface Props {
  onPick: (url: string, label: string, scale: Scale) => void;
  onClose: () => void;
}

const ITEMS_PER_PAGE = 40;

export function GlassLibraryDialog({ onPick, onClose }: Props) {
  const [library, setLibrary] = useState<SwatchItem[]>([]);
  const [loading, setLoading] = useState(true);
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
      .then(data => {
        setLibrary(data);
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
      result = result.filter(item => getColorFamily(item.name, item.base_sku) === colorFilter);
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
        const name = item.name.toLowerCase();
        let score = 0;
        
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
        
        if (name.includes('stipple') || name.includes('ripple') || name.includes('granite') || name.includes('mottle') || name.includes('streaky') || name.includes('mix') || name.includes('blend')) {
          score -= 40;
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
    
    // Calibrated Scale configuration
    const scale: Scale = {
      pxPerUnit: widthPx / item.real_world_width_in,
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
                >
                  <span style={{ marginRight: '4px' }}>{col.emoji}</span>
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
                      />
                      <span className={`glass-library-badge badge-${item.manufacturer.toLowerCase()}`}>
                        {item.manufacturer}
                      </span>
                    </div>
                    <div className="glass-library-card-details">
                      <div className="glass-library-card-sku">{item.base_sku}</div>
                      <div className="glass-library-card-name" title={item.name}>
                        {item.name}
                      </div>
                      <div className="glass-library-card-footer">
                        <span className="glass-library-card-cat">{item.category}</span>
                        <span className="glass-library-card-scale">
                          {item.real_world_width_in}"&times;{item.real_world_height_in}"
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
      </div>
    </div>
  );
}
