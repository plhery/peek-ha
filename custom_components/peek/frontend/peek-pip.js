// Pip, the parcel with a face, as Peek's widgets and parcel cards draw him: the box in its 300 × 310 frame, in the
// card's own colours (`--pip-ink` and `--pip-surface` on an ancestor), with a face for the parcel's stage. A port of
// Peek's src/components/map/PipDrawing.tsx and pipGeometry.ts, drawn still: no change of face, no box opening.

/** The box in its 300 × 310 frame, as Peek's `PARCEL` (src/components/Icon.tsx). */
const PARCEL = {
  inside: 'm55 142 95-47 95 47-95 48-95-48Z',
  left: 'm55 142 95 48v87l-95-48v-87Z',
  right: 'm150 190 95-48v87l-95 48v-87Z',
  hairlines: 'M56 144v84l93 47m2 0 92-46v-84',
  edges: 'm55 142 95 48 95-48m-95 48v87',
  tape: 'm96 122 13-7 95 48-13 7-95-48Z',
  seam: 'm103 119 94 47',
  facePlane: 'matrix(1 0.505263 0 1 55 142)',
  glint: 'M0 -1 .24 -.24 1 0 .24 .24 0 1 -.24 .24 -1 0 -.24 -.24Z',
  glints: [[43, 96, 23], [91, 57, 16], [151, 36, 24], [216, 55, 18], [261, 96, 25], [233, 145, 13]],
  flaps: {
    backLeft: { points: [[55, 142], [150, 95], [190, 143], [95, 190]], openedCorner: [112, 48] },
    backRight: { points: [[150, 95], [245, 142], [197.5, 166], [102.5, 118.5]], openedCorner: [270, 88] },
    frontRight: { points: [[245, 142], [150, 190], [102.5, 166], [197.5, 118.5]], openedCorner: [193, 189] },
    frontLeft: { points: [[55, 142], [150, 190], [197.5, 166], [102.5, 118.5]], openedCorner: [107, 189] },
  },
};
const EAGER_LIFT = 16;
const EYES = [26.25, 69.75];
const EYE_Y = 33;
const TWINKLES = ['ink', 'glint', 'ink', 'glint-deep', 'glint', 'ink'];

/** How Pip feels about the parcel's stage; one just added looks around too. */
export function pipMood(stage) {
  switch (stage) {
    case 'out_for_delivery': return 'eager';
    case 'customs': case 'ready_for_pickup': return 'wait';
    case 'failed_attempt': case 'exception': case 'returned': return 'worry';
    case 'delivered': return 'joy';
    default: return 'look';
  }
}

const fill = (name) => `style="fill:var(--pip-${name})"`;
const round = (value) => Number(value.toFixed(2));

/** A flap's corners, resting on the box or folded open on its hinge, as Peek's `flapPoints`. */
function flapPoints({ points, openedCorner }, open) {
  if (!open) return points.map((point) => point.join(',')).join(' ');
  const [origin, hinge, corner] = points;
  const angle = Math.atan2(hinge[1] - origin[1], hinge[0] - origin[0]);
  const local = ([x, y]) => [
    (x - origin[0]) * Math.cos(angle) + (y - origin[1]) * Math.sin(angle),
    (y - origin[1]) * Math.cos(angle) - (x - origin[0]) * Math.sin(angle),
  ];
  const from = local(corner);
  const to = local(openedCorner);
  const scale = to[1] / from[1];
  const slant = (to[0] - from[0]) / from[1];
  return points.map((point) => {
    const [x, y] = local(point);
    const foldedX = x + y * slant;
    const foldedY = y * scale;
    return [origin[0] + foldedX * Math.cos(angle) - foldedY * Math.sin(angle),
      origin[1] + foldedX * Math.sin(angle) + foldedY * Math.cos(angle)].map(round).join(',');
  }).join(' ');
}

function flap(name, tone, open) {
  return `<polygon points="${flapPoints(PARCEL.flaps[name], open)}" style="fill:var(--pip-${tone});stroke:var(--pip-ink)"`
    + ' stroke-opacity=".24" stroke-width=".7"/>';
}

function eyes(rx, ry, pupil, [lookX, lookY]) {
  return EYES.map((x) => {
    const px = round(x + lookX * 10.5);
    const py = round(EYE_Y + lookY * 10.5);
    return `<ellipse cx="${x}" cy="${EYE_Y}" rx="${rx}" ry="${ry}" ${fill('paper')}/>`
      + `<circle cx="${px}" cy="${py}" r="${pupil}" ${fill('deep')}/>`
      + `<circle cx="${round(px - 2.7)}" cy="${round(py - 3)}" r="2.4" ${fill('paper')}/>`;
  }).join('');
}

const blush = () => EYES.map((x) => `<ellipse cx="${x - 1}" cy="55.5" rx="9.75" ry="4.8" ${fill('blush')} opacity=".55"/>`).join('');
const deepLine = (d, width) => `<path d="${d}" style="stroke:var(--pip-deep)" stroke-width="${width}" stroke-linecap="round"/>`;
const mouth = (d, width) => `<path d="${d}" style="fill:var(--pip-deep);stroke:var(--pip-deep)" stroke-width="${width}" stroke-linejoin="round"/>`;

/** The face on the box's left side. In `look` and `eager` he watches the dot on his `side` (0: none, he looks down). */
function face(mood, side) {
  const toward = (y) => (side ? [0.44 * side, y] : [0, 0.3]);
  switch (mood) {
    case 'eager':
      return eyes(17.25, 19.5, 6.3, toward(-0.12)) + blush() + mouth('M37.5 55.5Q48 72 58.5 55.5Z', 2.4)
        + `<path d="M42.6 63.9Q48 60.3 53.4 63.9Q48 68.1 42.6 63.9Z" ${fill('blush')}/>`;
    case 'wait':
      return eyes(15, 17.25, 8.1, [-0.24, -0.52]) + deepLine('M41.25 59.25H54.75', 3.6);
    case 'worry':
      return eyes(15, 17.25, 8.1, [0, 0.16]) + deepLine('M12.75 9L36.75 8.5M56.25 7L80.25 4.5', 3.6)
        + deepLine('M39 60Q48 55 57 60', 3.6);
    case 'joy':
      return deepLine('M14.25 37.5Q26.25 21 38.25 37.5M57.75 37.5Q69.75 21 81.75 37.5', 4.5) + blush()
        + mouth('M33.75 53.25Q48 78 62.25 53.25Z', 2.7) + `<path d="M41.1 66Q48 61.5 54.9 66Q48 71.4 41.1 66Z" ${fill('blush')}/>`;
    default:
      return eyes(15, 17.25, 8.1, toward(0.06)) + deepLine('M39 57Q48 67.5 57 57', 3.6);
  }
}

/**
 * The part of the frame he covers, as Peek's `pipExtents`, down to his shadow: `[left, top, right, bottom]`. Open, his
 * flaps reach further than the box; eager, he is lifted and his speed lines trail on the side away from the place.
 */
export function pipExtents(mood, side = 0) {
  if (mood === 'joy') return [12, 24, 288, 296];
  if (mood === 'eager') return [side < 0 ? 52 : 0, 92 - EAGER_LIFT, side < 0 ? 300 : 248, 296];
  return [52, 92, 248, 296];
}

/**
 * Pip as SVG markup, his box `size` px wide. `side` is where the parcel's place is, from him: -1 to his left, 1 to
 * his right, 0 none. Out for delivery he hurries toward it; delivered, his box is open.
 */
export function pipSvg(mood, side = 0, size = 44) {
  const open = mood === 'joy';
  const eager = mood === 'eager';
  const tilt = eager ? -5 : mood === 'worry' ? 3 : 0;
  const speed = eager
    ? `<path d="M14 170H40M2 196H36M18 222H40" style="stroke:var(--pip-ink)" stroke-width="7" stroke-linecap="round"`
      + ` opacity=".32"${side < 0 ? ' transform="matrix(-1 0 0 1 300 0)"' : ''}/>`
    : '';
  const glints = open
    ? PARCEL.glints.map(([x, y, size], index) => `<path d="${PARCEL.glint}" transform="translate(${x} ${y}) scale(${size / 2})"`
      + ` ${fill(TWINKLES[index])}/>`).join('')
    : '';
  const tape = open
    ? ''
    : `<path d="${PARCEL.tape}" ${fill('tape')}/><path d="${PARCEL.seam}" style="stroke:var(--pip-seam)" stroke-opacity=".6"`
      + ' stroke-width="1" stroke-dasharray="3 3"/>';
  const body = `<path d="${PARCEL.inside}" ${fill('deep')}/>`
    + (open ? flap('backLeft', 'back-left', true) : '')
    + flap('backRight', 'back-right', open)
    + `<path d="${PARCEL.left}" ${fill('left')}/><path d="${PARCEL.right}" ${fill('right')}/>`
    + `<path d="${PARCEL.left}" ${fill('paper')} opacity=".07"/>`
    + `<path d="${PARCEL.hairlines}" style="stroke:var(--pip-ink)" stroke-opacity=".25" stroke-width=".8"/>`
    + `<path d="${PARCEL.edges}" style="stroke:var(--pip-paper)" stroke-width="1" opacity=".4"/>`
    + `<g transform="${PARCEL.facePlane}">${face(mood, side)}</g>`
    + (open ? flap('frontRight', 'front-right', true) : '')
    + flap('frontLeft', 'front-left', open)
    + tape + glints;
  const stance = `translate(0 ${eager ? -EAGER_LIFT : 0}) rotate(${tilt} 150 230)`;
  // The box is 196 units wide in the frame.
  const [left, top, right, bottom] = pipExtents(mood, side);
  const scale = size / 196;
  return `<svg class="pk-pip${eager ? ' pk-pip-eager' : ''}" viewBox="${left} ${top} ${right - left} ${bottom - top}"`
    + ` width="${round((right - left) * scale)}" height="${round((bottom - top) * scale)}"`
    + ` fill="none" aria-hidden="true"><ellipse cx="150" cy="286" rx="${eager ? 69 : 84}" ry="10" ${fill('shadow')}/>`
    + `${speed}<g transform="${stance}"><g class="pk-pip-body">${body}</g></g></svg>`;
}

/** Pip's tones, from the card's ink and surface as Peek mixes them; under `.dark` the surface is the darker one. */
export const PIP_CSS = `
  .pk-pip { display: block; overflow: visible;
    --pip-deep: color-mix(in srgb, var(--pip-ink) 82%, black);
    --pip-paper: color-mix(in srgb, var(--pip-surface) 38%, white);
    --pip-shadow: color-mix(in srgb, var(--pip-deep) 14%, transparent);
    --pip-right: color-mix(in srgb, var(--pip-surface), var(--pip-ink) 84%);
    --pip-left: color-mix(in srgb, var(--pip-surface), var(--pip-ink) 56%);
    --pip-back-left: color-mix(in srgb, var(--pip-surface), var(--pip-ink) 62%);
    --pip-back-right: color-mix(in srgb, var(--pip-surface), var(--pip-ink) 40%);
    --pip-front-right: color-mix(in srgb, var(--pip-surface), var(--pip-ink) 50%);
    --pip-front-left: color-mix(in srgb, var(--pip-surface), var(--pip-ink) 36%);
    --pip-tape: color-mix(in srgb, var(--pip-surface), var(--pip-ink) 20%);
    --pip-seam: color-mix(in srgb, var(--pip-surface), var(--pip-ink) 70%);
    --pip-blush: color-mix(in srgb, var(--pip-left) 45%, #f0707e);
    --pip-glint: color-mix(in srgb, var(--pip-surface), var(--pip-ink) 72%);
    --pip-glint-deep: color-mix(in srgb, var(--pip-surface), var(--pip-ink) 86%); }
  .dark .pk-pip {
    --pip-deep: color-mix(in srgb, var(--pip-surface) 82%, black);
    --pip-paper: color-mix(in srgb, var(--pip-ink) 38%, white);
    --pip-shadow: rgb(0 0 0 / 26%); }
  .pk-pip-eager .pk-pip-body { transform-origin: 150px 277px; animation: pk-pip-bob 1.1s ease-in-out infinite; }
  @keyframes pk-pip-bob { 0%, 100% { transform: translateY(0) rotate(-2deg); } 50% { transform: translateY(-3px) rotate(2.5deg); } }
  @media (prefers-reduced-motion: reduce) { .pk-pip-eager .pk-pip-body { animation: none; } }
`;
