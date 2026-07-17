export type ToolId = 'select' | 'pan' | 'crop' | 'measure' | 'box' | 'detect-all' | 'inspect' | 'polygon' | 'pen' | 'pencil';

import React, { type ReactNode } from 'react';
import { ToolTooltip } from './ToolTooltip';
import {
  IconSelect, IconHand, IconBox, IconWand, IconCrop, IconRuler, IconEye, IconPolygon,
} from './icons';

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
  sectionStart?: boolean;
  disabled?: boolean;
  loading?: boolean | number;
  tooltip?: ToolTooltipData;
}

interface ToolbarProps {
  tools: Tool[];
  activeTool: ToolId;
  onSelectTool: (id: ToolId) => void;
  children?: React.ReactNode;
}

export const SelectIcon = () => <IconSelect />;
export const HandIcon = () => <IconHand />;
export const CropIcon = () => <IconCrop />;
export const BoxIcon = () => <IconBox />;
export const MeasureIcon = () => <IconRuler />;
export const ViewIcon = () => <IconEye />;
export const DetectAllIcon = () => <IconWand />;

export const PenIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M10.5 2.5L3 10l-1.5 4.5L6 13l7.5-7.5-3-3z" />
    <path d="M8.5 4.5L11.5 7.5" />
    <circle cx="5" cy="11" r="0.75" fill="currentColor" />
    <line x1="3" y1="13" x2="5" y2="11" />
  </svg>
);

export const PolygonIcon = () => <IconPolygon />;

export const PencilIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 20h9" />
    <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
  </svg>
);

export function Toolbar({ tools, activeTool, onSelectTool, children }: ToolbarProps) {
  return (
    <div className="toolbar">
      {tools.map(tool => (
        <React.Fragment key={tool.id}>
          {tool.sectionStart && <div className="toolbar-divider" aria-hidden="true" />}
          <div className="tooltip-wrapper">
            <button
              className={`tool-btn ${activeTool === tool.id ? 'active' : ''}`}
              data-tool-id={tool.id}
              onClick={() => !tool.disabled && onSelectTool(tool.id)}
              disabled={tool.disabled && !tool.loading}
              style={tool.disabled && tool.loading ? { cursor: 'default' } : undefined}
            >
              <div style={{ position: 'relative', width: 18, height: 18, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <div style={{ opacity: tool.disabled && tool.loading ? 0.35 : 1, display: 'flex' }}>
                  {tool.icon}
                </div>
                {tool.loading !== undefined && tool.loading !== false && (
                  <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    {typeof tool.loading === 'number' ? (
                      <svg width="20" height="20" viewBox="0 0 16 16" style={{ transform: 'rotate(-90deg)' }}>
                        <circle cx="8" cy="8" r="7" stroke="rgba(192, 138, 31, 0.15)" strokeWidth="1.5" fill="none" />
                        <circle
                          cx="8" cy="8" r="7"
                          stroke="var(--amber)"
                          strokeWidth="1.5"
                          fill="none"
                          strokeDasharray={2 * Math.PI * 7}
                          strokeDashoffset={(2 * Math.PI * 7) - (tool.loading * 2 * Math.PI * 7)}
                          style={{ transition: 'stroke-dashoffset 0.1s linear' }}
                        />
                      </svg>
                    ) : (
                      <div className="spinner-tiny" style={{ width: 16, height: 16 }} />
                    )}
                  </div>
                )}
              </div>
              <span className="tool-label" style={{ opacity: tool.disabled && tool.loading ? 0.35 : 1 }}>
                {tool.label}
              </span>
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
        </React.Fragment>
      ))}
      {children}
    </div>
  );
}
