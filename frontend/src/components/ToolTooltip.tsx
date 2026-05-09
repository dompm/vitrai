import type { ReactNode } from 'react';

interface ToolTooltipProps {
  name: string;
  shortcut: string;
  description: string;
  animation: ReactNode;
}

export function ToolTooltip({ name, shortcut, description, animation }: ToolTooltipProps) {
  return (
    <div className="tool-tooltip-card">
      <div className="tool-tooltip-preview">{animation}</div>
      <div className="tool-tooltip-body">
        <div className="tool-tooltip-header">
          <span className="tool-tooltip-name">{name}</span>
          <kbd className="tool-tooltip-kbd">{shortcut}</kbd>
        </div>
        <p className="tool-tooltip-desc">{description}</p>
      </div>
    </div>
  );
}
