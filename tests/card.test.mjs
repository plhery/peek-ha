// Tests for the Peek parcels card, with Node's own runner and a stand-in for the browser: `node --test "tests/*.test.mjs"`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

class StubElement {
  constructor() {
    this.shadowRoot = null;
    this.listeners = {};
    this.dispatched = [];
  }

  attachShadow() {
    this.shadowRoot = { innerHTML: '' };
    return this.shadowRoot;
  }

  addEventListener(type, listener) {
    this.listeners[type] = listener;
  }

  dispatchEvent(event) {
    this.dispatched.push(event);
  }
}

const registry = new Map();
globalThis.HTMLElement = StubElement;
globalThis.window = globalThis;
globalThis.document = { documentElement: { lang: 'en' } };
globalThis.customElements = {
  get: (name) => registry.get(name),
  define: (name, element) => registry.set(name, element),
};
globalThis.CustomEvent = class {
  constructor(type, init) {
    this.type = type;
    Object.assign(this, init);
  }
};
const info = console.info;
console.info = () => {};
const { cardLines, cardParcels, cardStatus, dayWords, parcelLine, placeName } = await import(
  '../custom_components/peek/frontend/peek-parcels-card.js'
);
const { pipExtents, pipMood, pipSvg } = await import('../custom_components/peek/frontend/peek-pip.js');
const { carrierColors } = await import('../custom_components/peek/frontend/peek-trucks.js');
console.info = info;
const Card = registry.get('peek-parcels-card');

const TODAY = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Zurich' }).format(new Date());
const day = (offset) => {
  const date = new Date(`${TODAY}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + offset);
  return date.toISOString().slice(0, 10);
};

const parcel = (id, name, carrier, status, section, extra = {}) => ({
  id,
  name,
  carrier,
  status,
  section,
  status_text: 'Scanned at depot',
  expected_delivery: day(2),
  delivered_at: null,
  ...extra,
});

const PARCELS = [
  parcel('a', 'Hiking boots', 'UPS', 'out_for_delivery', 'today', { expected_delivery: TODAY }),
  parcel('b', 'Ceramic bowls', 'La Poste / Colissimo', 'ready_for_pickup', 'attention'),
  parcel('c', 'Winter jacket', 'DHL', 'in_transit', 'active', { expected_delivery: day(1) }),
  parcel('d', null, 'PostNL', 'pending', 'active', { sender: 'Demo Books', expected_delivery: null }),
];

function hass(overrides = {}) {
  return {
    language: 'en',
    locale: { language: 'en' },
    config: { time_zone: 'Europe/Zurich' },
    themes: { darkMode: false },
    entities: {
      'sensor.peek_on_the_way': { entity_id: 'sensor.peek_on_the_way', platform: 'peek', translation_key: 'on_the_way' },
    },
    states: {
      'sensor.peek_on_the_way': { state: String(PARCELS.length), attributes: { parcels: PARCELS } },
      'sensor.peek_delivered_today': {
        state: '1',
        attributes: {
          parcels: [parcel('e', 'USB-C dock', 'Swiss Post', 'delivered', undefined, { delivered_at: `${TODAY}T10:05:09+00:00` })],
        },
      },
    },
    ...overrides,
  };
}

function render(config, state = hass()) {
  const card = new Card();
  card.setConfig(config);
  card.hass = state;
  return card;
}

test('days read as today, tomorrow, else a short date', () => {
  assert.equal(dayWords(TODAY, TODAY, hass()), 'today');
  assert.equal(dayWords(day(1), TODAY, hass()), 'tomorrow');
  assert.equal(dayWords('2026-11-21', '2026-11-17', hass()), 'Sat Nov 21');
  assert.equal(dayWords('2026-11-21', '2026-11-17', hass({ language: 'fr', locale: { language: 'fr' } })), 'sam 21 nov');
  assert.equal(dayWords(null, TODAY, hass()), null);
});

test("a parcel's line: Peek's short stage, then the day or the delivery time", () => {
  assert.equal(parcelLine(PARCELS[0], TODAY, hass()), 'Delivering · today');
  assert.equal(parcelLine(PARCELS[3], TODAY, hass()), 'Added');
  const dock = parcel('e', 'USB-C dock', 'Swiss Post', 'delivered', undefined, { delivered_at: '2026-11-17T10:05:09+00:00' });
  // ICU may put a narrow no-break space before AM.
  assert.equal(parcelLine(dock, '2026-11-17', hass()).replace(/\s/g, ' '), 'Delivered · 11:05 AM');
  const french = hass({ language: 'fr', locale: { language: 'fr' } });
  assert.equal(parcelLine(dock, '2026-11-17', french), 'Livré · 11:05');
  assert.equal(parcelLine({ ...PARCELS[2], status: 'something_new' }, TODAY, hass()), 'Scanned at depot · tomorrow');
});

test("lines follow Peek's sections and stop at the row limit", () => {
  const lines = cardLines(PARCELS, 0, null, 3);
  assert.deepEqual(
    lines.map((line) => (line.type === 'row' ? line.parcel.id : `${line.type}:${line.kind ?? ''}:${line.count}`)),
    ['heading:attention:1', 'b', 'heading:today:1', 'a', 'heading:active:2', 'c', 'more::1'],
  );
  // Parcels beyond the sensor's list count as "on the way", and as more.
  const more = cardLines(PARCELS, 46, null, 30).at(-1);
  assert.deepEqual(more, { type: 'more', count: 46 });
  assert.deepEqual(cardLines([], 0, null, 6), []);
});

test('the card shows the sections, rows, trucks and the rest', () => {
  const card = render({ entity: 'sensor.peek_on_the_way', max_rows: 3, title: 'Parcels' });
  const html = card.shadowRoot.innerHTML;
  assert.match(html, /<h1 class="title">Parcels<\/h1>/);
  assert.ok(html.indexOf('Needs attention') < html.indexOf('Arriving today'));
  assert.ok(html.indexOf('Arriving today') < html.indexOf('On the way'));
  assert.match(html, /Ceramic bowls/);
  assert.match(html, /class="row attention"/);
  assert.match(html, /<svg class="pk-truck"/);
  assert.match(html, /\+1 more/);
  assert.doesNotMatch(html, /Demo Books/);
  // 30 + 25 for the title, 3 headings and "+1 more" at 22, 3 rows at 39: 260 px.
  assert.equal(card.getCardSize(), 6);
  assert.equal(new Card().getCardSize(), 1);
  assert.deepEqual(card.getGridOptions(), { columns: 6, min_columns: 3 });
});

test("today's deliveries, when asked for", () => {
  const html = render({ entity: 'sensor.peek_on_the_way', show_delivered: true, delivered_entity: 'sensor.peek_delivered_today' })
    .shadowRoot.innerHTML;
  assert.match(html, /Delivered today/);
  assert.match(html, /USB-C dock/);
});

test('names are text, never markup', () => {
  const state = hass();
  state.states['sensor.peek_on_the_way'] = {
    state: '1',
    attributes: { parcels: [parcel('x', '<img src=x onerror=alert(1)>', '<b>Carrier</b>', 'in_transit', 'active')] },
  };
  const html = render({ entity: 'sensor.peek_on_the_way' }, state).shadowRoot.innerHTML;
  assert.doesNotMatch(html, /<img/);
  assert.doesNotMatch(html, /<b>/);
  assert.match(html, /&#60;img/);
});

test('empty, unavailable and missing sensors each say so', () => {
  const empty = hass();
  empty.states['sensor.peek_on_the_way'] = { state: '0', attributes: { parcels: [] } };
  assert.match(render({ entity: 'sensor.peek_on_the_way' }, empty).shadowRoot.innerHTML, /Nothing on the way right now/);

  const down = hass();
  down.states['sensor.peek_on_the_way'] = { state: 'unavailable', attributes: {} };
  assert.match(render({ entity: 'sensor.peek_on_the_way' }, down).shadowRoot.innerHTML, /Peek is unavailable/);

  assert.match(render({ entity: 'sensor.nothing' }).shadowRoot.innerHTML, /On the way” sensor/);
});

test('French, and dark themes', () => {
  const state = hass({ language: 'fr', locale: { language: 'fr' }, themes: { darkMode: true } });
  const html = render({ entity: 'sensor.peek_on_the_way', max_rows: 2 }, state).shadowRoot.innerHTML;
  assert.match(html, /À vérifier/);
  assert.match(html, /\+2 autres/);
  assert.match(html, /class="root dark"/);
});

test('the same state is not drawn again', () => {
  const state = hass();
  const card = render({ entity: 'sensor.peek_on_the_way' }, state);
  card.shadowRoot.innerHTML = 'kept';
  card.hass = { ...state };
  assert.equal(card.shadowRoot.innerHTML, 'kept');
});

test('a click opens the sensor', () => {
  const card = render({ entity: 'sensor.peek_on_the_way' });
  card.connectedCallback();
  card.connectedCallback();
  card.listeners.click();
  assert.equal(card.dispatched.length, 1);
  assert.equal(card.dispatched[0].type, 'hass-more-info');
  assert.deepEqual(card.dispatched[0].detail, { entityId: 'sensor.peek_on_the_way' });
});

test('the card picker: a stub that finds the sensors, a form, and a preview', () => {
  assert.deepEqual(Card.getStubConfig(hass()), {
    entity: 'sensor.peek_on_the_way',
    show_delivered: false,
    max_rows: 6,
    delivered_entity: 'sensor.peek_delivered_today',
  });
  // Renamed or French entity ids are found by their translation key.
  const french = {
    entities: { 'sensor.peek_en_route': { entity_id: 'sensor.peek_en_route', platform: 'peek', translation_key: 'on_the_way' } },
    states: {},
  };
  assert.equal(Card.getStubConfig(french).entity, 'sensor.peek_en_route');

  const form = Card.getConfigForm();
  assert.deepEqual(
    form.schema.map((field) => field.name),
    ['entity', 'style', 'show_delivered', 'delivered_entity', 'max_rows', 'title'],
  );
  assert.deepEqual(form.schema[1].selector.select.options, [{ value: 'list', label: 'List' }, { value: 'cards', label: 'Cards' }]);
  assert.equal(form.computeLabel({ name: 'max_rows' }), 'Parcels at most');
  document.documentElement.lang = 'fr';
  assert.equal(form.computeLabel({ name: 'max_rows' }), 'Colis au plus');
  document.documentElement.lang = 'en';

  assert.deepEqual(window.customCards.map((card) => [card.type, card.preview]), [['peek-parcels-card', true]]);
  assert.throws(() => new Card().setConfig(null));
  assert.throws(() => new Card().setConfig({ entity: 'sensor.peek_on_the_way', style: 'tiles' }), /list or cards/);
});

test("the cards' parcels: Peek's sections in order, then today's deliveries, and how many are left", () => {
  const delivered = [parcel('e', 'USB-C dock', 'Swiss Post', 'delivered')];
  const { shown, left } = cardParcels(PARCELS, 2, delivered, 4);
  assert.deepEqual(shown.map(({ kind, parcel: item }) => `${kind}:${item.id}`), ['attention:b', 'today:a', 'active:c', 'active:d']);
  assert.equal(left, 3);
  assert.deepEqual(cardParcels(PARCELS, 0, delivered, 30).shown.at(-1).kind, 'delivered');
  assert.deepEqual(cardParcels([], 0, null, 6), { shown: [], left: 0 });
});

test("a card's status: the stage in full, and its day unless it is out for delivery", () => {
  assert.equal(cardStatus(PARCELS[0], TODAY, hass()), 'Out for delivery');
  assert.equal(cardStatus(PARCELS[1], TODAY, hass()), `Ready for pickup · ${dayWords(day(2), TODAY, hass())}`);
  assert.equal(cardStatus(PARCELS[2], TODAY, hass()), 'In transit · tomorrow');
  assert.equal(cardStatus(PARCELS[3], TODAY, hass()), 'Added to tracking');
  const french = hass({ language: 'fr', locale: { language: 'fr' } });
  assert.equal(cardStatus(PARCELS[2], TODAY, french), 'En transit · demain');
  const dock = parcel('e', 'USB-C dock', 'Swiss Post', 'delivered', undefined, { delivered_at: '2026-11-17T10:05:09+00:00' });
  assert.equal(cardStatus(dock, '2026-11-17', french), 'Livré · 11:05');
  assert.equal(cardStatus({ ...PARCELS[2], status: 'something_new' }, TODAY, hass()), 'Scanned at depot · tomorrow');
});

test("a place is the scan's town, out of capitals", () => {
  assert.equal(placeName('ZURICH-MULLIGEN, CH'), 'Zurich-Mulligen');
  assert.equal(placeName("L'ISLE D'ABEAU CEDEX, FR"), "L'Isle D'Abeau Cedex");
  assert.equal(placeName('Buchs SG'), 'Buchs SG');
  assert.equal(placeName('  , FR'), '');
  assert.equal(placeName(null), '');
});

test('the cards: in the carriers’ colours, with Pip by the place, and the rest counted', () => {
  const state = hass();
  state.states['sensor.peek_on_the_way'].attributes.parcels = [
    { ...PARCELS[0], location: 'BERN, CH' },
    ...PARCELS.slice(1),
  ];
  const card = render({ entity: 'sensor.peek_on_the_way', style: 'cards', max_rows: 3, title: 'Parcels' }, state);
  const html = card.shadowRoot.innerHTML;
  assert.match(html, /<div class="cards" role="list">/);
  assert.equal(html.match(/class="pc[ "]/g).length, 3);
  assert.ok(html.indexOf('Ceramic bowls') < html.indexOf('Hiking boots'));
  assert.match(html, /class="pc attention"/);
  assert.match(html, /<span class="pc-carrier">UPS<\/span>/);
  const ups = carrierColors('UPS');
  assert.ok(html.includes(`--pc-surface:${ups.surface[0]};--pc-ink:${ups.ink[0]};--pc-brand:${ups.brand[0]}`));
  // Out for delivery, Pip hurries toward the place; the parcels without one have him alone.
  assert.match(html, /class="pk-pip pk-pip-eager"[^]*<span class="pc-chip">Bern<\/span>/);
  assert.match(html, /aria-label="Hiking boots, UPS, Out for delivery, Bern"/);
  assert.match(html, /\+1 more/);
  assert.doesNotMatch(html, /Demo Books/);
  // 30 + 25 for the title, two rows of cards at 158 and "+1 more" at 26: 397 px.
  assert.equal(card.getCardSize(), 8);
  assert.deepEqual(card.getGridOptions(), { columns: 12, min_columns: 6 });

  const dark = render({ entity: 'sensor.peek_on_the_way', style: 'cards' }, hass({ themes: { darkMode: true } }));
  const darkHtml = dark.shadowRoot.innerHTML;
  assert.match(darkHtml, /class="root dark"/);
  assert.ok(darkHtml.includes(`--pc-surface:${ups.surface[1]};--pc-ink:${ups.ink[1]}`));

  const empty = hass();
  empty.states['sensor.peek_on_the_way'] = { state: '0', attributes: { parcels: [] } };
  assert.match(render({ entity: 'sensor.peek_on_the_way', style: 'cards' }, empty).shadowRoot.innerHTML, /Nothing on the way/);
});

test("the cards' names and places are text, never markup", () => {
  const state = hass();
  state.states['sensor.peek_on_the_way'] = {
    state: '1',
    attributes: {
      parcels: [parcel('x', '<img src=x onerror=alert(1)>', '<b>Carrier</b>', 'in_transit', 'active', { location: '<i>x</i>' })],
    },
  };
  const html = render({ entity: 'sensor.peek_on_the_way', style: 'cards' }, state).shadowRoot.innerHTML;
  assert.doesNotMatch(html, /<img|<b>|<i>/);
  assert.match(html, /&#60;img/);
});

test("carriers' card colours are Peek's, and a carrier Peek does not know gets its grey", () => {
  // Peek's palette for FedEx (#4d148c) and An Post (#00a76a): src/brand, carrierBrand().
  assert.deepEqual(carrierColors('FedEx'), {
    surface: ['#e6deef', '#272131'], ink: ['#23093f', '#c1add7'], brand: ['#360e62', '#b8a1d1'],
  });
  assert.deepEqual(carrierColors(' an post ').surface, ['#dbf3ea', '#0f2b1e']);
  assert.deepEqual(carrierColors('No such carrier'), carrierColors(undefined));
});

test("Pip's face follows the stage, and his frame what he covers", () => {
  assert.deepEqual(
    ['pending', 'in_transit', 'out_for_delivery', 'customs', 'ready_for_pickup', 'failed_attempt', 'delivered', undefined]
      .map(pipMood),
    ['look', 'look', 'eager', 'wait', 'wait', 'worry', 'joy', 'look'],
  );
  const look = pipSvg('look');
  assert.match(look, /viewBox="52 92 196 204" width="44" height="45.8"/);
  assert.equal(look.match(/<polygon/g).length, 2);
  assert.match(look, /stroke-dasharray="3 3"/);
  // Delivered, his four flaps are open and the tape is gone, with glints around.
  const joy = pipSvg('joy');
  assert.equal(joy.match(/<polygon/g).length, 4);
  assert.doesNotMatch(joy, /stroke-dasharray/);
  assert.equal(joy.match(/scale\(/g).length, 6);
  // Eager, his speed lines trail away from the place.
  assert.match(pipSvg('eager', 1), /M14 170H40/);
  assert.doesNotMatch(pipSvg('eager', 1), /matrix\(-1/);
  assert.match(pipSvg('eager', -1), /matrix\(-1 0 0 1 300 0\)/);
  assert.deepEqual(pipExtents('eager', -1), [52, 76, 300, 296]);
});
