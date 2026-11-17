<img src="custom_components/peek/brand/icon.png" alt="Peek" width="96" height="96">

# Peek for Home Assistant

[Peek](https://peektracker.com) follows your parcels, from every carrier, in one list. This integration brings that list into Home Assistant:

- sensors for the parcels on their way, those arriving today, those that need you, today's deliveries and the next delivery day;
- a **Deliveries** calendar;
- a **Parcel updates** event each time a parcel is added, moves on, goes out for delivery, needs you or is delivered;
- actions to add parcels from a text (an order email, say), archive one, or read the list;
- a dashboard card that looks like Peek's Parcels widget;
- a tool Assist can use to answer "what arrives today?".

It needs Home Assistant 2026.10 or later.

## Install

**From the Marketplace** (Home Assistant 2026.11 and later): open **Settings › Marketplace**, search for **Peek**, download it and restart Home Assistant.

**As a custom repository**, before Peek is in the catalog: in the Marketplace, add `https://github.com/plhery/peek-ha` as a custom repository of the **Integration** type, then download it and restart. Adding a custom repository needs the Marketplace's GitHub connection. On Home Assistant 2026.10, do the same in HACS.

**By hand**: copy `custom_components/peek` into your configuration's `custom_components` folder and restart.

## Set up

1. Go to **Settings › Devices & services › Add integration** and choose **Peek**.
2. Your browser opens Peek. Sign in, check what Home Assistant asks for (to see your parcels, and to add and archive them) and select **Allow**.
3. Peek sends you back through [My Home Assistant](https://my.home-assistant.io), which returns you to your Home Assistant. The first time, My Home Assistant asks for your Home Assistant's address.

There is nothing to type in Home Assistant: no client id, no secret, no Application Credentials. One Peek account can be connected to each Home Assistant. When Peek refuses the connection (because you disconnected Home Assistant in Peek, for example), **Settings › Devices & services** says "Authentication expired for Peek"; reconfiguring it starts the same sign-in.

Peek's connections for assistants are experimental. If Peek says it can't connect assistants to your account, the integration can't be set up yet.

## Entities

The entity ids below are the English ones; in another language they follow your language's names.

| Entity | What it shows |
| --- | --- |
| `sensor.peek_on_the_way` | Every parcel on its way. Its `parcels` attribute lists them (50 at most), each with its `section`: `attention`, `today` or `active`, as in Peek's list. |
| `sensor.peek_arriving_today` | Parcels out for delivery or expected today, unless they need you. |
| `sensor.peek_needs_attention` | Parcels that need you: waiting at a pickup point, a missed delivery, customs. |
| `sensor.peek_delivered_today` | Parcels delivered today, still in the list (not archived). Its `parcels` attribute lists them. |
| `sensor.peek_next_delivery` | The next day a parcel is expected, today or later. Its `parcels` attribute lists the parcels expected that day. |
| `calendar.peek_deliveries` | All-day events: each parcel on its way on its expected day, each delivery on the day it came. |
| `event.peek_parcel_updates` | One event per change; see below. |

"Today" is the day in Home Assistant's time zone. The counts keep long-term statistics; the `parcels` attributes are left out of the recorder.

Home Assistant reads Peek every 30 minutes, and every 10 minutes on a day a parcel is out for delivery or expected. It reads again right after an action adds or archives a parcel. To read on demand, call `homeassistant.update_entity` on any Peek entity.

### Parcel updates

`event.peek_parcel_updates` fires one of these event types: `added`, `status_changed`, `out_for_delivery`, `delivered`, `needs_attention` and `expected_delivery_changed`. Its attributes describe the parcel: `id`, `name` (the shop's when the parcel has none), `carrier`, `status`, `status_text`, `needs_attention`, `expected_delivery` and `location` (the latest scan's place).

The first read after Home Assistant starts sets what the next reads are compared with, so it fires nothing. A change that happens while Peek can't be read fires once the next read works.

## Actions

### `peek.add_parcels`

Finds the tracking numbers in a text and adds each one to Peek. A number Peek already follows is left as it is. It returns each number's outcome.

```yaml
action: peek.add_parcels
data:
  text: "Your order is on its way with UPS. Tracking number: 1Z4E7W960398127345"
  name: Fjord Outdoor
response_variable: added
```

```yaml
parcels:
  - tracking_number: 1Z4E7W960398127345
    carrier: UPS
    outcome: added
    id: 0ca5a2d0-b0f2-45ef-97b1-0f542ef30b98
```

Send only the shipping part when you can: Peek keeps the tracking numbers and the name, nothing else. It adds at most 10 numbers a call.

### `peek.archive_parcel`

Moves a parcel to the archive, by its `id` or tracking number. You can restore it in Peek.

```yaml
action: peek.archive_parcel
data:
  parcel: 1Z4E7W960398127345
```

### `peek.get_parcels`

Reads the parcels that match from Peek now, and returns them. `status` is `active` (the default), `attention`, `today`, `week`, `delivered`, `archived` or `all`. `sort` is `expected`, `delivered`, `updated` or `added`. `search` looks in names, shops, carriers, tracking numbers and scans. `limit` is 1 to 50, 20 unless given.

```yaml
action: peek.get_parcels
data:
  status: delivered
  sort: delivered
  limit: 1
response_variable: latest
```

## Automation examples

Tell your phone when a parcel goes out for delivery:

```yaml
triggers:
  - trigger: state
    entity_id: event.peek_parcel_updates
    not_from: [unavailable, unknown]
conditions:
  - condition: template
    value_template: "{{ trigger.to_state.attributes.event_type == 'out_for_delivery' }}"
actions:
  - action: notify.mobile_app_your_phone
    data:
      message: >-
        {{ trigger.to_state.attributes.name or trigger.to_state.attributes.carrier }}
        is out for delivery.
```

Add the tracking numbers from your shipping emails, read with the [IMAP integration](https://www.home-assistant.io/integrations/imap/):

```yaml
triggers:
  - trigger: event
    event_type: imap_content
    event_data:
      initial: true
conditions:
  - condition: template
    value_template: "{{ 'shipped' in trigger.event.data.subject | lower }}"
actions:
  - action: peek.add_parcels
    data:
      text: "{{ trigger.event.data.text }}"
```

Say in the morning what arrives today:

```yaml
triggers:
  - trigger: time
    at: "07:30:00"
conditions:
  - condition: numeric_state
    entity_id: sensor.peek_arriving_today
    above: 0
actions:
  - action: notify.mobile_app_your_phone
    data:
      message: >-
        Arriving today:
        {{ state_attr('sensor.peek_on_the_way', 'parcels')
           | selectattr('section', 'eq', 'today')
           | map(attribute='name') | reject('none') | join(', ') }}
```

Archive what was delivered, every evening:

```yaml
triggers:
  - trigger: time
    at: "22:00:00"
actions:
  - repeat:
      for_each: "{{ state_attr('sensor.peek_delivered_today', 'parcels') | map(attribute='id') | list }}"
      sequence:
        - action: peek.archive_parcel
          data:
            parcel: "{{ repeat.item }}"
```

## The card

The integration serves its card and loads it on every dashboard: there is no resource to add. In a dashboard, add a card and pick **Peek parcels**, or write it in YAML:

```yaml
type: custom:peek-parcels-card
entity: sensor.peek_on_the_way
show_delivered: true
delivered_entity: sensor.peek_delivered_today
max_rows: 6
title: Parcels
```

It shows the parcels under Peek's sections (needs attention, arriving today, on the way), each with its carrier's truck, its stage and its day, then "+N more" past `max_rows`. It follows your theme, light or dark, and your language (English or French). Selecting it opens the "On the way" sensor. Set `--peek-attention-color` in a theme to change the colour of parcels that need you.

## Assist

Once one of Peek's entities is exposed to Assist (**Settings › Voice assistants › Expose**), Assist gets a read-only tool, `peek__list_parcels`, so you can ask "what arrives today?" or "where's my parcel from Fjord Outdoor?". It never adds or archives parcels.

What the tool returns (names, shops, carriers, stages, expected days and the latest scan's place) goes to the conversation agent you chose, which may be a cloud service.

## Privacy

- **Between Home Assistant and Peek.** Home Assistant talks to Peek only, at `peektracker.com`. It reads your parcels, and sends what you give the actions. Sign-in passes your browser through my.home-assistant.io, which forwards it to your Home Assistant; the one-time code it carries is useless without the secret (PKCE) that stays in Home Assistant.
- **In Home Assistant.** The sign-in's tokens are kept in Home Assistant's configuration, like every integration's. The sensors' `parcels` attributes are not recorded; the counts are. Parcel updates events, with the parcel's name, carrier, stage and latest place, are kept in Home Assistant's history like any event. Diagnostics leave out the tokens and every parcel's id, name, tracking number, shop, wording and place.
- **Elsewhere.** The card runs in your browser and draws from Home Assistant's states; it loads nothing from anywhere else. Assist's tool output goes to your conversation agent (see above).
- **To remove it.** Delete Peek in **Settings › Devices & services**: Home Assistant gives the token back to Peek, which forgets the connection. If Peek can't be reached then, or to cut Home Assistant off from Peek itself, open **Settings › Assistants** in Peek and select **Disconnect** next to Home Assistant. Your parcels stay in Peek.

## Development

For a local Peek, point the integration at it in `configuration.yaml`:

```yaml
peek:
  url: http://127.0.0.1:3418
  # Only when the client document is somewhere else:
  # client_id: http://127.0.0.1:3418/oauth/clients/home-assistant.json
```

Home Assistant logs a warning while this is set. A connection belongs to the address it was signed in at: after changing `url`, Home Assistant asks you to sign in again.

Tests use only synthetic parcels and mocked HTTP:

```sh
pip install -r requirements_test.txt
pytest --cov
node --test tests/
```

`scripts/build_trucks.mjs` builds `frontend/peek-trucks.js`, the carriers' trucks, from Peek's brand data.

## License

[Apache License 2.0](LICENSE)
