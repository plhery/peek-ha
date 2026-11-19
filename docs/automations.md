# Automation examples

## Tell your phone when a parcel goes out for delivery

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

## Add the tracking numbers from your shipping emails

With the [IMAP integration](https://www.home-assistant.io/integrations/imap/) reading your mailbox:

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

## Say in the morning what arrives today

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

## Archive what was delivered, every evening

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
