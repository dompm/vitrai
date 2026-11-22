import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { DEFAULT_GLASS_ASSETS, TUTORIAL_GLASS_ASSETS } from '../assets';
import { listAllSheetsAcrossProjects, type RecentSheet } from '../storage/opfs';
import type { Scale } from '../types';

interface AddSheetMenuProps {
  anchor: { left: number; top: number };
  currentProjectName: string;
  onPickUrl: (url: string, label: string, scale?: Scale | null) => void;
  onUpload: (file: File) => void;
  onClose: () => void;
  onOpenLibrary: () => void;
}

export function AddSheetMenu({
  anchor, currentProjectName, onPickUrl, onUpload, onClose, onOpenLibrary,
}: AddSheetMenuProps) {
  const { t } = useTranslation();
  const menuRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [recent, setRecent] = useState<RecentSheet[]>([]);
  const [pos, setPos] = useState({ left: anchor.left, top: anchor.top });

  useLayoutEffect(() => {
    const el = menuRef.current;
    if (!el) return;
    const clampToViewport = () => {
      const rect = el.getBoundingClientRect();
      const pad = 12;
      const maxLeft = Math.max(pad, window.innerWidth - rect.width - pad);
      const nextLeft = Math.min(Math.max(pad, anchor.left), maxLeft);
      const maxTop = Math.max(pad, window.innerHeight - rect.height - pad);
      const nextTop = Math.min(Math.max(pad, anchor.top), maxTop);
      setPos(prev =>
        prev.left === nextLeft && prev.top === nextTop ? prev : { left: nextLeft, top: nextTop },
      );
    };
    clampToViewport();
    const ro = new ResizeObserver(clampToViewport);
    ro.observe(el);
    window.addEventListener('resize', clampToViewport);
    return () => {
      ro.disconnect();
      window.removeEventListener('resize', clampToViewport);
    };
  }, [anchor.left, anchor.top, recent.length]);

  useEffect(() => {
    let cancelled = false;
    const defaultUrls = new Set<string>([
      ...DEFAULT_GLASS_ASSETS.map(g => g.url),
      ...TUTORIAL_GLASS_ASSETS.map(g => g.url),
    ]);
    listAllSheetsAcrossProjects(currentProjectName).then(r => {
      if (!cancelled) setRecent(r.filter(s => !defaultUrls.has(s.url)));
    });
    return () => { cancelled = true; };
  }, [currentProjectName]);

  useEffect(() => {
    function onDown(e: PointerEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) onClose();
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    document.addEventListener('pointerdown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('pointerdown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [onClose]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    onUpload(file);
    onClose();
  };

  return (
    <div
      ref={menuRef}
      className="add-sheet-menu"
      style={{ left: pos.left, top: pos.top }}
      onMouseDown={e => e.stopPropagation()}
    >
      <button className="add-sheet-menu-item" onClick={() => { onClose(); onOpenLibrary(); }}>
        <span className="add-sheet-menu-label">Browse Glass Library…</span>
      </button>
      <button
        className="add-sheet-menu-item add-sheet-menu-upload"
        onClick={() => fileInputRef.current?.click()}
      >
        <span className="add-sheet-menu-upload-icon" aria-hidden>+</span>
        <span className="add-sheet-menu-label">{t('addSheetUpload')}</span>
      </button>
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        style={{ display: 'none' }}
        onChange={handleFileChange}
      />

      {recent.length > 0 && (
        <>
          <div className="add-sheet-menu-divider" />
          <div className="add-sheet-menu-section">{t('addSheetRecent')}</div>
          {recent.map(s => (
            <button
              key={s.url}
              className="add-sheet-menu-item"
              onClick={() => { onPickUrl(s.url, s.label); onClose(); }}
              title={t('addSheetFromProject', { project: s.projectName })}
            >
              <img className="add-sheet-menu-thumb" crossOrigin="anonymous" src={s.url} alt="" />
              <span className="add-sheet-menu-label">{s.label}</span>
              {s.projectName !== 'default' && (
                <span className="add-sheet-menu-source">{s.projectName}</span>
              )}
            </button>
          ))}
        </>
      )}

      <div className="add-sheet-menu-divider" />
      <div className="add-sheet-menu-section">{t('addSheetDefaults')}</div>
      {DEFAULT_GLASS_ASSETS.map(g => (
        <button
          key={g.url}
          className="add-sheet-menu-item"
          onClick={() => { onPickUrl(g.url, g.label, g.scale); onClose(); }}
        >
          <img className="add-sheet-menu-thumb" src={g.url} alt="" />
          <span className="add-sheet-menu-label">{g.label}</span>
        </button>
      ))}
    </div>
  );
}
