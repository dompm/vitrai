export type ToolId = 'select' | 'pan' | 'crop' | 'measure' | 'box' | 'detect-all' | 'inspect' | 'pen' | 'pencil';

import React, { type ReactNode } from 'react';
import { ToolTooltip } from './ToolTooltip';
import {
  IconSelect, IconHand, IconBox, IconWand, IconCrop, IconRuler, IconEye,
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
        <div key={tool.id} className="tooltip-wrapper">
          <button
            className={`tool-btn ${activeTool === tool.id ? 'active' : ''}`}
            data-tool-id={tool.id}
            onClick={() => !tool.disabled && onSelectTool(tool.id)}
            disabled={tool.disabled}
            style={tool.loading ? { position: 'relative' } : undefined}
          >
            {tool.icon}
            <span className="tool-label">{tool.label}</span>
            {tool.loading && (
              <div style={{
                position: 'absolute', inset: 0, display: 'flex',
                alignItems: 'center', justifyContent: 'center',
                background: 'rgba(255, 254, 250, 0.7)', borderRadius: 'inherit',
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
