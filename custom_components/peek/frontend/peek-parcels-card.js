// The Peek parcels card: the parcels on their way, under the sections of Peek's list, as Peek's Parcels widget shows
// them. It reads the `parcels` attribute of Peek's "On the way" sensor (and of "Delivered today", when asked to), and
// depends on nothing but Home Assistant's frontend.

import { TRUCK_CSS, truckSvg } from './peek-trucks.js';

const VERSION = '0.1.0';
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
    description: 'The parcels on their way, as Peek’s Parcels widget shows them.',
    form: {
      entity: '“On the way” sensor',
      delivered_entity: '“Delivered today” sensor',
      show_delivered: 'Show today’s deliveries',
      max_rows: 'Rows at most',
      title: 'Title',
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
    description: 'Tes colis en route, comme les montre le widget Colis de Peek.',
    form: {
      entity: 'Capteur « En route »',
      delivered_entity: 'Capteur « Livrés aujourd’hui »',
      show_delivered: 'Afficher les livraisons du jour',
      max_rows: 'Lignes au plus',
      title: 'Titre',
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
  ${TRUCK_CSS}
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

/** The stage and the day under a parcel's name. */
export function parcelLine(parcel, today, hass) {
  const words = stringsFor(hass);
  const timeZone = hass?.config?.time_zone;
  const stage = words.stage[parcel.status] || parcel.status_text || '';
  let day;
  if (parcel.status === 'delivered' && parcel.delivered_at) {
    day = parcel.delivered_at.length > 10
      ? new Intl.DateTimeFormat(localeFor(hass), { hour: 'numeric', minute: '2-digit', timeZone })
        .format(new Date(parcel.delivered_at))
      : dayWords(parcel.delivered_at, today, hass);
  } else {
    day = dayWords((parcel.expected_delivery || '').slice(0, 10), today, hass);
  }
  return opening(day ? `${stage} · ${day}` : stage);
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
    this._config = { show_delivered: false, max_rows: DEFAULT_ROWS, ...config };
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

  /** In 50 px units: the padding, the title, then 39 px a row and 22 px a heading or "+N more". */
  getCardSize() {
    const lines = this._lines || [];
    const height = lines.reduce((sum, line) => sum + (line.type === 'row' ? 39 : 22), this._config?.title ? 55 : 30);
    return Math.max(1, Math.ceil(height / 50));
  }

  getGridOptions() {
    return { columns: 6, min_columns: 3 };
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
      this._lines = cardLines(parcels, extra, delivered?.length ? delivered : null, maxRows);
      body = this._lines.length
        ? this._lines.map((line) => this._line(line, today, hass)).join('')
        : `<div class="state">${escapeHtml(words.empty)}</div>`;
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
