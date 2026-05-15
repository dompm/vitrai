export type ToolId = 'select' | 'pan' | 'crop' | 'measure' | 'box' | 'detect-all' | 'inspect';

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
