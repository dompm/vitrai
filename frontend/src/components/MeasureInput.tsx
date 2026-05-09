import { useState, useRef, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import type { ScaleUnit } from '../types';

function formatInitial(v: number): string {
  return parseFloat(v.toPrecision(4)).toString();
}

interface Props {
  screenX: number;
  screenY: number;
  pixelLength: number;
  initialValue?: number;
  initialUnit?: ScaleUnit;
  onConfirm: (realLength: number, unit: ScaleUnit) => void;
  onCancel: () => void;
  onDrag: (delta: { x: number; y: number }) => void;
}

export function MeasureInput({ screenX, screenY, pixelLength, initialValue, initialUnit, onConfirm, onCancel, onDrag }: Props) {
  const { t } = useTranslation();
  
  const units: { id: ScaleUnit; label: string }[] = [
    { id: 'mm', label: t('unit_mm') },
    { id: 'cm', label: t('unit_cm') },
    { id: 'in', label: t('unit_in') },
  ];

  const [value, setValue] = useState(() => initialValue != null ? formatInitial(initialValue) : '');
  const [unit, setUnit] = useState<ScaleUnit>(initialUnit ?? 'mm');
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => { inputRef.current?.select(); }, []);
  useEffect(() => () => clearTimeout(debounceRef.current), []);

  const tryConfirm = useCallback((v: string, u: ScaleUnit) => {
    const n = parseFloat(v);
    if (n > 0) onConfirm(n, u);
  }, [onConfirm]);

  function handleValueChange(e: React.ChangeEvent<HTMLInputElement>) {
    const v = e.target.value;
    setValue(v);
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => tryConfirm(v, unit), 300);
  }

  function handleUnitChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const u = e.target.value as ScaleUnit;
    setUnit(u);
    clearTimeout(debounceRef.current);
    tryConfirm(value, u); // unit change is a discrete action, no debounce needed
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Escape') onCancel();
  }

  return (
    <div
      style={{
        position: 'absolute',
        left: Math.round(screenX),
        top: Math.round(screenY) - 16,
        transform: 'translate(-50%, -100%)',
        zIndex: 20,
        pointerEvents: 'none',
      }}
    >
      <div style={{ pointerEvents: 'auto', background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: '4px 10px 8px 10px', boxShadow: '0 4px 16px rgba(0,0,0,0.14)', display: 'flex', flexDirection: 'column', gap: 6, minWidth: 160 }}>
        <div 
          onMouseDown={(e) => {
            let lastX = e.clientX;
            let lastY = e.clientY;
            const handleMouseMove = (em: MouseEvent) => {
              const dx = em.clientX - lastX;
              const dy = em.clientY - lastY;
              lastX = em.clientX;
              lastY = em.clientY;
              onDrag({ x: dx, y: dy });
            };
            const handleMouseUp = () => {
              document.removeEventListener('mousemove', handleMouseMove);
              document.removeEventListener('mouseup', handleMouseUp);
            };
            document.addEventListener('mousemove', handleMouseMove);
            document.addEventListener('mouseup', handleMouseUp);
          }}
          style={{ height: 6, width: '40%', background: '#e5e7eb', borderRadius: 3, margin: '4px auto 8px auto', cursor: 'grab' }} 
        />
        <span style={{ fontSize: 11, color: '#6b7280', fontWeight: 600, textAlign: 'center' }}>
          {Math.round(pixelLength)} px =
        </span>
      <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
        <input
          ref={inputRef}
          type="number"
          min="0.01"
          step="any"
          placeholder={t('lengthPlaceholder')}
          value={value}
          onChange={handleValueChange}
          onKeyDown={handleKeyDown}
          style={{
            flex: 1,
            padding: '3px 6px',
            border: '1px solid #d1d5db',
            borderRadius: 4,
            fontSize: 13,
            outline: 'none',
            minWidth: 0,
          }}
        />
        <select
          value={unit}
          onChange={handleUnitChange}
          style={{
            padding: '3px 4px',
            border: '1px solid #d1d5db',
            borderRadius: 4,
            fontSize: 13,
            background: '#fff',
            cursor: 'pointer',
          }}
        >
          {units.map(u => <option key={u.id} value={u.id}>{u.label}</option>)}
        </select>
      </div>
    </div>
  </div>
  );
}
