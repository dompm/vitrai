import { useEffect, useState, useMemo } from 'react';
import type { Scale } from '../types';

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

    return result;
  }, [library, search, mfgFilter, catFilter]);

  // Reset page size when filter changes
  useEffect(() => {
    setVisibleCount(ITEMS_PER_PAGE);
  }, [search, mfgFilter, catFilter]);

  const paginatedItems = useMemo(() => {
    return filteredItems.slice(0, visibleCount);
  }, [filteredItems, visibleCount]);

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
          <div className="glass-library-search-wrapper">
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
