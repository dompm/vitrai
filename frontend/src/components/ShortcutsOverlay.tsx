import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { IconClose } from './icons';

interface Shortcut {
  keys: string[]; // e.g. ["⌘", "Z"] or ["V"]
  labelKey: string;
}

interface Group {
  titleKey: string;
  shortcuts: Shortcut[];
}

const isMac = typeof navigator !== 'undefined' && /Mac|iPod|iPhone|iPad/.test(navigator.platform);
const MOD = isMac ? '⌘' : 'Ctrl';

const GROUPS: Group[] = [
  {
    titleKey: 'shortcutsGroupTools',
    shortcuts: [
      { keys: ['V'], labelKey: 'shortcutSelect' },
      { keys: ['H'], labelKey: 'shortcutPan' },
      { keys: ['Space'], labelKey: 'shortcutPanHold' },
      { keys: ['B'], labelKey: 'shortcutCut' },
      { keys: ['C'], labelKey: 'shortcutCrop' },
      { keys: ['M'], labelKey: 'shortcutMeasure' },
      { keys: ['I'], labelKey: 'shortcutInspect' },
    ],
  },
  {
    titleKey: 'shortcutsGroupRefine',
    shortcuts: [
      { keys: ['A'], labelKey: 'shortcutAddRegion' },
      { keys: ['S'], labelKey: 'shortcutCutFrom' },
      { keys: ['Del'], labelKey: 'shortcutDelete' },
      { keys: ['Esc'], labelKey: 'shortcutDeselect' },
    ],
  },
  {
    titleKey: 'shortcutsGroupProject',
    shortcuts: [
      { keys: [MOD, 'Z'], labelKey: 'shortcutUndo' },
      { keys: ['⇧', MOD, 'Z'], labelKey: 'shortcutRedo' },
      { keys: [MOD, 'Y'], labelKey: 'shortcutRedoAlt' },
      { keys: [MOD, '⏎'], labelKey: 'shortcutPrint' },
    ],
  },
  {
    titleKey: 'shortcutsGroupHelp',
    shortcuts: [
      { keys: ['?'], labelKey: 'shortcutShowShortcuts' },
    ],
  },
];

interface Props {
  open: boolean;
  onClose: () => void;
}

export function ShortcutsOverlay({ open, onClose }: Props) {
  const { t } = useTranslation();

  useEffect(() => {
    if (!open) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    }
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="shortcuts-backdrop"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={t('shortcutsTitle')}
    >
      <div
        className="shortcuts-card"
        onClick={e => e.stopPropagation()}
      >
        <div className="shortcuts-header">
          <h2>{t('shortcutsTitle')}</h2>
          <button className="shortcuts-close" onClick={onClose} aria-label={t('shortcutsClose')}>
            <IconClose size={16} />
            <span>Esc</span>
          </button>
        </div>
        <div className="shortcuts-grid">
          {GROUPS.map(group => (
            <div className="shortcuts-group" key={group.titleKey}>
              <div className="shortcuts-group-title">{t(group.titleKey)}</div>
              <ul>
                {group.shortcuts.map(s => (
                  <li key={s.labelKey}>
                    <span className="shortcuts-label">{t(s.labelKey)}</span>
                    <span className="shortcuts-keys">
                      {s.keys.map((k, i) => (
                        <kbd key={i}>{k}</kbd>
                      ))}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
