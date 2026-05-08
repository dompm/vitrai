import { useState, useRef, useEffect, useCallback } from 'react';
import type { ScaleUnit } from '../types';

const UNITS: { id: ScaleUnit; label: string }[] = [
  { id: 'mm', label: 'mm' },
  { id: 'cm', label: 'cm' },
  { id: 'in', label: 'in' },
];

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
}

export function MeasureInput({ screenX, screenY, pixelLength, initialValue, initialUnit, onConfirm, onCancel }: Props) {
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
        left: Math.round(screenX) + 14,
        top: Math.round(screenY) - 36,
        background: '#fff',
        border: '1px solid #e5e7eb',
        borderRadius: 8,
        padding: '8px 10px',
        boxShadow: '0 4px 16px rgba(0,0,0,0.14)',
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        zIndex: 20,
        minWidth: 160,
        pointerEvents: 'all',
      }}
    >
      <span style={{ fontSize: 11, color: '#6b7280', fontWeight: 600 }}>
        {Math.round(pixelLength)} px =
      </span>
      <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
        <input
          ref={inputRef}
          type="number"
          min="0.01"
          step="any"
          placeholder="length"
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
          {UNITS.map(u => <option key={u.id} value={u.id}>{u.label}</option>)}
        </select>
      </div>
    </div>
  );
}
