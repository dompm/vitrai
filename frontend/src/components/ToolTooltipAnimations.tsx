import React from 'react';

/* ── Shared geometry ────────────────────────────────────────────────────── */

const FC  = { x: 110, y: 55 };   // flower center (220×110 viewport)
const FO  = 18;                    // petal offset from center
const FRX = 7;                     // petal semi-axis x
const FRY = 15;                    // petal semi-axis y
const FCR = 9;                     // center-circle radius
const ANGLES = [0, 60, 120, 180, 240, 300];

// Actual flower extents (used for crop target & measure line)
const CT = 22, CB = 88, CL = 81, CR = 139;

// Idle / selected palette
const IF  = 'rgba(59,130,246,0.12)';  // petal idle fill
const CF  = 'rgba(59,130,246,0.52)';  // center fill  (solid)
const IS  = '#818cf8';                 // idle stroke
const SS  = '#2563eb';                 // selected stroke

/* ── Tiny render helpers ─────────────────────────────────────────────────── */

// One idle petal (no animation)
function Petal({ a }: { a: number }) {
  return (
    <ellipse
      cx={FC.x} cy={FC.y - FO} rx={FRX} ry={FRY}
      transform={`rotate(${a}, ${FC.x}, ${FC.y})`}
      fill={IF} stroke={IS} strokeWidth="1.5" strokeLinejoin="round"
    />
  );
}

// Center circle (solid appearance, no animation)
function Center({ fill = CF }: { fill?: string }) {
  return <circle cx={FC.x} cy={FC.y} r={FCR} fill={fill} stroke={IS} strokeWidth="1.5" />;
}

// Full idle flower (all 6 petals + solid center), no animations
function IdleFlower() {
  return (
    <>
      {ANGLES.map(a => <Petal key={a} a={a} />)}
      <Center />
    </>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   Select Animation — cursor clicks one petal; only that petal highlights
   ═══════════════════════════════════════════════════════════════════════════ */
export function SelectAnimation() {
  const dur = '4s';
  const KT = '0; 0.28; 0.36; 0.75; 0.88; 1';

  // Target: petal at 120° (bottom-right), center ≈ (126, 64)
  const tx = 122, ty = 60;

  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 110" overflow="hidden">
      <rect width="220" height="110" fill="#eff6ff" />

      {/* 5 idle petals (all except angle 120°) */}
      {[0, 60, 180, 240, 300].map(a => <Petal key={a} a={a} />)}

      {/* Animated petal at 120° — larger outline on cursor click */}
      <ellipse
        cx={FC.x} cy={FC.y - FO} rx={FRX} ry={FRY}
        transform="rotate(120, 110, 55)"
        fill={IF} stroke={IS} strokeWidth="1.5" strokeLinejoin="round"
      >
        <animate attributeName="stroke"
          values={`${IS};${IS};${SS};${SS};${IS};${IS}`}
          keyTimes={KT} dur={dur} repeatCount="indefinite" />
        <animate attributeName="stroke-width"
          values="1.5;1.5;5;5;1.5;1.5"
          keyTimes={KT} dur={dur} repeatCount="indefinite" />
      </ellipse>

      {/* Solid center — stays idle */}
      <Center />

      {/* Cursor: flies in, clicks petal, retreats — 7 keyTimes → 6 splines */}
      <g transform="translate(210,100)">
        <animateTransform
          attributeName="transform" type="translate"
          values={`210,100; ${tx},${ty}; ${tx},${ty}; ${tx-3},${ty-3}; ${tx-3},${ty-3}; 210,100; 210,100`}
          keyTimes="0; 0.20; 0.28; 0.30; 0.75; 0.90; 1"
          dur={dur} repeatCount="indefinite" calcMode="spline"
          keySplines="0.4,0,0.2,1; 0,0,1,1; 0.4,0,0.6,1; 0,0,1,1; 0.4,0,0.2,1; 0,0,1,1" />
        <g>
          <animate attributeName="opacity"
            values="0;0;1;1;1;1;0;0"
            keyTimes="0;0.05;0.12;0.28;0.30;0.75;0.90;1"
            dur={dur} repeatCount="indefinite" />
          <polygon points="0,0 0,14 3.5,10.5 6,16 8,15 5.5,9 10,9"
            fill="white" stroke="#1e293b" strokeWidth="0.8" strokeLinejoin="round" />
        </g>
      </g>
    </svg>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   Box Animation — box drawn around the top petal; only it is detected
   ═══════════════════════════════════════════════════════════════════════════ */
export function BoxAnimation() {
  const dur = '4.5s';

  // Top petal (0°): ellipse at (110,37), rx=7, ry=15 → extents x:103-117, y:22-52
  // Detection box with padding
  const bx = 98, by = 15, bw = 24, bh = 42;
  const perim = (bw + bh) * 2; // 132

  // 5 keyTimes → 4 splines for petal highlight
  const KT_P = '0; 0.42; 0.50; 0.80; 1';

  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 110" overflow="hidden">
      <rect width="220" height="110" fill="#eff6ff" />

      {/* 5 idle petals (all except top petal at 0°) */}
      {[60, 120, 180, 240, 300].map(a => <Petal key={a} a={a} />)}

      {/* Top petal (0°) — larger outline when box is drawn (SAM result) */}
      <ellipse
        cx={FC.x} cy={FC.y - FO} rx={FRX} ry={FRY}
        transform="rotate(0, 110, 55)"
        fill={IF} stroke={IS} strokeWidth="1.5" strokeLinejoin="round"
      >
        <animate attributeName="stroke"
          values={`${IS};${IS};${SS};${SS};${IS}`}
          keyTimes={KT_P} dur={dur} repeatCount="indefinite" />
        <animate attributeName="stroke-width"
          values="1.5;1.5;5;5;1.5"
          keyTimes={KT_P} dur={dur} repeatCount="indefinite" />
      </ellipse>

      {/* Center stays idle */}
      <Center />

      {/* Amber detection box — draws via stroke-dashoffset — 6 keyTimes → 5 splines */}
      <rect x={bx} y={by} width={bw} height={bh}
        fill="rgba(245,158,11,0.05)" stroke="#f59e0b" strokeWidth="1.6"
        strokeDasharray={`${perim}`} strokeLinecap="round">
        <animate attributeName="stroke-dashoffset"
          values={`${perim};${perim};0;0;${perim};${perim}`}
          keyTimes="0; 0.22; 0.44; 0.80; 0.92; 1"
          dur={dur} repeatCount="indefinite" calcMode="spline"
          keySplines="0,0,1,1; 0.4,0,0.2,1; 0,0,1,1; 0.4,0,0.2,1; 0,0,1,1" />
        <animate attributeName="opacity"
          values="0;0;1;1;0;0"
          keyTimes="0; 0.20; 0.24; 0.80; 0.92; 1"
          dur={dur} repeatCount="indefinite" />
      </rect>

      {/* Amber crosshair — sweeps top-left to bottom-right of box — 5 keyTimes → 4 splines */}
      <g transform={`translate(${bx},${by})`}>
        <animateTransform
          attributeName="transform" type="translate"
          values={`${bx},${by}; ${bx+bw},${by+bh}; ${bx+bw},${by+bh}; ${bx+bw},${by+bh}; ${bx+bw},${by+bh}`}
          keyTimes="0; 0.20; 0.44; 0.80; 1"
          dur={dur} repeatCount="indefinite" calcMode="spline"
          keySplines="0.4,0,0.2,1; 0,0,1,1; 0,0,1,1; 0,0,1,1" />
        <g>
          <animate attributeName="opacity"
            values="1;1;0;0;1" keyTimes="0;0.20;0.28;0.96;1"
            dur={dur} repeatCount="indefinite" />
          <line x1="-8" y1="0" x2="-3" y2="0" stroke="#f59e0b" strokeWidth="1.5" />
          <line x1="3"  y1="0" x2="8"  y2="0" stroke="#f59e0b" strokeWidth="1.5" />
          <line x1="0" y1="-8" x2="0" y2="-3" stroke="#f59e0b" strokeWidth="1.5" />
          <line x1="0"  y1="3" x2="0"  y2="8" stroke="#f59e0b" strokeWidth="1.5" />
          <circle cx="0" cy="0" r="2" fill="none" stroke="#f59e0b" strokeWidth="1.2" />
        </g>
      </g>
    </svg>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   Detect All — scan line sweeps, then all 7 pieces highlight at once
   ═══════════════════════════════════════════════════════════════════════════ */
export function DetectAllAnimation() {
  const dur = '4s';

  // All 7 pieces share the same highlight timing
  const KT = '0; 0.28; 0.35; 0.72; 0.85; 1';
  const strokeAnim = `${IS};${IS};${SS};${SS};${IS};${IS}`;
  const swAnim = '1.5;1.5;5;5;1.5;1.5';

  const AnimPetal = ({ a }: { a: number }) => (
    <ellipse
      cx={FC.x} cy={FC.y - FO} rx={FRX} ry={FRY}
      transform={`rotate(${a}, ${FC.x}, ${FC.y})`}
      fill={IF} stroke={IS} strokeWidth="1.5" strokeLinejoin="round"
    >
      <animate attributeName="stroke"  values={strokeAnim} keyTimes={KT} dur={dur} repeatCount="indefinite" />
      <animate attributeName="stroke-width" values={swAnim} keyTimes={KT} dur={dur} repeatCount="indefinite" />
    </ellipse>
  );

  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 110" overflow="hidden">
      <rect width="220" height="110" fill="#eff6ff" />

      {/* All 6 petals — animate together */}
      {ANGLES.map(a => <AnimPetal key={a} a={a} />)}

      {/* Center — same timing */}
      <circle cx={FC.x} cy={FC.y} r={FCR} fill={CF} stroke={IS} strokeWidth="1.5">
        <animate attributeName="stroke"  values={strokeAnim} keyTimes={KT} dur={dur} repeatCount="indefinite" />
        <animate attributeName="stroke-width" values={swAnim} keyTimes={KT} dur={dur} repeatCount="indefinite" />
      </circle>

      {/* Amber scan line sweeps CT→CB just before detection (opacity uses linear) */}
      <line x1="0" x2="220" stroke="#f59e0b" strokeWidth="1.5">
        <animate attributeName="y1"
          values={`${CT};${CT};${CB};${CB}`}
          keyTimes="0; 0.15; 0.30; 1"
          calcMode="spline" keySplines="0,0,1,1; 0.4,0,0.2,1; 0,0,1,1"
          dur={dur} repeatCount="indefinite" />
        <animate attributeName="y2"
          values={`${CT};${CT};${CB};${CB}`}
          keyTimes="0; 0.15; 0.30; 1"
          calcMode="spline" keySplines="0,0,1,1; 0.4,0,0.2,1; 0,0,1,1"
          dur={dur} repeatCount="indefinite" />
        <animate attributeName="opacity"
          values="0;0;0.65;0.65;0;0"
          keyTimes="0;0.12;0.15;0.30;0.36;1"
          dur={dur} repeatCount="indefinite" />
      </line>
    </svg>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   Crop Animation — four guide lines slide in one at a time: top, bottom,
   left, right — each followed by its gray overlay
   ═══════════════════════════════════════════════════════════════════════════ */
export function CropAnimation() {
  const dur = '4.5s';

  // Line settle times (slide-in phase is 0.14 each)
  //   top:    slides 0.12 → 0.26
  //   bottom: slides 0.26 → 0.40
  //   left:   slides 0.40 → 0.54
  //   right:  slides 0.54 → 0.68
  // Hold 0.68 → 0.82   |   fade 0.82 → 0.95

  // 4 keyTimes for position → 3 splines
  const posSpline = '0,0,1,1; 0.4,0,0.2,1; 0,0,1,1';
  const FADE_END = 0.95;

  type LineProps = {
    axis: 'x' | 'y';
    from: number;
    to: number;
    slideStart: number;
    slideEnd: number;
    fixed1?: number;
    fixed2?: number;
  };

  function GuideLine({ axis, from, to, slideStart, slideEnd, fixed1 = 0, fixed2 = 220 }: LineProps) {
    const posVals = `${from};${from};${to};${to}`;
    const posKT   = `0; ${slideStart}; ${slideEnd}; 1`;
    const opKT    = `0; ${slideStart - 0.02}; ${slideStart + 0.02}; ${0.82}; ${FADE_END}; 1`;

    if (axis === 'y') {
      return (
        <line x1={fixed1} x2={fixed2} stroke="#818cf8" strokeWidth="1.2">
          <animate attributeName="y1" values={posVals} keyTimes={posKT} calcMode="spline" keySplines={posSpline} dur={dur} repeatCount="indefinite" />
          <animate attributeName="y2" values={posVals} keyTimes={posKT} calcMode="spline" keySplines={posSpline} dur={dur} repeatCount="indefinite" />
          <animate attributeName="opacity" values={`0;0;1;1;0;0`} keyTimes={opKT} dur={dur} repeatCount="indefinite" />
        </line>
      );
    }
    return (
      <line y1={fixed1} y2={fixed2} stroke="#818cf8" strokeWidth="1.2">
        <animate attributeName="x1" values={posVals} keyTimes={posKT} calcMode="spline" keySplines={posSpline} dur={dur} repeatCount="indefinite" />
        <animate attributeName="x2" values={posVals} keyTimes={posKT} calcMode="spline" keySplines={posSpline} dur={dur} repeatCount="indefinite" />
        <animate attributeName="opacity" values={`0;0;1;1;0;0`} keyTimes={opKT} dur={dur} repeatCount="indefinite" />
      </line>
    );
  }

  // Gray overlay rects — 4 non-overlapping regions outside the crop zone
  type OverlayProps = { x: number; y: number; w: number; h: number; appearAt: number };
  function Overlay({ x, y, w, h, appearAt }: OverlayProps) {
    const oKT = `0; ${appearAt}; ${appearAt + 0.02}; ${0.82}; ${FADE_END}; 1`;
    return (
      <rect x={x} y={y} width={w} height={h} fill="rgba(148,163,184,0.50)">
        <animate attributeName="opacity" values="0;0;1;1;0;0" keyTimes={oKT} dur={dur} repeatCount="indefinite" />
      </rect>
    );
  }

  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 110" overflow="hidden">
      <rect width="220" height="110" fill="#f8f9fb" />

      {/* The image being cropped */}
      <IdleFlower />

      {/* Gray overlays — appear after their corresponding line settles */}
      <Overlay x={0}   y={0}  w={220}      h={CT}       appearAt={0.26} />
      <Overlay x={0}   y={CB} w={220}      h={110 - CB} appearAt={0.40} />
      <Overlay x={0}   y={CT} w={CL}       h={CB - CT}  appearAt={0.54} />
      <Overlay x={CR}  y={CT} w={220 - CR} h={CB - CT}  appearAt={0.68} />

      {/* Guide lines — one at a time */}
      <GuideLine axis="y" from={0}   to={CT} slideStart={0.12} slideEnd={0.26} />
      <GuideLine axis="y" from={110} to={CB} slideStart={0.26} slideEnd={0.40} />
      <GuideLine axis="x" from={0}   to={CL} slideStart={0.40} slideEnd={0.54} />
      <GuideLine axis="x" from={220} to={CR} slideStart={0.54} slideEnd={0.68} />
    </svg>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   Measure Animation — line spans full flower width at center height
   ═══════════════════════════════════════════════════════════════════════════ */
export function MeasureAnimation() {
  const dur = '3.5s';
  const x1 = CL, x2 = CR, lineY = FC.y;   // 81 → 139 at y=55
  const lineLen = x2 - x1;                  // 58

  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 110" overflow="hidden">
      <rect width="220" height="110" fill="#eff6ff" />

      <IdleFlower />

      {/* Measurement line — draws L→R via dashoffset — 5 keyTimes → 4 splines */}
      <line x1={x1} y1={lineY} x2={x2} y2={lineY}
        stroke="#f59e0b" strokeWidth="2" strokeLinecap="round"
        strokeDasharray={`${lineLen}`}>
        <animate attributeName="stroke-dashoffset"
          values={`${lineLen};${lineLen};0;0;${lineLen}`}
          keyTimes="0; 0.14; 0.38; 0.80; 0.96"
          dur={dur} repeatCount="indefinite" calcMode="spline"
          keySplines="0,0,1,1; 0.4,0,0.2,1; 0,0,1,1; 0.4,0,0.2,1" />
        <animate attributeName="opacity"
          values="0;0;1;1;0;0"
          keyTimes="0; 0.10; 0.16; 0.80; 0.96; 1"
          dur={dur} repeatCount="indefinite" />
      </line>

      {/* Left endpoint — springs in — 6 keyTimes → 5 splines */}
      <circle cx={x1} cy={lineY} r="4" fill="#f59e0b" stroke="#ffffff" strokeWidth="1.5">
        <animate attributeName="opacity" values="0;0;1;1;0;0"
          keyTimes="0; 0.06; 0.14; 0.80; 0.96; 1" dur={dur} repeatCount="indefinite" />
        <animate attributeName="r" values="0;0;5;4;4;0"
          keyTimes="0; 0.06; 0.12; 0.18; 0.80; 0.96" dur={dur} repeatCount="indefinite"
          calcMode="spline" keySplines="0,0,1,1; 0.4,0,0.2,1; 0.4,0,0.2,1; 0,0,1,1; 0,0,1,1" />
      </circle>

      {/* Right endpoint — springs in after line reaches it — 7 keyTimes → 6 splines */}
      <circle cx={x2} cy={lineY} r="4" fill="#f59e0b" stroke="#ffffff" strokeWidth="1.5">
        <animate attributeName="opacity" values="0;0;0;1;1;0;0"
          keyTimes="0; 0.06; 0.30; 0.42; 0.80; 0.96; 1" dur={dur} repeatCount="indefinite" />
        <animate attributeName="r" values="0;0;0;5;4;4;0"
          keyTimes="0; 0.06; 0.30; 0.38; 0.44; 0.80; 0.96" dur={dur} repeatCount="indefinite"
          calcMode="spline" keySplines="0,0,1,1; 0,0,1,1; 0.4,0,0.2,1; 0.4,0,0.2,1; 0,0,1,1; 0,0,1,1" />
      </circle>

      {/* Tick marks */}
      <line x1={x1} y1={lineY - 9} x2={x1} y2={lineY + 9}
        stroke="#f59e0b" strokeWidth="1.5" strokeLinecap="round">
        <animate attributeName="opacity" values="0;0;0;1;1;0;0"
          keyTimes="0; 0.10; 0.16; 0.24; 0.80; 0.96; 1" dur={dur} repeatCount="indefinite" />
      </line>
      <line x1={x2} y1={lineY - 9} x2={x2} y2={lineY + 9}
        stroke="#f59e0b" strokeWidth="1.5" strokeLinecap="round">
        <animate attributeName="opacity" values="0;0;0;0;1;1;0;0"
          keyTimes="0; 0.10; 0.16; 0.38; 0.46; 0.80; 0.96; 1" dur={dur} repeatCount="indefinite" />
      </line>

      {/* Label above the flower */}
      <rect x="87" y="5" width="46" height="16" rx="8" fill="white" stroke="#f59e0b" strokeWidth="1.2">
        <animate attributeName="opacity" values="0;0;0;1;1;0;0"
          keyTimes="0; 0.35; 0.44; 0.52; 0.80; 0.96; 1" dur={dur} repeatCount="indefinite" />
      </rect>
      <text x="110" y="16.5" textAnchor="middle" fill="#f59e0b"
        fontSize="9" fontFamily="monospace" fontWeight="600" letterSpacing="0.5">
        58 mm
        <animate attributeName="opacity" values="0;0;0;1;1;0;0"
          keyTimes="0; 0.35; 0.44; 0.52; 0.80; 0.96; 1" dur={dur} repeatCount="indefinite" />
      </text>

      {/* Connector: label → measurement line */}
      <line x1="110" y1="21" x2="110" y2={lineY} stroke="#f59e0b" strokeWidth="0.8" strokeDasharray="2 2">
        <animate attributeName="opacity" values="0;0;0;0.6;0.6;0;0"
          keyTimes="0; 0.35; 0.44; 0.52; 0.80; 0.96; 1" dur={dur} repeatCount="indefinite" />
      </line>
    </svg>
  );
}


/* ═══════════════════════════════════════════════════════════════════════════
   Inspect Animation — pieces fade out to reveal the pattern, then return
   ═══════════════════════════════════════════════════════════════════════════ */
export function InspectAnimation() {
  const dur = '3.5s';
  const KT = '0; 0.35; 0.45; 0.85; 0.95; 1';

  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 110" overflow="hidden">
      <rect width="220" height="110" fill="#eff6ff" />
      
      {/* Pattern Image (always visible) */}
      <IdleFlower />
      
      {/* Pieces layer - fades out and in */}
      <g>
        <animate attributeName="opacity"
          values="1;1;0;0;1;1"
          keyTimes={KT} dur={dur} repeatCount="indefinite" />
        
        {/* Slightly offset "glass" petals over the original ones */}
        {ANGLES.map(a => (
          <ellipse
            key={a}
            cx={FC.x} cy={FC.y - FO} rx={FRX} ry={FRY}
            transform={`rotate(${a}, ${FC.x}, ${FC.y})`}
            fill="rgba(59,130,246,0.3)" stroke="#1d4ed8" strokeWidth="1.8"
          />
        ))}
        <circle cx={FC.x} cy={FC.y} r={FCR} fill="rgba(59,130,246,0.5)" stroke="#1d4ed8" strokeWidth="1.8" />
      </g>
      
      {/* Eye icon overlay - flashes when active */}
      <g transform="translate(195, 12) scale(0.8)">
        <path d="M1 8s3-5.5 7-5.5 7 5.5 7 5.5-3 5.5-7 5.5-7-5.5-7-5.5z" fill="none" stroke="#1d4ed8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="8" cy="8" r="2.5" fill="#1d4ed8" />
        <animate attributeName="opacity"
          values="0.3;0.3;1;1;0.3;0.3"
          keyTimes={KT} dur={dur} repeatCount="indefinite" />
      </g>
    </svg>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   Pan Animation — Hand grabbing and dragging the canvas
   ═══════════════════════════════════════════════════════════════════════════ */
export function PanAnimation() {
  const dur = '3s';
  const KT = '0; 0.2; 0.5; 0.7; 1';
  
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 110" overflow="hidden">
      <rect width="220" height="110" fill="#eff6ff" />
      
      {/* Pattern Image that gets moved */}
      <g>
        <animateTransform
          attributeName="transform" type="translate"
          values="0,0; 0,0; -30,-10; -30,-10; 0,0"
          keyTimes={KT} dur={dur} repeatCount="indefinite" />
        <IdleFlower />
      </g>
      
      {/* Hand icon moving */}
      <g>
        <animateTransform
          attributeName="transform" type="translate"
          values="110,60; 110,60; 80,50; 80,50; 110,60"
          keyTimes={KT} dur={dur} repeatCount="indefinite" />
        
        {/* Open hand -> Closed hand -> Open hand */}
        <g stroke="#1e293b" strokeWidth="1.5" fill="white" strokeLinecap="round" strokeLinejoin="round">
          <path d="M8 6.5V1.5C8 1 7 1 7 1.5V6.5 M7 6V2.5C7 2 6 2 6 2.5V8.5 M6 7.5V3.5C6 3 5 3 5 3.5V10.5 M8 8V4.5C8 4 9 4 9 4.5V10 M9 10C10 10 11 9.5 11 8.5V5.5C11 5 10 5 10 5.5 M5 10.5C5 12 6 14 8 14C10 14 11 12 11 10 M3.5 11.5L5 10.5">
            <animate attributeName="d"
              values="M8 6.5V1.5C8 1 7 1 7 1.5V6.5 M7 6V2.5C7 2 6 2 6 2.5V8.5 M6 7.5V3.5C6 3 5 3 5 3.5V10.5 M8 8V4.5C8 4 9 4 9 4.5V10 M9 10C10 10 11 9.5 11 8.5V5.5C11 5 10 5 10 5.5 M5 10.5C5 12 6 14 8 14C10 14 11 12 11 10 M3.5 11.5L5 10.5;
                      M8 6.5V3C8 2.5 7 2.5 7 3V6.5 M7 6V4C7 3.5 6 3.5 6 4V8.5 M6 7.5V5C6 4.5 5 4.5 5 5V10.5 M8 8V6C8 5.5 9 5.5 9 6V10 M9 10C10 10 11 9.5 11 8.5V5.5C11 5 10 5 10 5.5 M5 10.5C5 12 6 14 8 14C10 14 11 12 11 10 M3.5 11.5L5 10.5;
                      M8 6.5V3C8 2.5 7 2.5 7 3V6.5 M7 6V4C7 3.5 6 3.5 6 4V8.5 M6 7.5V5C6 4.5 5 4.5 5 5V10.5 M8 8V6C8 5.5 9 5.5 9 6V10 M9 10C10 10 11 9.5 11 8.5V5.5C11 5 10 5 10 5.5 M5 10.5C5 12 6 14 8 14C10 14 11 12 11 10 M3.5 11.5L5 10.5;
                      M8 6.5V1.5C8 1 7 1 7 1.5V6.5 M7 6V2.5C7 2 6 2 6 2.5V8.5 M6 7.5V3.5C6 3 5 3 5 3.5V10.5 M8 8V4.5C8 4 9 4 9 4.5V10 M9 10C10 10 11 9.5 11 8.5V5.5C11 5 10 5 10 5.5 M5 10.5C5 12 6 14 8 14C10 14 11 12 11 10 M3.5 11.5L5 10.5;
                      M8 6.5V1.5C8 1 7 1 7 1.5V6.5 M7 6V2.5C7 2 6 2 6 2.5V8.5 M6 7.5V3.5C6 3 5 3 5 3.5V10.5 M8 8V4.5C8 4 9 4 9 4.5V10 M9 10C10 10 11 9.5 11 8.5V5.5C11 5 10 5 10 5.5 M5 10.5C5 12 6 14 8 14C10 14 11 12 11 10 M3.5 11.5L5 10.5"
              keyTimes={KT} dur={dur} repeatCount="indefinite" />
          </path>
        </g>
      </g>
    </svg>
  );
}
