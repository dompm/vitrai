export type ToolId = 'select' | 'crop' | 'measure' | 'box' | 'detect-all';

import React, { type ReactNode } from 'react';
import { ToolTooltip } from './ToolTooltip';

interface ToolTooltipData {
  name: string;
  shortcut: string;
  description: string;
  animation: ReactNode;
}

interface Tool {
  id: ToolId;
  label: string;
  icon: React.ReactNode;
  disabled?: boolean;
  loading?: boolean;
  tooltip?: ToolTooltipData;
}

interface ToolbarProps {
  tools: Tool[];
  activeTool: ToolId;
  onSelectTool: (id: ToolId) => void;
  children?: React.ReactNode;
}

export const SelectIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
    <path d="M3 1.5l9.5 6-3.8 1.4 2.3 4.2-1.5.8-2.3-4.2L4 11.5V1.5z" />
  </svg>
);

export const CropIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
    <path d="M4 1v9h9" />
    <path d="M1 4h9v9" />
  </svg>
);

export const BoxIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M8 1.5L14.5 6L12.5 14H3.5L1.5 6Z" />
    <path d="M8 1.5V9M1.5 6L8 9L14.5 6M3.5 14L8 9L12.5 14" />
  </svg>
);

export const MeasureIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
    <rect x="1.5" y="5.5" width="13" height="5" rx="1" />
    <line x1="4.5" y1="5.5" x2="4.5" y2="7.5" />
    <line x1="7.5" y1="5.5" x2="7.5" y2="8" />
    <line x1="10.5" y1="5.5" x2="10.5" y2="7.5" />
  </svg>
);

export const MagicIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M11.5 1.5l3 3" />
    <path d="M13 1l1.5 1.5" />
    <path d="M1.5 14.5l8-8" />
    <path d="M12 4.5l-2.5 2.5" />
    <path d="M3 3l.5.5" />
    <path d="M5 2l.5.5" />
    <path d="M2 5l.5.5" />
  </svg>
);

// Wand (auto-detect) + mini pentagon (same shape as BoxIcon) = "detect all"
export const DetectAllIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    {/* Mini pentagon (BoxIcon shape), scaled to left half */}
    <path d="M5 1.5L9 4.5L7.5 9.5H2.5L1 4.5Z" />
    <path d="M5 1.5V6M1 4.5L5 6L9 4.5M2.5 9.5L5 6L7.5 9.5" />
    {/* Wand */}
    <line x1="11" y1="7" x2="15.5" y2="11.5" strokeWidth="1.8" />
    {/* Sparkle */}
    <line x1="11" y1="2.5" x2="11" y2="4" />
    <line x1="13" y1="3.2" x2="12.2" y2="4" />
    <line x1="9" y1="3.2" x2="9.8" y2="4" />
  </svg>
);

export function Toolbar({ tools, activeTool, onSelectTool, children }: ToolbarProps) {
  return (
    <div className="toolbar">
      {tools.map(tool => (
        <div key={tool.id} className="tooltip-wrapper">
          <button
            className={`tool-btn ${activeTool === tool.id ? 'active' : ''}`}
            onClick={() => !tool.disabled && onSelectTool(tool.id)}
            disabled={tool.disabled}
            style={tool.loading ? { position: 'relative' } : undefined}
          >
            {tool.icon}
            {tool.loading && (
              <div style={{
                position: 'absolute', inset: 0, display: 'flex',
                alignItems: 'center', justifyContent: 'center',
                background: 'rgba(255,255,255,0.5)', borderRadius: 'inherit',
              }}>
                <div className="spinner-tiny" />
              </div>
            )}
          </button>
          {tool.tooltip ? (
            <ToolTooltip
              name={tool.tooltip.name}
              shortcut={tool.tooltip.shortcut}
              description={tool.tooltip.description}
              animation={tool.tooltip.animation}
            />
          ) : (
            <span className="tooltip-tip">{tool.label}</span>
          )}
        </div>
      ))}
      {children}
    </div>
  );
}
