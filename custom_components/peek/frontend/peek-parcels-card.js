// The Peek parcels card: the parcels on their way, as Peek's widgets show them. Its `list` style is the Parcels
// widget, under the sections of Peek's list; its `cards` style is a card per parcel in its carrier's colours, with
// Pip. It reads the `parcels` attribute of Peek's "On the way" sensor (and of "Delivered today", when asked to), and
// depends on nothing but Home Assistant's frontend.

import { PIP_CSS, pipMood, pipSvg } from './peek-pip.js';
import { TRUCK_CSS, carrierColors, truckSvg } from './peek-trucks.js';

const VERSION = '0.1.1';
const STYLES = ['list', 'cards'];
const SECTIONS = ['attention', 'today', 'active'];
const DEFAULT_ROWS = 6;

// Peek's own words (shared/locales): the sections, the widget's short stages, the days.
const STRINGS = {
  en: {
    attention: 'Needs attention',
    today: 'Arriving today',
    active: 'On the way',
    delivered: 'Delivered today',
    empty: 'Nothing on the way right now',
    more: (count) => `+${count} more`,
    dayToday: 'today',
    dayTomorrow: 'tomorrow',
    unavailable: 'Peek is unavailable',
    missing: 'Pick Peek’s “On the way” sensor',
    name: 'Peek parcels',
    description: 'The parcels on their way, as a list or as cards, as Peek’s widgets show them.',
    form: {
      entity: '“On the way” sensor',
      style: 'Style',
      delivered_entity: '“Delivered today” sensor',
      show_delivered: 'Show today’s deliveries',
      max_rows: 'Parcels at most',
      title: 'Title',
    },
    styles: { list: 'List', cards: 'Cards' },
    // The stages in full, as the cards write them (Peek's `stage.*`).
    stageLong: {
      pending: 'Added to tracking',
      registered: 'Label created',
      accepted: 'Received by carrier',
      in_transit: 'In transit',
      customs: 'At customs',
      exception: 'Needs attention',
      out_for_delivery: 'Out for delivery',
      failed_attempt: 'Delivery attempted',
      ready_for_pickup: 'Ready for pickup',
      delivered: 'Delivered',
      returned: 'Returned to sender',
    },
    stage: {
      pending: 'Added',
      registered: 'Label made',
      accepted: 'With carrier',
      in_transit: 'In transit',
      customs: 'At customs',
      exception: 'Issue',
      out_for_delivery: 'Delivering',
      failed_attempt: 'Attempted',
      ready_for_pickup: 'To pick up',
      delivered: 'Delivered',
      returned: 'Returned',
    },
  },
  fr: {
    attention: 'À vérifier',
    today: 'Livraison prévue aujourd’hui',
    active: 'En route',
    delivered: 'Livrés aujourd’hui',
    empty: 'Aucun colis en route pour le moment',
    more: (count) => `+${count} ${count > 1 ? 'autres' : 'autre'}`,
    dayToday: 'aujourd’hui',
    dayTomorrow: 'demain',
    unavailable: 'Peek est indisponible',
    missing: 'Choisis le capteur « En route » de Peek',
    name: 'Colis Peek',
    description: 'Tes colis en route, en liste ou en cartes, comme les montrent les widgets de Peek.',
    form: {
      entity: 'Capteur « En route »',
      style: 'Style',
      delivered_entity: 'Capteur « Livrés aujourd’hui »',
      show_delivered: 'Afficher les livraisons du jour',
      max_rows: 'Colis au plus',
      title: 'Titre',
    },
    styles: { list: 'Liste', cards: 'Cartes' },
    stageLong: {
      pending: 'Ajouté au suivi',
      registered: 'Étiquette créée',
      accepted: 'Pris en charge',
      in_transit: 'En transit',
      customs: 'À la douane',
      exception: 'Problème signalé',
      out_for_delivery: 'En livraison',
      failed_attempt: 'Tentative de livraison',
      ready_for_pickup: 'Prêt à être retiré',
      delivered: 'Livré',
      returned: 'Retourné à l’expéditeur',
    },
    stage: {
      pending: 'Ajouté',
      registered: 'Étiqueté',
      accepted: 'Expédié',
      in_transit: 'En transit',
      customs: 'À la douane',
      exception: 'Problème',
      out_for_delivery: 'En livraison',
      failed_attempt: 'Tentative',
      ready_for_pickup: 'À retirer',
      delivered: 'Livré',
      returned: 'Retourné',
    },
  },
};

const STYLE = `
  :host { display: block; }
  ha-card { padding: 12px 16px 14px; cursor: pointer; overflow: hidden; }
  .title { font-size: var(--ha-font-size-l, 16px); font-weight: var(--ha-font-weight-medium, 500);
    color: var(--primary-text-color); margin: 0 0 6px; }
  .root { --pk-warning: #963e19; display: flex; flex-direction: column; gap: 5px; }
  .root.dark { --pk-warning: #ffb184; }
  .heading { display: flex; align-items: center; gap: 5px; margin-top: 4px; }
  .heading:first-child { margin-top: 0; }
  .heading span:first-child { font-size: var(--ha-font-size-s, 12px); font-weight: 600; color: var(--primary-text-color);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .pill { font-size: 11px; font-variant-numeric: tabular-nums; color: var(--secondary-text-color); padding: 1px 5px;
    border-radius: 999px; background: color-mix(in srgb, var(--primary-text-color) 9%, transparent); }
  .row { display: flex; align-items: center; gap: 6px; min-width: 0; }
  .mark { flex: none; width: 27px; height: 18px; display: flex; }
  .mark svg { width: 27px; height: 18px; }
  .words { min-width: 0; flex: 1; display: flex; flex-direction: column; }
  .name { font-size: var(--ha-font-size-m, 14px); font-weight: 600; color: var(--primary-text-color); line-height: 1.25;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .line { font-size: var(--ha-font-size-s, 12px); color: var(--secondary-text-color); line-height: 1.3;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .attention .line { color: var(--peek-attention-color, var(--pk-warning)); }
  .more { font-size: var(--ha-font-size-s, 12px); font-weight: 600; color: var(--secondary-text-color);
    padding-left: 33px; }
  .state { font-size: var(--ha-font-size-m, 14px); color: var(--secondary-text-color); padding: 12px 0; text-align: center; }
  .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(144px, 1fr)); gap: 8px; }
  .cards + .more { padding: 8px 0 0 4px; }
  .pc { --pip-ink: var(--pc-ink); --pip-surface: var(--pc-surface); min-width: 0; min-height: 150px; box-sizing: border-box;
    display: flex; flex-direction: column; padding: 11px 13px 12px; border-radius: 18px; background: var(--pc-surface); }
  .pc-mark { display: flex; align-items: center; gap: 6px; min-width: 0; }
  .pc-mark .pk-truck { flex: none; width: 23px; height: 15px; }
  .pc-carrier { font-size: 11.5px; font-weight: 700; letter-spacing: .02em; color: var(--pc-brand); white-space: nowrap;
    overflow: hidden; text-overflow: ellipsis; }
  .pc-art { flex: 1; display: flex; align-items: center; justify-content: center; min-width: 0; min-height: 64px;
    padding: 2px 0 4px; }
  .pc-art .pk-pip { flex: none; }
  .pc-place { display: flex; align-items: center; min-width: 0; margin-top: -10px; }
  .pc-dot { flex: none; width: 8px; height: 8px; margin: 0 5px 0 1px; border-radius: 50%; background: var(--pc-ink);
    box-shadow: 0 0 0 2.5px var(--pc-ring); }
  .pc-chip { min-width: 0; padding: 3px 7px; border-radius: 8px; font-size: 12.5px; line-height: 1.25; color: var(--pc-ink);
    background: var(--pc-chip); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .pc-name { font-size: var(--ha-font-size-l, 16px); font-weight: 600; line-height: 1.22; color: var(--primary-text-color);
    overflow-wrap: anywhere; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; }
  .pc-status { margin-top: 3px; font-size: var(--ha-font-size-s, 12px); line-height: 1.3; color: var(--pc-ink);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .pc.attention .pc-status { color: var(--peek-attention-color, var(--pk-warning)); }
  ${TRUCK_CSS}
  ${PIP_CSS}
`;

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (character) => `&#${character.charCodeAt(0)};`);
}

/** The reader's language: Home Assistant's profile setting, else the page's, which the frontend sets to it. */
function localeFor(hass) {
  return hass?.locale?.language || hass?.language || globalThis.document?.documentElement?.lang || 'en';
}

function stringsFor(hass) {
  return localeFor(hass).toLowerCase().startsWith('fr') ? STRINGS.fr : STRINGS.en;
}

/** A day as YYYY-MM-DD in a time zone. */
function dayIn(date, timeZone) {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit' })
    .formatToParts(date);
  const part = (type) => parts.find((item) => item.type === type).value;
  return `${part('year')}-${part('month')}-${part('day')}`;
}

function addDays(day, count) {
  const date = new Date(`${day}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + count);
  return date.toISOString().slice(0, 10);
}

/** "today", "tomorrow", else the short weekday and date in the reader's language, such as "Mon 2 Nov". */
export function dayWords(day, today, hass) {
  if (!day) return null;
  const words = stringsFor(hass);
  if (day === today) return words.dayToday;
  if (day === addDays(today, 1)) return words.dayTomorrow;
  const date = new Date(`${day}T12:00:00Z`);
  return new Intl.DateTimeFormat(localeFor(hass), { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC' })
    .format(date).replace(/,/g, '').replace(/\.(?=\s|$)/g, '');
}

function opening(text) {
  return text ? text.charAt(0).toLocaleUpperCase() + text.slice(1) : text;
}

function title(parcel) {
  return parcel.name || parcel.sender || parcel.carrier || parcel.tracking_number || '';
}

/** A parcel's day: when it was delivered (the time, on a delivery scan's day), else the day it is expected. */
function parcelDay(parcel, today, hass) {
  if (parcel.status === 'delivered' && parcel.delivered_at) {
    return parcel.delivered_at.length > 10
      ? new Intl.DateTimeFormat(localeFor(hass), { hour: 'numeric', minute: '2-digit', timeZone: hass?.config?.time_zone })
        .format(new Date(parcel.delivered_at))
      : dayWords(parcel.delivered_at, today, hass);
  }
  return dayWords((parcel.expected_delivery || '').slice(0, 10), today, hass);
}

/** The stage and the day under a parcel's name. */
export function parcelLine(parcel, today, hass) {
  const stage = stringsFor(hass).stage[parcel.status] || parcel.status_text || '';
  const day = parcelDay(parcel, today, hass);
  return opening(day ? `${stage} · ${day}` : stage);
}

/** A card's status: the stage in full and its day, as Peek's widgets write it. Out for delivery, the day is today. */
export function cardStatus(parcel, today, hass) {
  const stage = stringsFor(hass).stageLong[parcel.status] || parcel.status_text || '';
  const day = parcel.status === 'out_for_delivery' ? null : parcelDay(parcel, today, hass);
  return opening(day ? `${stage} · ${day}` : stage);
}

/** The town of a scan's place, as a carrier writes it ("ZURICH-MULLIGEN, CH"): before the first comma, not in capitals. */
export function placeName(location) {
  const place = typeof location === 'string' ? location.split(',')[0].trim() : '';
  if (!place || /\p{Ll}/u.test(place)) return place;
  return place.toLocaleLowerCase().replace(/(^|[\s\-'’(])(\p{L})/gu, (_, before, letter) => before + letter.toLocaleUpperCase());
}

/** The parcels the cards style shows, in the order of Peek's sections, at most `max`, and how many are left out. */
export function cardParcels(parcels, extra, delivered, max) {
  const ordered = SECTIONS.flatMap((kind) => parcels.filter((parcel) => (parcel.section || 'active') === kind)
    .map((parcel) => ({ kind, parcel })));
  for (const parcel of delivered || []) ordered.push({ kind: 'delivered', parcel });
  const shown = ordered.slice(0, max);
  return { shown, left: ordered.length - shown.length + extra };
}

/** The lines the card shows: headings, rows and the count of the rest, at most `maxRows` rows. */
export function cardLines(parcels, extra, delivered, maxRows) {
  const groups = SECTIONS.map((kind) => ({ kind, parcels: parcels.filter((parcel) => (parcel.section || 'active') === kind) }));
  groups[2].extra = extra;
  if (delivered) groups.push({ kind: 'delivered', parcels: delivered });
  const lines = [];
  let shown = 0;
  let left = 0;
  for (const group of groups) {
    const count = group.parcels.length + (group.extra || 0);
    if (!count) continue;
    const room = Math.max(maxRows - shown, 0);
    const rows = group.parcels.slice(0, room);
    if (rows.length) {
      lines.push({ type: 'heading', kind: group.kind, count });
      for (const parcel of rows) lines.push({ type: 'row', kind: group.kind, parcel });
    }
    shown += rows.length;
    left += count - rows.length;
  }
  if (left > 0) lines.push({ type: 'more', count: left });
  return lines;
}

function findEntity(hass, key) {
  const fromRegistry = Object.values(hass?.entities || {})
    .find((entity) => entity.platform === 'peek' && entity.translation_key === key);
  if (fromRegistry) return fromRegistry.entity_id;
  const english = { on_the_way: 'sensor.peek_on_the_way', delivered_today: 'sensor.peek_delivered_today' }[key];
  return hass?.states?.[english] ? english : undefined;
}

class PeekParcelsCard extends HTMLElement {
  static getStubConfig(hass) {
    const config = { entity: findEntity(hass, 'on_the_way') || '', show_delivered: false, max_rows: DEFAULT_ROWS };
    const delivered = findEntity(hass, 'delivered_today');
    if (delivered) config.delivered_entity = delivered;
    return config;
  }

  static getConfigForm() {
    const sensor = { entity: { domain: 'sensor', integration: 'peek' } };
    return {
      schema: [
        { name: 'entity', required: true, selector: sensor },
        {
          name: 'style',
          selector: { select: { mode: 'list', options: STYLES.map((value) => ({ value, label: stringsFor().styles[value] })) } },
        },
        { name: 'show_delivered', selector: { boolean: {} } },
        { name: 'delivered_entity', selector: sensor },
        { name: 'max_rows', selector: { number: { min: 1, max: 30, mode: 'box' } } },
        { name: 'title', selector: { text: {} } },
      ],
      // Called with the field only.
      computeLabel: (schema) => stringsFor().form[schema.name],
    };
  }

  setConfig(config) {
    if (!config || typeof config !== 'object') throw new Error('Invalid configuration');
    if (config.style !== undefined && !STYLES.includes(config.style)) throw new Error(`style is ${STYLES.join(' or ')}`);
    this._config = { style: 'list', show_delivered: false, max_rows: DEFAULT_ROWS, ...config };
    this._last = undefined;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  get hass() {
    return this._hass;
  }

  /**
   * In 50 px units: the padding and the title, then 39 px a row and 22 px a heading or "+N more", or 158 px a row of
   * cards, two to a row.
   */
  getCardSize() {
    const start = this._config?.title ? 55 : 30;
    const height = this._cards
      ? start + Math.ceil(this._cards.shown.length / 2) * 158 + (this._cards.left ? 26 : 0)
      : (this._lines || []).reduce((sum, line) => sum + (line.type === 'row' ? 39 : 22), start);
    return Math.max(1, Math.ceil(height / 50));
  }

  /** Half a section for the list, and the whole one for cards, which want two or three side by side. */
  getGridOptions() {
    return this._config?.style === 'cards' ? { columns: 12, min_columns: 6 } : { columns: 6, min_columns: 3 };
  }

  connectedCallback() {
    if (!this._clicks) {
      this._clicks = true;
      this.addEventListener('click', () => {
        if (!this._config?.entity) return;
        this.dispatchEvent(new CustomEvent('hass-more-info', {
          detail: { entityId: this._config.entity }, bubbles: true, composed: true,
        }));
      });
    }
  }

  _render() {
    const hass = this._hass;
    const config = this._config;
    if (!hass || !config) return;
    const main = config.entity ? hass.states[config.entity] : undefined;
    const deliveredState = config.show_delivered && config.delivered_entity
      ? hass.states[config.delivered_entity] : undefined;
    const dark = Boolean(hass.themes?.darkMode);
    const today = dayIn(new Date(), hass.config?.time_zone);
    const key = [main, deliveredState, dark, today, localeFor(hass), JSON.stringify(config)];
    if (this._last && key.every((value, index) => value === this._last[index])) return;
    this._last = key;

    if (!this.shadowRoot) this.attachShadow({ mode: 'open' });
    const words = stringsFor(hass);
    let body;
    this._lines = [];
    this._cards = null;
    if (!main) {
      body = `<div class="state">${escapeHtml(words.missing)}</div>`;
    } else if (main.state === 'unavailable' || main.state === 'unknown') {
      body = `<div class="state">${escapeHtml(words.unavailable)}</div>`;
    } else {
      const parcels = Array.isArray(main.attributes.parcels) ? main.attributes.parcels : [];
      const total = Number(main.state);
      const extra = Number.isFinite(total) ? Math.max(total - parcels.length, 0) : 0;
      const delivered = deliveredState && Array.isArray(deliveredState.attributes.parcels)
        ? deliveredState.attributes.parcels : null;
      const maxRows = Math.max(1, Number(config.max_rows) || DEFAULT_ROWS);
      if (config.style === 'cards') {
        this._cards = cardParcels(parcels, extra, delivered, maxRows);
        const { shown, left } = this._cards;
        body = shown.length
          ? `<div class="cards" role="list">${shown.map((item) => this._card(item, today, hass, dark)).join('')}</div>`
            + (left ? `<div class="more">${escapeHtml(words.more(left))}</div>` : '')
          : `<div class="state">${escapeHtml(words.empty)}</div>`;
      } else {
        this._lines = cardLines(parcels, extra, delivered?.length ? delivered : null, maxRows);
        body = this._lines.length
          ? this._lines.map((line) => this._line(line, today, hass)).join('')
          : `<div class="state">${escapeHtml(words.empty)}</div>`;
      }
    }
    const heading = config.title ? `<h1 class="title">${escapeHtml(config.title)}</h1>` : '';
    this.shadowRoot.innerHTML = `<style>${STYLE}</style><ha-card>${heading}`
      + `<div class="root${dark ? ' dark' : ''}">${body}</div></ha-card>`;
  }

  _line(line, today, hass) {
    const words = stringsFor(hass);
    if (line.type === 'heading') {
      return `<div class="heading" role="heading" aria-level="2"><span>${escapeHtml(words[line.kind])}</span>`
        + `<span class="pill">${line.count}</span></div>`;
    }
    if (line.type === 'more') return `<div class="more">${escapeHtml(words.more(line.count))}</div>`;
    const { parcel } = line;
    const name = title(parcel);
    const status = parcelLine(parcel, today, hass);
    const label = [name, parcel.carrier, status].filter(Boolean).join(', ');
    return `<div class="row${line.kind === 'attention' ? ' attention' : ''}" aria-label="${escapeHtml(label)}">`
      + `<span class="mark">${truckSvg(parcel.carrier)}</span>`
      + `<span class="words"><span class="name">${escapeHtml(name)}</span>`
      + `<span class="line">${escapeHtml(status)}</span></span></div>`;
  }

  /** A parcel's card in its carrier's colours: the truck and the carrier, Pip by the latest place, the name, the stage. */
  _card({ kind, parcel }, today, hass, dark) {
    const name = title(parcel);
    const status = cardStatus(parcel, today, hass);
    const place = placeName(parcel.location);
    const colors = carrierColors(parcel.carrier);
    const tone = dark ? 1 : 0;
    const surface = colors.surface[tone];
    const ink = colors.ink[tone];
    // The place's chip and the dot's ring: the surface lifted toward white, a little in dark, much in light.
    const style = `--pc-surface:${surface};--pc-ink:${ink};--pc-brand:${colors.brand[tone]};`
      + `--pc-chip:color-mix(in srgb, ${surface}, white ${dark ? 10 : 60}%);`
      + `--pc-ring:color-mix(in srgb, ${surface}, white ${dark ? 18 : 80}%)`;
    const label = [name, parcel.carrier, status, place].filter(Boolean).join(', ');
    const art = place
      ? `${pipSvg(pipMood(parcel.status), 1)}<span class="pc-place"><span class="pc-dot"></span>`
        + `<span class="pc-chip">${escapeHtml(place)}</span></span>`
      : pipSvg(pipMood(parcel.status));
    return `<div class="pc${kind === 'attention' ? ' attention' : ''}" role="listitem" style="${style}"`
      + ` aria-label="${escapeHtml(label)}">`
      + `<div class="pc-mark">${truckSvg(parcel.carrier)}<span class="pc-carrier">${escapeHtml(parcel.carrier || '')}</span></div>`
      + `<div class="pc-art" aria-hidden="true">${art}</div>`
      + `<div class="pc-name">${escapeHtml(name)}</div><div class="pc-status">${escapeHtml(status)}</div></div>`;
  }
}

if (!customElements.get('peek-parcels-card')) {
  customElements.define('peek-parcels-card', PeekParcelsCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: 'peek-parcels-card',
    name: STRINGS.en.name,
    description: STRINGS.en.description,
    preview: true,
    documentationURL: 'https://github.com/plhery/peek-ha',
  });
  console.info(`%c PEEK-PARCELS-CARD %c ${VERSION} `, 'background:#f3cf48;color:#171714', '');
}
