
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
const IF  = 'rgba(142, 136, 122, 0.08)';  // brand sand/frosted fill (soft)
const CF  = 'rgba(142, 136, 122, 0.40)';  // brand sand/frosted center (semi-solid)
const IS  = '#23201a';                 // dark charcoal/solder line (matches --text-bright)
const SS  = '#c08a1f';                 // brand amber highlight (matches --amber)

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
      <rect width="220" height="110" fill="transparent" />

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

  // 5 keyTimes → 4 splines for petal highlight
  const KT_P = '0; 0.42; 0.50; 0.80; 1';

  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 110" overflow="hidden">
      <rect width="220" height="110" fill="transparent" />

      {/* 5 idle petals (all except top petal at 0°) */}
      {[60, 120, 180, 240, 300].map(a => <Petal key={a} a={a} />)}

      {/* Top petal (0°) — larger outline and rich fill when box is drawn (SAM result) */}
      <ellipse
        cx={FC.x} cy={FC.y - FO} rx={FRX} ry={FRY}
        transform="rotate(0, 110, 55)"
        fill={IF} stroke={IS} strokeWidth="1.5" strokeLinejoin="round"
      >
        <animate attributeName="fill"
          values={`${IF};${IF};rgba(142, 136, 122, 0.28);rgba(142, 136, 122, 0.28);${IF}`}
          keyTimes={KT_P} dur={dur} repeatCount="indefinite" />
        <animate attributeName="stroke"
          values={`${IS};${IS};${SS};${SS};${IS}`}
          keyTimes={KT_P} dur={dur} repeatCount="indefinite" />
        <animate attributeName="stroke-width"
          values="1.5;1.5;5;5;1.5"
          keyTimes={KT_P} dur={dur} repeatCount="indefinite" />
      </ellipse>

      {/* Center stays idle */}
      <Center />

      {/* Amber detection box — expands dynamically as the cursor drags */}
      <rect x={bx} y={by} fill="rgba(245,158,11,0.05)" stroke="#f59e0b" strokeWidth="1.6" strokeLinecap="round">
        <animate attributeName="width"
          values={`0; 0; ${bw}; ${bw}; 0; 0`}
          keyTimes="0; 0.12; 0.44; 0.80; 0.92; 1"
          dur={dur} repeatCount="indefinite" calcMode="spline"
          keySplines="0,0,1,1; 0.4,0,0.2,1; 0,0,1,1; 0.4,0,0.2,1; 0,0,1,1" />
        <animate attributeName="height"
          values={`0; 0; ${bh}; ${bh}; 0; 0`}
          keyTimes="0; 0.12; 0.44; 0.80; 0.92; 1"
          dur={dur} repeatCount="indefinite" calcMode="spline"
          keySplines="0,0,1,1; 0.4,0,0.2,1; 0,0,1,1; 0.4,0,0.2,1; 0,0,1,1" />
        <animate attributeName="opacity"
          values="0; 1; 1; 1; 0; 0"
          keyTimes="0; 0.12; 0.44; 0.80; 0.92; 1"
          dur={dur} repeatCount="indefinite" />
      </rect>

      {/* Amber crosshair — sweeps top-left to bottom-right of box */}
      <g>
        <animateTransform
          attributeName="transform" type="translate"
          values={`
            ${bx},${by};
            ${bx},${by};
            ${bx+bw},${by+bh};
            ${bx+bw},${by+bh};
            ${bx},${by};
            ${bx},${by}
          `}
          keyTimes="0; 0.12; 0.44; 0.80; 0.92; 1"
          dur={dur} repeatCount="indefinite" calcMode="spline"
          keySplines="0,0,1,1; 0.4,0,0.2,1; 0,0,1,1; 0.4,0,0.2,1; 0,0,1,1" />
        <g>
          <animate attributeName="opacity"
            values="0;0;1;1;0;0" keyTimes="0;0.10;0.12;0.80;0.92;1"
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
  const fillAnim = `${IF};${IF};rgba(142, 136, 122, 0.28);rgba(142, 136, 122, 0.28);${IF};${IF}`;
  const strokeAnim = `${IS};${IS};${SS};${SS};${IS};${IS}`;
  const swAnim = '1.5;1.5;5;5;1.5;1.5';

  const centerFillAnim = `${CF};${CF};rgba(142, 136, 122, 0.55);rgba(142, 136, 122, 0.55);${CF};${CF}`;

  const AnimPetal = ({ a }: { a: number }) => (
    <ellipse
      cx={FC.x} cy={FC.y - FO} rx={FRX} ry={FRY}
      transform={`rotate(${a}, ${FC.x}, ${FC.y})`}
      fill={IF} stroke={IS} strokeWidth="1.5" strokeLinejoin="round"
    >
      <animate attributeName="fill" values={fillAnim} keyTimes={KT} dur={dur} repeatCount="indefinite" />
      <animate attributeName="stroke"  values={strokeAnim} keyTimes={KT} dur={dur} repeatCount="indefinite" />
      <animate attributeName="stroke-width" values={swAnim} keyTimes={KT} dur={dur} repeatCount="indefinite" />
    </ellipse>
  );

  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 110" overflow="hidden">
      <rect width="220" height="110" fill="transparent" />

      {/* All 6 petals — animate together */}
      {ANGLES.map(a => <AnimPetal key={a} a={a} />)}

      {/* Center — same timing */}
      <circle cx={FC.x} cy={FC.y} r={FCR} fill={CF} stroke={IS} strokeWidth="1.5">
        <animate attributeName="fill" values={centerFillAnim} keyTimes={KT} dur={dur} repeatCount="indefinite" />
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
        <line x1={fixed1} x2={fixed2} stroke="#c08a1f" strokeWidth="1.2">
          <animate attributeName="y1" values={posVals} keyTimes={posKT} calcMode="spline" keySplines={posSpline} dur={dur} repeatCount="indefinite" />
          <animate attributeName="y2" values={posVals} keyTimes={posKT} calcMode="spline" keySplines={posSpline} dur={dur} repeatCount="indefinite" />
          <animate attributeName="opacity" values={`0;0;1;1;0;0`} keyTimes={opKT} dur={dur} repeatCount="indefinite" />
        </line>
      );
    }
    return (
      <line y1={fixed1} y2={fixed2} stroke="#c08a1f" strokeWidth="1.2">
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
      <rect x={x} y={y} width={w} height={h} fill="rgba(35, 32, 26, 0.42)">
        <animate attributeName="opacity" values="0;0;1;1;0;0" keyTimes={oKT} dur={dur} repeatCount="indefinite" />
      </rect>
    );
  }

  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 110" overflow="hidden">
      <rect width="220" height="110" fill="transparent" />

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
      <rect width="220" height="110" fill="transparent" />

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
      <rect width="220" height="110" fill="transparent" />
      
      {/* Raw colorful pattern image (source photo always visible underneath) */}
      <g opacity="0.6">
        {ANGLES.map(a => (
          <ellipse
            key={a}
            cx={FC.x} cy={FC.y - FO} rx={FRX} ry={FRY}
            transform={`rotate(${a}, ${FC.x}, ${FC.y})`}
            fill="rgba(142, 136, 122, 0.35)"
          />
        ))}
        <circle cx={FC.x} cy={FC.y} r={FCR} fill="rgba(192, 138, 31, 0.45)" />
      </g>
      
      {/* Digital vector trace lines - fades out to allow inspection of photo */}
      <g>
        <animate attributeName="opacity"
          values="1;1;0.05;0.05;1;1"
          keyTimes={KT} dur={dur} repeatCount="indefinite" />
        
        {/* Dark lead outlines of the traced pieces */}
        {ANGLES.map(a => (
          <ellipse
            key={a}
            cx={FC.x} cy={FC.y - FO} rx={FRX} ry={FRY}
            transform={`rotate(${a}, ${FC.x}, ${FC.y})`}
            fill="none" stroke="#1a1a1a" strokeWidth="1.6"
          />
        ))}
        <circle cx={FC.x} cy={FC.y} r={FCR} fill="none" stroke="#1a1a1a" strokeWidth="1.6" />
      </g>
      
      {/* Eye icon overlay - active when trace lines are hidden */}
      <g transform="translate(195, 12) scale(0.8)">
        <path d="M1 8s3-5.5 7-5.5 7 5.5 7 5.5-3 5.5-7 5.5-7-5.5-7-5.5z" fill="none" stroke="#c08a1f" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="8" cy="8" r="2.5" fill="#c08a1f" />
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
      <rect width="220" height="110" fill="transparent" />
      
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

export function PolygonAnimation() {
  const dur = '4s';
  const p1 = { x: 50, y: 75 };
  const p2 = { x: 110, y: 25 };
  const p3 = { x: 170, y: 75 };
  
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 110" overflow="hidden">
      <rect width="220" height="110" fill="transparent" />
      
      {/* Target shape boundary that highlights on completion */}
      <polygon points={`${p1.x},${p1.y} ${p2.x},${p2.y} ${p3.x},${p3.y}`} fill="rgba(192, 138, 31, 0.04)" stroke="#8a8270" strokeWidth="1.2" strokeDasharray="3 3" />
      
      {/* Growing polygon segments */}
      <polyline points="" fill="none" stroke="#c08a1f" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round">
        <animate attributeName="points"
          values={`
            ${p1.x},${p1.y};
            ${p1.x},${p1.y} ${p1.x},${p1.y};
            ${p1.x},${p1.y} ${p2.x},${p2.y};
            ${p1.x},${p1.y} ${p2.x},${p2.y} ${p2.x},${p2.y};
            ${p1.x},${p1.y} ${p2.x},${p2.y} ${p3.x},${p3.y};
            ${p1.x},${p1.y} ${p2.x},${p2.y} ${p3.x},${p3.y} ${p1.x},${p1.y};
            ${p1.x},${p1.y} ${p2.x},${p2.y} ${p3.x},${p3.y} ${p1.x},${p1.y}
          `}
          keyTimes="0; 0.15; 0.35; 0.50; 0.70; 0.85; 1"
          dur={dur} repeatCount="indefinite" />
      </polyline>
      
      {/* Vertex handles */}
      {/* Node 1 */}
      <circle cx={p1.x} cy={p1.y} r="3.5" fill="#f59e0b" stroke="#c08a1f" strokeWidth="1">
        <animate attributeName="opacity" values="0;1;1;1;1;1;1" keyTimes="0;0.10;0.35;0.50;0.70;0.85;1" dur={dur} repeatCount="indefinite" />
      </circle>
      
      {/* Node 2 */}
      <circle cx={p2.x} cy={p2.y} r="3" fill="#ffffff" stroke="#c08a1f" strokeWidth="1">
        <animate attributeName="opacity" values="0;0;0;1;1;1;1" keyTimes="0;0.10;0.30;0.45;0.70;0.85;1" dur={dur} repeatCount="indefinite" />
      </circle>
      
      {/* Node 3 */}
      <circle cx={p3.x} cy={p3.y} r="3" fill="#ffffff" stroke="#c08a1f" strokeWidth="1">
        <animate attributeName="opacity" values="0;0;0;0;0;1;1" keyTimes="0;0.10;0.30;0.45;0.65;0.80;1" dur={dur} repeatCount="indefinite" />
      </circle>

      {/* Finished shape highlight */}
      <polygon points={`${p1.x},${p1.y} ${p2.x},${p2.y} ${p3.x},${p3.y}`} fill="rgba(192, 138, 31, 0.14)" stroke="#c08a1f" strokeWidth="3" opacity="0">
        <animate attributeName="opacity" values="0;0;0;0;0;1;1" keyTimes="0;0.10;0.30;0.45;0.65;0.85;1" dur={dur} repeatCount="indefinite" />
      </polygon>
      
      {/* Pen Nib Cursor */}
      <g transform="translate(190, 80)">
        <animateTransform
          attributeName="transform" type="translate"
          values={`
            190,80;
            ${p1.x},${p1.y};
            ${p2.x},${p2.y};
            ${p3.x},${p3.y};
            ${p1.x},${p1.y};
            190,80;
            190,80
          `}
          keyTimes="0; 0.15; 0.45; 0.70; 0.85; 0.95; 1"
          dur={dur} repeatCount="indefinite" calcMode="spline"
          keySplines="
            0.4,0,0.2,1;
            0.4,0,0.2,1;
            0.4,0,0.2,1;
            0.4,0,0.2,1;
            0.4,0,0.2,1;
            0,0,1,1
          " />
        <path d="M0,0 C0.8,2.4 1.6,4 3.6,6 L4.8,4.8 C2.8,2.8 1.2,2 0,0" fill="#1e293b" stroke="#1e293b" strokeWidth="0.5" />
        <path d="M3.6,6 L8.8,11.2 L11.2,8.8 L6,3.6 Z" fill="white" stroke="#1e293b" strokeWidth="0.8" />
        <line x1="0" y1="0" x2="2.8" y2="2.8" stroke="#1e293b" strokeWidth="0.8" />
        <circle cx="2.8" cy="2.8" r="0.5" fill="#1e293b" />
      </g>
    </svg>
  );
}

export function PenAnimation() {
  const dur = '5s';
  const path = 'M 42,76 C 55,30 82,20 110,31 C 140,42 158,52 178,76 C 145,96 76,96 42,76 Z';

  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 110" overflow="hidden">
      <rect width="220" height="110" fill="transparent" />

      {/* The intended contour stays visible while the Pen constructs it. */}
      <path
        d={path}
        fill="rgba(192, 138, 31, 0.04)"
        stroke="#8a8270"
        strokeWidth="1.2"
        strokeDasharray="3 3"
      />

      {/* The first segment starts straight, then visibly bows while the user
          drags away from the top anchor to create direction handles. */}
      <path
        d="M 42,76 C 42,76 42,76 42,76"
        fill="none"
        stroke="#c08a1f"
        strokeWidth="2.2"
        strokeLinecap="round"
      >
        <animate
          attributeName="d"
          values="
            M 42,76 C 42,76 42,76 42,76;
            M 42,76 C 42,76 42,76 42,76;
            M 42,76 C 65,61 87,46 110,31;
            M 42,76 C 55,30 82,20 110,31;
            M 42,76 C 55,30 82,20 110,31;
            M 42,76 C 55,30 82,20 110,31;
            M 42,76 C 55,30 82,20 110,31
          "
          keyTimes="0;0.14;0.28;0.42;0.56;0.66;1"
          dur={dur}
          repeatCount="indefinite"
        />
        <animate
          attributeName="opacity"
          values="0;0;1;1;1;0;0"
          keyTimes="0;0.14;0.28;0.42;0.56;0.66;1"
          dur={dur}
          repeatCount="indefinite"
        />
      </path>

      {/* The rest of the Bézier path draws on after the curve gesture. */}
      <path
        d={path}
        pathLength="1"
        fill="rgba(192, 138, 31, 0.12)"
        stroke="#c08a1f"
        strokeWidth="2.2"
        strokeLinejoin="round"
        strokeLinecap="round"
        strokeDasharray="1"
      >
        <animate
          attributeName="stroke-dashoffset"
          values="1;1;1;0.76;0.42;0;0"
          keyTimes="0;0.16;0.42;0.48;0.66;0.84;1"
          dur={dur}
          repeatCount="indefinite"
        />
        <animate
          attributeName="fill-opacity"
          values="0;0;0;0;0;1;1"
          keyTimes="0;0.16;0.34;0.48;0.66;0.84;1"
          dur={dur}
          repeatCount="indefinite"
        />
      </path>

      {/* Direction handles at the smooth top anchor. */}
      <g opacity="0">
        <line x1="110" y1="31" x2="110" y2="31" stroke="#64748b" strokeWidth="1.2">
          <animate attributeName="x1" values="110;110;110;80;80;80;110" keyTimes="0;0.25;0.29;0.42;0.60;0.76;1" dur={dur} repeatCount="indefinite" />
          <animate attributeName="y1" values="31;31;31;20;20;20;31" keyTimes="0;0.25;0.29;0.42;0.60;0.76;1" dur={dur} repeatCount="indefinite" />
          <animate attributeName="x2" values="110;110;110;140;140;140;110" keyTimes="0;0.25;0.29;0.42;0.60;0.76;1" dur={dur} repeatCount="indefinite" />
          <animate attributeName="y2" values="31;31;31;42;42;42;31" keyTimes="0;0.25;0.29;0.42;0.60;0.76;1" dur={dur} repeatCount="indefinite" />
        </line>
        <circle cx="110" cy="31" r="2.5" fill="white" stroke="#64748b" strokeWidth="1.2">
          <animate attributeName="cx" values="110;110;110;80;80;80;110" keyTimes="0;0.25;0.29;0.42;0.60;0.76;1" dur={dur} repeatCount="indefinite" />
          <animate attributeName="cy" values="31;31;31;20;20;20;31" keyTimes="0;0.25;0.29;0.42;0.60;0.76;1" dur={dur} repeatCount="indefinite" />
        </circle>
        <circle cx="110" cy="31" r="2.5" fill="white" stroke="#64748b" strokeWidth="1.2">
          <animate attributeName="cx" values="110;110;110;140;140;140;110" keyTimes="0;0.25;0.29;0.42;0.60;0.76;1" dur={dur} repeatCount="indefinite" />
          <animate attributeName="cy" values="31;31;31;42;42;42;31" keyTimes="0;0.25;0.29;0.42;0.60;0.76;1" dur={dur} repeatCount="indefinite" />
        </circle>
        <animate
          attributeName="opacity"
          values="0;0;1;1;1;0;0"
          keyTimes="0;0.25;0.29;0.60;0.72;0.84;1"
          dur={dur}
          repeatCount="indefinite"
        />
      </g>

      {/* Anchors appear as they are placed; the smooth anchor is highlighted. */}
      <circle cx="42" cy="76" r="3" fill="white" stroke="#c08a1f" strokeWidth="1.2">
        <animate attributeName="opacity" values="0;1;1;1;1;1;1" keyTimes="0;0.14;0.25;0.48;0.66;0.84;1" dur={dur} repeatCount="indefinite" />
      </circle>
      <circle cx="110" cy="31" r="3.5" fill="#f59e0b" stroke="#c08a1f" strokeWidth="1.2">
        <animate attributeName="opacity" values="0;0;1;1;1;1;1" keyTimes="0;0.18;0.29;0.48;0.66;0.84;1" dur={dur} repeatCount="indefinite" />
      </circle>
      <circle cx="178" cy="76" r="3" fill="white" stroke="#c08a1f" strokeWidth="1.2">
        <animate attributeName="opacity" values="0;0;0;0;1;1;1" keyTimes="0;0.18;0.29;0.48;0.62;0.84;1" dur={dur} repeatCount="indefinite" />
      </circle>

      {/* Pen nib: click first, drag a smooth anchor, place the last point, close. */}
      <g transform="translate(194,88)">
        <animateTransform
          attributeName="transform"
          type="translate"
          values="194,88;42,76;110,31;140,42;178,76;42,76;194,88;194,88"
          keyTimes="0;0.14;0.28;0.42;0.62;0.82;0.94;1"
          dur={dur}
          repeatCount="indefinite"
          calcMode="spline"
          keySplines="0.4,0,0.2,1;0.4,0,0.2,1;0.2,0,0.2,1;0.4,0,0.2,1;0.4,0,0.2,1;0.4,0,0.2,1;0,0,1,1"
        />
        <path d="M0,0 C0.8,2.4 1.6,4 3.6,6 L4.8,4.8 C2.8,2.8 1.2,2 0,0" fill="#1e293b" stroke="#1e293b" strokeWidth="0.5" />
        <path d="M3.6,6 L8.8,11.2 L11.2,8.8 L6,3.6 Z" fill="white" stroke="#1e293b" strokeWidth="0.8" />
        <line x1="0" y1="0" x2="2.8" y2="2.8" stroke="#1e293b" strokeWidth="0.8" />
        <circle cx="2.8" cy="2.8" r="0.5" fill="#1e293b" />
      </g>
    </svg>
  );
}

export function SnappingAnimation() {
  const dur = '3.8s';
  const keyTimes = '0;0.14;0.54;0.62;0.84;1';
  const xValues = '52;52;138;150;150;52';
  const yValues = '82;82;39;30;30;82';

  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 110" overflow="hidden">
      <rect width="220" height="110" fill="transparent" />

      {/* A familiar closed shape provides an unambiguous corner target. */}
      <rect
        x="150"
        y="30"
        width="42"
        height="52"
        rx="3"
        fill="rgba(138, 130, 112, 0.05)"
        stroke="#8a8270"
        strokeWidth="1.5"
      />
      <circle cx="150" cy="30" r="3" fill="white" stroke="#8a8270" strokeWidth="1.2" />

      {/* Alignment guides appear only when the moving point locks on. */}
      <g opacity="0">
        <line x1="150" y1="10" x2="150" y2="99" stroke="#c08a1f" strokeWidth="1" strokeDasharray="3 3" />
        <line x1="24" y1="30" x2="202" y2="30" stroke="#c08a1f" strokeWidth="1" strokeDasharray="3 3" />
        <animate attributeName="opacity" values="0;0;0;1;1;0" keyTimes={keyTimes} dur={dur} repeatCount="indefinite" />
      </g>

      {/* The segment follows freely, then jumps the last few pixels to target. */}
      <line x1="31" y1="88" x2="52" y2="82" stroke="#c08a1f" strokeWidth="2.2" strokeLinecap="round">
        <animate attributeName="x2" values={xValues} keyTimes={keyTimes} dur={dur} repeatCount="indefinite" />
        <animate attributeName="y2" values={yValues} keyTimes={keyTimes} dur={dur} repeatCount="indefinite" />
      </line>
      <circle cx="52" cy="82" r="3.5" fill="#f59e0b" stroke="#c08a1f" strokeWidth="1.2">
        <animate attributeName="cx" values={xValues} keyTimes={keyTimes} dur={dur} repeatCount="indefinite" />
        <animate attributeName="cy" values={yValues} keyTimes={keyTimes} dur={dur} repeatCount="indefinite" />
      </circle>

      {/* A quick pulse makes the moment of acquisition unmistakable. */}
      <circle cx="150" cy="30" r="5" fill="none" stroke="#c08a1f" strokeWidth="1.5" opacity="0">
        <animate attributeName="r" values="5;5;5;5;13;13" keyTimes={keyTimes} dur={dur} repeatCount="indefinite" />
        <animate attributeName="opacity" values="0;0;0;1;0;0" keyTimes={keyTimes} dur={dur} repeatCount="indefinite" />
      </circle>

      {/* Cursor travels with the unsnapped point and settles on the target. */}
      <g transform="translate(52,82)">
        <animateTransform
          attributeName="transform"
          type="translate"
          values="52,82;52,82;138,39;150,30;150,30;52,82"
          keyTimes={keyTimes}
          dur={dur}
          repeatCount="indefinite"
        />
        <path d="M1 1v14l4-4 3.2 6.2 2.5-1.3-3.2-6H13z" fill="#1e293b" stroke="white" strokeWidth="0.8" strokeLinejoin="round" />
      </g>
    </svg>
  );
}

export function PencilAnimation() {
  const dur = '3s';
  const freehandPath = 'M 60,75 C 60,30 160,30 160,75 C 160,100 60,100 60,75';
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 110" overflow="hidden">
      <rect width="220" height="110" fill="transparent" />
      
      {/* Target closed curved path */}
      <path d={freehandPath} fill="rgba(192, 138, 31, 0.04)" stroke="#8a8270" strokeWidth="1.2" strokeDasharray="3 3" />
      
      {/* Reveal one immutable path. Already-drawn ink never morphs behind the pencil. */}
      <path
        d={freehandPath}
        pathLength="1"
        fill="rgba(192, 138, 31, 0.12)"
        stroke="#c08a1f"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
        strokeDasharray="1"
        strokeDashoffset="1"
      >
        <animate
          attributeName="stroke-dashoffset"
          values="1;1;0;0"
          keyTimes="0;0.15;0.85;1"
          dur={dur}
          repeatCount="indefinite"
        />
        <animate
          attributeName="fill-opacity"
          values="0;0;0;1"
          keyTimes="0;0.15;0.85;1"
          dur={dur}
          repeatCount="indefinite"
        />
      </path>
      
      {/* The pencil follows the exact same path used by the revealed stroke. */}
      <g>
        <animateMotion
          path={freehandPath}
          keyPoints="0;0;1;1"
          keyTimes="0;0.15;0.85;1"
          calcMode="linear"
          dur={dur}
          repeatCount="indefinite"
        />

        {/* Pencil body */}
        <g transform="translate(-2, -18) rotate(45 0 16)">
          <path d="M 0,16 L 3,8 L -3,8 Z" fill="#f59e0b" />
          <rect x="-3" y="-8" width="6" height="16" fill="#f59e0b" />
          <rect x="-3" y="-12" width="6" height="4" fill="#ef4444" />
          <path d="M 0,16 L 1,14 L -1,14 Z" fill="#000000" />
        </g>
      </g>
    </svg>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   Solder Animation — the lead lines between glass pieces grow and shrink as
   the solder width is adjusted with a slider
   ═══════════════════════════════════════════════════════════════════════════ */
export function SolderAnimation() {
  const dur = '3.5s';
  const KT  = '0; 0.45; 0.55; 1';
  const SPL = '0.4,0,0.2,1; 0,0,1,1; 0.4,0,0.2,1';
  const SW  = '1.5;6;6;1.5';
  const SOLDER = '#1a1a1a';

  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 110" overflow="hidden">
      <rect width="220" height="110" fill="transparent" />

      {/* Glass petals — the solder outline pulses thick → thin */}
      {ANGLES.map(a => (
        <ellipse key={a}
          cx={FC.x} cy={FC.y - FO} rx={FRX} ry={FRY}
          transform={`rotate(${a}, ${FC.x}, ${FC.y})`}
          fill="rgba(142, 136, 122, 0.08)" stroke={SOLDER} strokeWidth="1.5" strokeLinejoin="round">
          <animate attributeName="stroke-width" values={SW} keyTimes={KT} dur={dur}
            repeatCount="indefinite" calcMode="spline" keySplines={SPL} />
        </ellipse>
      ))}
      <circle cx={FC.x} cy={FC.y} r={FCR} fill="rgba(142, 136, 122, 0.35)" stroke={SOLDER} strokeWidth="1.5">
        <animate attributeName="stroke-width" values={SW} keyTimes={KT} dur={dur}
          repeatCount="indefinite" calcMode="spline" keySplines={SPL} />
      </circle>

      {/* Thickness slider */}
      <line x1="74" y1="100" x2="146" y2="100" stroke="rgba(40, 30, 15, 0.14)" strokeWidth="3" strokeLinecap="round" />
      <line x1="74" y1="100" x2="146" y2="100" stroke="#c08a1f" strokeWidth="3" strokeLinecap="round" strokeDasharray="72">
        <animate attributeName="stroke-dashoffset" values="71;1;1;71" keyTimes={KT} dur={dur}
          repeatCount="indefinite" calcMode="spline" keySplines={SPL} />
      </line>
      <circle cy="100" r="5" fill="#ffffff" stroke="#c08a1f" strokeWidth="2">
        <animate attributeName="cx" values="75;145;145;75" keyTimes={KT} dur={dur}
          repeatCount="indefinite" calcMode="spline" keySplines={SPL} />
      </circle>
    </svg>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   Symmetry Animation — a mark drawn in one facet is replicated radially across
   all facets at once
   ═══════════════════════════════════════════════════════════════════════════ */
export function SymmetryAnimation() {
  const dur = '4.5s';

  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 110" overflow="hidden">
      <rect width="220" height="110" fill="transparent" />

      {/* 3 side-by-side trapezoidal lamp facets */}
      <polygon points="42,20 70,20 80,75 32,75" fill="rgba(148,163,184,0.04)" stroke="rgba(40, 30, 15, 0.18)" strokeWidth="1.2" />
      <polygon points="96,20 124,20 134,75 86,75" fill="rgba(148,163,184,0.04)" stroke="rgba(40, 30, 15, 0.18)" strokeWidth="1.2" />
      <polygon points="150,20 178,20 188,75 140,75" fill="rgba(148,163,184,0.04)" stroke="rgba(40, 30, 15, 0.18)" strokeWidth="1.2" />

      {/* Segment 1: Growing drawn line on middle facet */}
      <polyline points="" fill="none" stroke="#c08a1f" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round">
        <animate attributeName="points"
          values="
            86,75;
            86,75 86,75;
            86,75 90,55;
            86,75 90,55 90,55;
            86,75 90,55 130,55;
            86,75 90,55 130,55 130,55;
            86,75 90,55 130,55 134,75;
            86,75 90,55 130,55 134,75 86,75;
            86,75 90,55 130,55 134,75 86,75
          "
          keyTimes="0; 0.10; 0.22; 0.32; 0.44; 0.54; 0.66; 0.76; 1"
          dur={dur} repeatCount="indefinite" />
        <animate attributeName="opacity" values="1;1;1;1;1;1;1;1;0" keyTimes="0;0.10;0.22;0.32;0.44;0.54;0.66;0.76;1" dur={dur} repeatCount="indefinite" />
      </polyline>

      {/* Segment 2: Replicated drawn line on left facet */}
      <polyline points="" fill="none" stroke="#c08a1f" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round">
        <animate attributeName="points"
          values="
            32,75;
            32,75 32,75;
            32,75 36,55;
            32,75 36,55 36,55;
            32,75 36,55 76,55;
            32,75 36,55 76,55 76,55;
            32,75 36,55 76,55 80,75;
            32,75 36,55 76,55 80,75 32,75;
            32,75 36,55 76,55 80,75 32,75
          "
          keyTimes="0; 0.10; 0.22; 0.32; 0.44; 0.54; 0.66; 0.76; 1"
          dur={dur} repeatCount="indefinite" />
        <animate attributeName="opacity" values="1;1;1;1;1;1;1;1;0" keyTimes="0;0.10;0.22;0.32;0.44;0.54;0.66;0.76;1" dur={dur} repeatCount="indefinite" />
      </polyline>

      {/* Segment 3: Replicated drawn line on right facet */}
      <polyline points="" fill="none" stroke="#c08a1f" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round">
        <animate attributeName="points"
          values="
            140,75;
            140,75 140,75;
            140,75 144,55;
            140,75 144,55 144,55;
            140,75 144,55 184,55;
            140,75 144,55 184,55 184,55;
            140,75 144,55 184,55 188,75;
            140,75 144,55 184,55 188,75 140,75;
            140,75 144,55 184,55 188,75 140,75
          "
          keyTimes="0; 0.10; 0.22; 0.32; 0.44; 0.54; 0.66; 0.76; 1"
          dur={dur} repeatCount="indefinite" />
        <animate attributeName="opacity" values="1;1;1;1;1;1;1;1;0" keyTimes="0;0.10;0.22;0.32;0.44;0.54;0.66;0.76;1" dur={dur} repeatCount="indefinite" />
      </polyline>

      {/* Highlight of finished glass pieces (fades in on close) */}
      <g opacity="0">
        <animate attributeName="opacity" values="0;0;0;0;0;0;0;1;1;0" keyTimes="0;0.10;0.22;0.32;0.44;0.54;0.66;0.76;0.94;1" dur={dur} repeatCount="indefinite" />
        <polygon points="32,75 36,55 76,55 80,75" fill="rgba(192, 138, 31, 0.14)" stroke="#c08a1f" strokeWidth="2" strokeLinejoin="round" />
        <polygon points="86,75 90,55 130,55 134,75" fill="rgba(192, 138, 31, 0.14)" stroke="#c08a1f" strokeWidth="2" strokeLinejoin="round" />
        <polygon points="140,75 144,55 184,55 188,75" fill="rgba(192, 138, 31, 0.14)" stroke="#c08a1f" strokeWidth="2" strokeLinejoin="round" />
      </g>

      {/* Cursor drawing the piece on middle facet */}
      <g>
        <animateTransform attributeName="transform" type="translate"
          values="
            150,95;
            86,75;
            90,55;
            130,55;
            134,75;
            86,75;
            150,95;
            150,95
          "
          keyTimes="0; 0.10; 0.22; 0.44; 0.66; 0.76; 0.88; 1"
          dur={dur} repeatCount="indefinite"
          calcMode="spline" keySplines="0.4,0,0.2,1; 0.4,0,0.2,1; 0.4,0,0.2,1; 0.4,0,0.2,1; 0.4,0,0.2,1; 0.4,0,0.2,1; 0,0,1,1" />
        <g>
          <animate attributeName="opacity" values="0;1;1;1;1;1;1;0;0" keyTimes="0;0.05;0.22;0.44;0.66;0.76;0.82;0.88;1" dur={dur} repeatCount="indefinite" />
          <polygon points="0,0 0,14 3.5,10.5 6,16 8,15 5.5,9 10,9"
            fill="white" stroke="#1e293b" strokeWidth="0.8" strokeLinejoin="round" />
        </g>
      </g>
    </svg>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   Profile Animation — dragging a control handle reshapes the lamp's silhouette,
   mirrored across its vertical axis
   ═══════════════════════════════════════════════════════════════════════════ */
export function ProfileAnimation() {
  const dur = '4s';
  const KT  = '0; 0.5; 1';
  const SPL = '0.4,0,0.2,1; 0.4,0,0.2,1';
  const dNarrow = 'M 92,26 L 88,57 L 80,86 L 140,86 L 132,57 L 128,26 Z';
  const dWide   = 'M 92,26 L 72,57 L 80,86 L 140,86 L 148,57 L 128,26 Z';

  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 110" overflow="hidden">
      <rect width="220" height="110" fill="transparent" />

      {/* Vertical axis of revolution */}
      <line x1="110" y1="16" x2="110" y2="96" stroke="rgba(40, 30, 15, 0.18)" strokeWidth="1" strokeDasharray="3 3" />

      {/* Lamp body — silhouette bulges in and out with straight polyline segments */}
      <path d={dNarrow} fill="rgba(192, 138, 31, 0.08)" stroke="#7a5512" strokeWidth="1.6" strokeLinejoin="round">
        <animate attributeName="d" values={`${dNarrow};${dWide};${dNarrow}`} keyTimes={KT} dur={dur}
          repeatCount="indefinite" calcMode="spline" keySplines={SPL} />
      </path>

      {/* Top + bottom rings */}
      <ellipse cx="110" cy="26" rx="18" ry="4.5" fill="rgba(192, 138, 31, 0.14)" stroke="#7a5512" strokeWidth="1.2" />
      <ellipse cx="110" cy="86" rx="30" ry="6"   fill="rgba(192, 138, 31, 0.14)" stroke="#7a5512" strokeWidth="1.2" />

      {/* Right control handle (dragged) + left mirror — placed exactly on the joints */}
      <circle cy="57" r="4.5" fill="#ffffff" stroke="#7a5512" strokeWidth="1.4">
        <animate attributeName="cx" values="132;148;132" keyTimes={KT} dur={dur}
          repeatCount="indefinite" calcMode="spline" keySplines={SPL} />
      </circle>
      <circle cy="57" r="4.5" fill="#ffffff" stroke="#7a5512" strokeWidth="1.4">
        <animate attributeName="cx" values="88;72;88" keyTimes={KT} dur={dur}
          repeatCount="indefinite" calcMode="spline" keySplines={SPL} />
      </circle>
    </svg>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   Pack Animation — scattered pieces translate and rotate into a tightly
   packed arrangement on the sheet, then scatter again
   ═══════════════════════════════════════════════════════════════════════════ */
export function PackAnimation() {
  const dur = '4.5s';
  const KT  = '0; 0.14; 0.55; 0.82; 1';
  const SPL = '0,0,1,1; 0.4,0,0.2,1; 0,0,1,1; 0.45,0,0.55,1';

  const pieces = [
    { w: 40, h: 34, sx: 150, sy: 30, sr: 18,  px: 40, py: 33 },
    { w: 30, h: 34, sx: 58,  sy: 82, sr: -22, px: 79, py: 33 },
    { w: 72, h: 22, sx: 150, sy: 84, sr: 12,  px: 53, py: 62 },
  ];

  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 110" overflow="hidden">
      <rect width="220" height="110" fill="transparent" />

      {/* Glass sheet */}
      <rect x="14" y="12" width="190" height="86" rx="3"
        fill="rgba(192, 138, 31, 0.04)" stroke="#c08a1f" strokeWidth="1.4" strokeDasharray="4 3" />

      {pieces.map((p, i) => (
        <g key={i}>
          <animateTransform attributeName="transform" type="translate"
            values={`${p.sx},${p.sy}; ${p.sx},${p.sy}; ${p.px},${p.py}; ${p.px},${p.py}; ${p.sx},${p.sy}`}
            keyTimes={KT} dur={dur} repeatCount="indefinite" calcMode="spline" keySplines={SPL} />
          <g>
            <animateTransform attributeName="transform" type="rotate"
              values={`${p.sr};${p.sr};0;0;${p.sr}`}
              keyTimes={KT} dur={dur} repeatCount="indefinite" calcMode="spline" keySplines={SPL} />
            <rect x={-p.w / 2} y={-p.h / 2} width={p.w} height={p.h} rx="2"
              fill={IF} stroke={IS} strokeWidth="1.5" strokeLinejoin="round" />
          </g>
        </g>
      ))}
    </svg>
  );
}
