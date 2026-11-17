#!/usr/bin/env node
/**
 * Writes custom_components/peek/frontend/peek-trucks.js, the carrier trucks the Lovelace card draws, from a Peek
 * checkout's brand data (src/brand) and the carrier catalog of the Universal Parcel Scraper it pins.
 *
 *   node scripts/build_trucks.mjs <peek-checkout> [--all]     (or set PEEK_CHECKOUT)
 *
 * Every catalog carrier gets its colours; the carriers below (and their brand families) also get their livery, and
 * `--all` gives every carrier its own. Each truck is drawn as Peek's CarrierMark draws it, with the paints resolved
 * to literal colours: the parts Peek paints differently in dark switch under an ancestor with class `dark`.
 */
import { readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

/** Carriers drawn in their own livery, by catalog id. The rest of each one's brand family follows (dpd-*, gls-*…). */
const LIVERIES = [
  // Worldwide and cross-border
  'dhl', 'ups', 'fedex', 'tnt', 'amazon-logistics', 'aliexpress', 'asendia', 'spring-gds', 'landmark-global',
  'yunexpress', 'four-px', 'yanwen', 'cne', 'sunyou', 'china-post', 'ems', 'sf-express', 'j-and-t', 'gofo',
  'packlink', 'vinted-go', 'ecoscooting',
  // Switzerland
  'swiss-post', 'quickpac', 'planzer', 'gls-ch', 'dpd',
  // France
  'la-poste', 'chronopost', 'mondial-relay', 'relais-colis', 'colis-prive', 'geodis', 'colisweb', 'c-chez-vous',
  'heppner', 'ciblex', 'paack',
  // Germany and Austria
  'hermes', 'hermes-de', 'go-express', 'trans-o-flex', 'austrian-post',
  // United Kingdom and Ireland
  'royal-mail', 'parcelforce', 'evri', 'inpost', 'apc-overnight', 'whistl', 'dx', 'an-post',
  // Benelux
  'bpost', 'post-luxembourg', 'budbee',
  // Spain and Portugal
  'correos-spain', 'correos-express', 'seur', 'mrw', 'nacex', 'ctt', 'ctt-express', 'tipsa', 'zeleris', 'envialia',
  // Italy
  'poste-italiane', 'brt',
  // Nordics
  'postnord', 'bring-posten', 'posti', 'instabox', 'dao', 'matkahuolto', 'airmee', 'helthjem', 'early-bird',
  // Poland and Czechia
  'poczta-polska', 'orlen-paczka', 'allegro-one', 'packeta',
  // United States
  'usps', 'ontrac', 'uniuni', 'speedx', 'lso', 'veho', 'cdl', 'osm-worldwide', 'epost-global',
  // Canada
  'canada-post', 'purolator', 'canpar', 'intelcom', 'loomis-express', 'nationex',
  // Australia and New Zealand
  'australia-post', 'aramex', 'couriersplease', 'team-global-express', 'nz-post',
];

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const outputPath = path.join(repoRoot, 'custom_components', 'peek', 'frontend', 'peek-trucks.js');

const args = process.argv.slice(2);
const everyLivery = args.includes('--all');
const checkout = args.find((arg) => !arg.startsWith('--')) ?? process.env.PEEK_CHECKOUT;
if (!checkout) {
  console.error('usage: node scripts/build_trucks.mjs <peek-checkout> [--all]   (a clone of github.com/plhery/peek-delivery-tracker with npm ci done)');
  process.exit(2);
}
const peekRoot = path.resolve(checkout);

// Peek's own reader of src/brand: families, palettes and decals spread over each family as the app spreads them.
const { readBrandData } = await import(pathToFileURL(path.join(peekRoot, 'scripts', 'generate-brand.mjs')).href);
const brand = readBrandData();
// The scraper's published catalog: `carrierInfo(id).name` without a locale is `displayName`.
const catalog = JSON.parse(readFileSync(
  path.join(peekRoot, 'node_modules', 'universal-parcel-scraper', 'data', 'catalog.json'), 'utf8'));

// ---- Palette derivation, as src/brand/index.ts does it ----

const HEX = /^#[\da-f]{6}$/i;

function mix(color, base, amount) {
  const hex = HEX.test(color) ? color : brand.fallbackColor;
  return '#' + [1, 3, 5].map((offset) => Math.round(
    parseInt(hex.slice(offset, offset + 2), 16) * (1 - amount)
    + parseInt(base.slice(offset, offset + 2), 16) * amount,
  ).toString(16).padStart(2, '0')).join('');
}

const linear = (channel) => (channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4);
const encoded = (channel) => {
  const clamped = Math.min(1, Math.max(0, channel));
  return clamped <= 0.0031308 ? 12.92 * clamped : 1.055 * clamped ** (1 / 2.4) - 0.055;
};
const channels = (hex) => [1, 3, 5].map((offset) => parseInt(hex.slice(offset, offset + 2), 16) / 255);

function luminance(hex) {
  const [red, green, blue] = channels(hex).map(linear);
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
}

function contrast(first, second) {
  const [light, dark] = [luminance(first), luminance(second)].sort((a, b) => b - a);
  return (light + 0.05) / (dark + 0.05);
}

function oklch(hex) {
  const [red, green, blue] = channels(hex).map(linear);
  const l = Math.cbrt(0.4122214708 * red + 0.5363325363 * green + 0.0514459929 * blue);
  const m = Math.cbrt(0.2119034982 * red + 0.6806995451 * green + 0.1073969566 * blue);
  const s = Math.cbrt(0.0883024619 * red + 0.2817188376 * green + 0.6299787005 * blue);
  const a = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s;
  const b = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s;
  return [0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s, Math.hypot(a, b), ((Math.atan2(b, a) * 180) / Math.PI + 360) % 360];
}

function fromOklch(lightness, chroma, hue) {
  const a = chroma * Math.cos((hue * Math.PI) / 180);
  const b = chroma * Math.sin((hue * Math.PI) / 180);
  const l = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (lightness - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return '#' + [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ].map((channel) => Math.round(encoded(channel) * 255).toString(16).padStart(2, '0')).join('');
}

function tone(color, { lightness, chroma, maxChroma, amber }) {
  const [, sourceChroma, sourceHue] = oklch(color);
  const hue = sourceHue > amber.from && sourceHue < amber.to ? amber.hue + (sourceHue - amber.from) * amber.slope : sourceHue;
  const toned = fromOklch(lightness, Math.min(maxChroma, sourceChroma * chroma), hue);
  return luminance(toned) > luminance(color) ? color : toned;
}

function litEdge(truck, surface, edge, { below, lift, floor, maxChroma } = brand.litEdge) {
  if (!HEX.test(truck) || !HEX.test(surface) || contrast(truck, surface) >= below) return edge;
  const [lightness, chroma, hue] = oklch(truck);
  return fromOklch(Math.max(lightness + lift, floor), Math.min(chroma, maxChroma), hue);
}

function carrierPalette(color, palette) {
  return Object.fromEntries(brand.derivation.map((step) => {
    if (palette?.[step.property] !== undefined) return [step.property, palette[step.property]];
    const mixed = mix(color, step.base, step.amount);
    return [step.property, step.tone ? tone(mixed, step.tone) : mixed];
  }));
}

// The port must agree with the examples Peek's own tests check.
const toneStep = brand.derivation.find((step) => step.tone);
for (const [input, expected] of brand.toneExamples) {
  if (tone(input, toneStep.tone) !== expected) throw new Error(`tone(${input}) is not ${expected}: palette derivation drifted`);
}
for (const [truck, surface, edge, expected] of brand.litEdgeExamples) {
  if (litEdge(truck, surface, edge) !== expected) throw new Error(`litEdge(${truck}) is not ${expected}: palette derivation drifted`);
}

// ---- What the generated module runs: these functions are copied into it as written ----

/** A carrier's outline when it declares none: its truck colour, a fifth darker. */
function shade(hex) {
  return '#' + [1, 3, 5].map((at) => Math.round(parseInt(hex.slice(at, at + 2), 16) * 0.8).toString(16).padStart(2, '0')).join('');
}

/**
 * One livery shape. `c`, `p` and `l` are a circle, a filled path and a stroked path; the paint follows, as `#rrggbb`
 * or one letter (`t` truck, `e` edge, `a` accent); then the circle's `cx cy r`, the path's `d`, or the stroke width
 * followed by `d` (which starts with `M`).
 */
function shapeMarkup(code, paints) {
  const literal = code[1] === '#';
  const paint = literal ? code.slice(1, 8) : paints[code[1]];
  const rest = code.slice(literal ? 8 : 2);
  if (code[0] === 'c') {
    const [cx, cy, r] = rest.split(' ');
    return `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${paint}"/>`;
  }
  if (code[0] === 'p') return `<path d="${rest}" fill="${paint}"/>`;
  const at = rest.indexOf('M');
  return `<path d="${rest.slice(at)}" stroke="${paint}" stroke-width="${rest.slice(0, at)}"/>`;
}

// ---- The truck every carrier shares ----

/** SVG numbers as CarrierMark writes them: `0.6` is `.6`. */
const n = (value) => String(value).replace(/^(-?)0\./, '$1.');
const TOKENS = { truck: 't', edge: 'e', accent: 'a' };

/** A paint in the shared templates: a literal, or `{t}`, `{e}`, `{a}` filled in per carrier. */
function templatePaint(paint) {
  if (paint.startsWith('#')) return paint;
  if (!TOKENS[paint]) throw new Error(`truck.json paints the shared truck with ${paint}, which peek-trucks.js does not carry`);
  return `{${TOKENS[paint]}}`;
}

function rgba(hex, opacity) {
  return `rgba(${channels(hex).map((channel) => Math.round(channel * 255)).join(',')},${n(opacity)})`;
}

const { truck: geometry } = brand;
const { strokeWidth, body, cab, windshield, wheels } = geometry;
const edgeClass = (stroke) => (stroke === 'edge' ? ' class="pk-edge"' : '');
const BODY = [
  `<rect x="${n(body.x)}" y="${n(body.y)}" width="${n(body.width)}" height="${n(body.height)}" rx="${n(body.rx)}" fill="${templatePaint(body.fill)}" stroke="${templatePaint(body.stroke)}" stroke-width="${n(strokeWidth)}"${edgeClass(body.stroke)}/>`,
  `<path d="${cab.d}" fill="${templatePaint(cab.fill)}" stroke="${templatePaint(cab.stroke)}" stroke-width="${n(strokeWidth)}"${edgeClass(cab.stroke)}/>`,
  `<path d="${windshield.d}" fill="${templatePaint(windshield.fill)}" class="pk-glass"/>`,
].join('');
const WHEELS = wheels.centers.map(([x, y]) => [
  `<circle cx="${n(x)}" cy="${n(y)}" r="${n(wheels.tire.r)}" fill="${templatePaint(wheels.tire.fill)}" stroke-width="${n(wheels.tire.rimWidth)}" class="pk-tire"/>`,
  `<circle cx="${n(x)}" cy="${n(y)}" r="${n(wheels.hub.r)}" fill="${templatePaint(wheels.hub.fill)}"/>`,
].join('')).join('');
const VIEWBOX = `0 0 ${n(geometry.viewBox.width)} ${n(geometry.viewBox.height)}`;
// In dark, Peek lights a dark truck's outline, tints the glass and darkens the tyres behind a faint rim.
const TRUCK_CSS = [
  '.pk-truck{overflow:visible}',
  '.dark .pk-truck .pk-edge{stroke:var(--pk-edge-dark)}',
  `.dark .pk-truck .pk-glass{fill:${windshield.dark}}`,
  `.dark .pk-truck .pk-tire{fill:${wheels.tire.dark};stroke:${rgba(wheels.tire.rim, wheels.tire.rimOpacity)}}`,
].join('');

// ---- Liveries ----

/** A livery as compact shapes. Brand properties other than truck, edge and accent are written in as literals. */
function liveryCode(decal, palette) {
  const shapes = geometry.decals[decal];
  if (!shapes) throw new Error(`truck.json has no decal ${decal}`);
  return shapes.map((shape) => {
    const source = shape.type === 'line' ? shape.stroke : shape.fill;
    const paint = source.startsWith('#') ? source : TOKENS[source] ?? palette[source];
    if (!/^(#[\da-f]{6}|[tea])$/i.test(paint)) throw new Error(`decal ${decal} has a paint ${source} that is not a colour`);
    if (shape.type === 'circle') return `c${paint}${n(shape.cx)} ${n(shape.cy)} ${n(shape.r)}`;
    if (!/^M[^|]*$/.test(shape.d)) throw new Error(`decal ${decal} has a path that does not start with M`);
    if (shape.type === 'polygon') return `p${paint}${shape.d}`;
    if (shape.type === 'line') return `l${paint}${n(shape.strokeWidth)}${shape.d}`;
    throw new Error(`decal ${decal} has a shape of type ${shape.type}`);
  }).join('|');
}

for (const id of LIVERIES) if (!catalog[id]) throw new Error(`LIVERIES names ${id}, which the catalog does not hold`);
const chosenFamilies = new Set(LIVERIES.map((id) => brand.families[id] ?? id));

const liveries = [];
const liveryIndex = new Map();
function liveryNumber(code) {
  if (!liveryIndex.has(code)) {
    liveryIndex.set(code, liveries.length);
    liveries.push(code);
  }
  return liveryIndex.get(code);
}

/**
 * A carrier as `truck,edge,edgeDark,accent,livery`, colours without `#`. An empty or missing field takes its default:
 * the edge is `shade(truck)`, the dark edge is the edge, the accent white, the livery `default` (number 0).
 */
function carrierRecord(palette, livery) {
  const strip = (hex) => hex.slice(1).toLowerCase();
  const edgeDark = litEdge(palette.truck, palette['surface-dark'], palette.edge);
  for (const [property, value] of Object.entries({ truck: palette.truck, edge: palette.edge, edgeDark, accent: palette.accent })) {
    if (!HEX.test(value)) throw new Error(`palette ${property} ${value} is not a #rrggbb colour`);
  }
  const fields = [
    strip(palette.truck),
    palette.edge.toLowerCase() === shade(palette.truck) ? '' : strip(palette.edge),
    edgeDark.toLowerCase() === palette.edge.toLowerCase() ? '' : strip(edgeDark),
    palette.accent.toLowerCase() === '#ffffff' ? '' : strip(palette.accent),
    livery === 0 ? '' : String(livery),
  ];
  while (fields.at(-1) === '') fields.pop();
  return fields.join(',');
}

const defaultPalette = carrierPalette(brand.defaultColor);
liveryNumber(liveryCode('default', defaultPalette));
const DEFAULT_RECORD = carrierRecord(defaultPalette, 0);

const carriers = {};
const drawn = new Set();
for (const [id, entry] of Object.entries(catalog)) {
  const key = entry.displayName.trim().toLowerCase();
  if (key === '__proto__') throw new Error(`carrier ${id} is named __proto__`);
  if (Object.hasOwn(carriers, key)) throw new Error(`two carriers are named ${entry.displayName}`);
  const palette = carrierPalette(entry.color, brand.palettes[id]);
  const decal = brand.decals[id] ?? 'default';
  const own = everyLivery || chosenFamilies.has(brand.families[id] ?? id);
  if (own && decal !== 'default') drawn.add(id);
  carriers[key] = carrierRecord(palette, own ? liveryNumber(liveryCode(decal, palette)) : 0);
}

// ---- The module ----

const output = `// Generated by scripts/build_trucks.mjs from Peek's brand data. Do not edit.
// Peek's carrier trucks: every catalog carrier's colours, and the liveries of ${drawn.size} carriers.

export const TRUCK_CSS = ${JSON.stringify(TRUCK_CSS)};

const BODY = ${JSON.stringify(BODY)};
const WHEELS = ${JSON.stringify(WHEELS)};

${shade}

${shapeMarkup}

/** Livery 0 is Peek's \`default\`: a stripe and a dot in the accent. */
const LIVERIES = ${JSON.stringify(liveries)};

/** Peek's default carrier colour, for a name the catalog does not hold. */
const DEFAULT = ${JSON.stringify(DEFAULT_RECORD)};

/** By lower-case display name: "truck,edge,edgeDark,accent,livery" (see build_trucks.mjs). */
const CARRIERS = ${JSON.stringify(carriers)};

/** The carrier's truck as SVG markup, from the display name Peek's API gives a parcel's \`carrier\`. */
export function truckSvg(carrier) {
  const key = typeof carrier === 'string' ? carrier.trim().toLowerCase() : '';
  const [truck, edge, edgeDark, accent, livery] = (Object.hasOwn(CARRIERS, key) ? CARRIERS[key] : DEFAULT).split(',');
  const t = '#' + truck;
  const e = edge ? '#' + edge : shade(t);
  const paints = { t, e, a: accent ? '#' + accent : '#ffffff' };
  const fill = (template) => template.replace(/\\{([tea])\\}/g, (_, token) => paints[token]);
  const decals = LIVERIES[Number(livery) || 0].split('|').map((code) => shapeMarkup(code, paints)).join('');
  return \`<svg class="pk-truck" viewBox="${VIEWBOX}" fill="none" aria-hidden="true" style="--pk-edge-dark:\${edgeDark ? '#' + edgeDark : e}">\${fill(BODY)}\${decals}\${fill(WHEELS)}</svg>\`;
}
`;

writeFileSync(outputPath, output);
console.log(`Wrote ${path.relative(repoRoot, outputPath)}: ${(Buffer.byteLength(output) / 1024).toFixed(1)} KB, `
  + `${Object.keys(carriers).length} carriers, ${drawn.size} in their own livery (${liveries.length} distinct liveries).`);
