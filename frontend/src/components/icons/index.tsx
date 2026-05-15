import type { SVGProps } from 'react';

interface IconProps extends SVGProps<SVGSVGElement> {
  size?: number;
}

function Svg({ size = 18, children, strokeWidth = 1.5, ...rest }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...rest}
    >
      {children}
    </svg>
  );
}

export const IconSelect = (p: IconProps) => (
  <Svg {...p}>
    <path d="M5 3l10 7-4.2 1.5 2.5 4.7-1.7.9-2.5-4.7L5 15.5V3z" fill="currentColor" stroke="none" />
  </Svg>
);

export const IconHand = (p: IconProps) => (
  <Svg {...p}>
    <path d="M8 11V6.5a1.5 1.5 0 0 1 3 0V10" />
    <path d="M11 10V4a1.5 1.5 0 0 1 3 0v6" />
    <path d="M14 10V5.5a1.5 1.5 0 0 1 3 0V12" />
    <path d="M17 7.5a1.5 1.5 0 0 1 3 0V14a6 6 0 0 1-12 0v-2a1.5 1.5 0 0 1 3 0v1" />
  </Svg>
);

// Dashed rectangle + center dot — universal marquee/cut affordance
export const IconBox = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 4h3" /><path d="M10 4h4" /><path d="M17 4h3" />
    <path d="M4 20h3" /><path d="M10 20h4" /><path d="M17 20h3" />
    <path d="M4 7v3" /><path d="M4 14v3" />
    <path d="M20 7v3" /><path d="M20 14v3" />
    <circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none" />
  </Svg>
);

// Wand + a single sparkle — auto-detect
export const IconWand = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 20l11-11" />
    <path d="M14 8l3 3" />
    <path d="M18 4v3M16.5 5.5h3" />
  </Svg>
);

export const IconCrop = (p: IconProps) => (
  <Svg {...p} strokeWidth={1.8}>
    <path d="M6 2v14h14" />
    <path d="M2 6h14v14" />
  </Svg>
);

export const IconRuler = (p: IconProps) => (
  <Svg {...p}>
    <rect x="2" y="8" width="20" height="8" rx="1.2" />
    <path d="M6 8v3" /><path d="M10 8v4" /><path d="M14 8v3" /><path d="M18 8v4" />
  </Svg>
);

export const IconEye = (p: IconProps) => (
  <Svg {...p}>
    <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" />
    <circle cx="12" cy="12" r="3" />
  </Svg>
);

export const IconUndo = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 8v6h6" />
    <path d="M20 18a8 8 0 0 0-8-8 8 8 0 0 0-6 2.6L4 14" />
  </Svg>
);

export const IconRedo = (p: IconProps) => (
  <Svg {...p}>
    <path d="M20 8v6h-6" />
    <path d="M4 18a8 8 0 0 1 8-8 8 8 0 0 1 6 2.6l2 1.4" />
  </Svg>
);

export const IconUpload = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3 16v3a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-3" />
    <path d="M17 8l-5-5-5 5" />
    <path d="M12 3v13" />
  </Svg>
);

export const IconDownload = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3 16v3a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-3" />
    <path d="M7 11l5 5 5-5" />
    <path d="M12 16V3" />
  </Svg>
);

export const IconPrinter = (p: IconProps) => (
  <Svg {...p}>
    <path d="M6 9V3h12v6" />
    <rect x="3" y="9" width="18" height="9" rx="1.5" />
    <rect x="7" y="14" width="10" height="7" rx="0.8" />
  </Svg>
);

export const IconGlobe = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M3 12h18" />
    <path d="M12 3a13 13 0 0 1 0 18a13 13 0 0 1 0-18z" />
  </Svg>
);

export const IconClose = (p: IconProps) => (
  <Svg {...p}>
    <path d="M6 6l12 12" />
    <path d="M18 6L6 18" />
  </Svg>
);

export const IconPlus = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 5v14" />
    <path d="M5 12h14" />
  </Svg>
);

export const IconChevron = (p: IconProps) => (
  <Svg {...p}>
    <path d="M6 9l6 6 6-6" />
  </Svg>
);

export const IconCheck = (p: IconProps) => (
  <Svg {...p}>
    <path d="M5 12l5 5L20 7" />
  </Svg>
);

export const IconTrash = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 7h16" />
    <path d="M9 7V4h6v3" />
    <path d="M6 7l1 13a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-13" />
  </Svg>
);

export const IconSmooth = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3 18c4 0 4-12 8-12s4 12 8 12" />
  </Svg>
);

export const IconSpark = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 3v6M12 15v6M3 12h6M15 12h6" />
  </Svg>
);
