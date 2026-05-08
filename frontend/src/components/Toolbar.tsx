export type ToolId = 'select' | 'crop' | 'measure' | 'box';

interface Tool {
  id: ToolId;
  label: string;
  icon: React.ReactNode;
  disabled?: boolean;
}

interface ToolbarProps {
  tools: Tool[];
  activeTool: ToolId;
  onSelectTool: (id: ToolId) => void;
}

import React from 'react';

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
    <rect x="2" y="2" width="12" height="12" rx="1" strokeDasharray="3 2.5" />
    <line x1="8" y1="5" x2="8" y2="11" />
    <line x1="5" y1="8" x2="11" y2="8" />
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

export function Toolbar({ tools, activeTool, onSelectTool }: ToolbarProps) {
  return (
    <div className="toolbar">
      {tools.map(tool => (
        <button
          key={tool.id}
          className={`tool-btn ${activeTool === tool.id ? 'active' : ''}`}
          onClick={() => !tool.disabled && onSelectTool(tool.id)}
          disabled={tool.disabled}
          title={tool.label}
        >
          {tool.icon}
        </button>
      ))}
    </div>
  );
}
