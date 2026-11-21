# Actions

## `peek.add_parcels`

Finds the tracking numbers in a text and adds each one to Peek. A number Peek already follows is left as it is. It returns each number's outcome.

| Field | |
| --- | --- |
| `text` | Required. Any text with tracking numbers in it: an order email, a message. |
| `name` | Optional. The name to give the parcels, such as the shop's. |

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

## Editing a parcel

The five actions below need Home Assistant to be allowed to edit your parcels. A Peek connected before version 0.2.0 may only see and add them: the first edit then fails with "Home Assistant may not edit or archive your parcels in Peek yet" and asks you to sign in to Peek again, once (**Reconfigure** next to Peek in **Settings › Devices & services**). Everything else keeps working meanwhile.

Each one names the parcel by its `id` or its tracking number, and reads Peek again once the change is made. They return nothing.

### `peek.archive_parcel`

Moves a parcel to the archive. `peek.restore_parcel` brings it back.

```yaml
action: peek.archive_parcel
data:
  parcel: 1Z4E7W960398127345
```

### `peek.restore_parcel`

Brings an archived parcel back to the list of deliveries. `peek.get_parcels` with `status: archived` lists them.

```yaml
action: peek.restore_parcel
data:
  parcel: "46523910834"
```

### `peek.rename_parcel`

Gives a parcel the name Peek lists it by.

| Field | |
| --- | --- |
| `parcel` | Required. |
| `name` | Required. At most 80 characters; `""` clears the name. |

```yaml
action: peek.rename_parcel
data:
  parcel: 1Z4E7W960398127345
  name: Hiking boots
```

### `peek.change_carrier`

Sets the carrier that delivers a parcel, when Peek has the wrong one. Peek checks the parcel with it at once.

| Field | |
| --- | --- |
| `parcel` | Required. |
| `carrier` | Required. Peek's id for the carrier, such as `dhl`, `ups`, `la-poste` (La Poste / Colissimo) or `dpd-de` (DPD Germany). [Peek's carrier catalog](https://peektracker.com/api/carriers) lists every id with its `displayName`. |
| `postcode` | Optional. The delivery postcode, for a carrier that asks for it. Without it, the parcel keeps the postcode it has; `""` removes it. |

```yaml
action: peek.change_carrier
data:
  parcel: "01505024382917"
  carrier: dpd-de
  postcode: "10115"
```

### `peek.set_parcel_notifications`

Turns Peek's notifications about one parcel off or back on, for when an automation tells you instead. Peek's emails about it stay as they are.

| Field | |
| --- | --- |
| `parcel` | Required. |
| `notifications` | Required. `true` for Peek's notifications about this parcel, `false` for none. |

```yaml
action: peek.set_parcel_notifications
data:
  parcel: 1Z4E7W960398127345
  notifications: false
```

## `peek.get_parcels`

Reads the parcels that match from Peek now, and returns them.

| Field | |
| --- | --- |
| `status` | `active` (the default), `attention`, `today`, `week`, `delivered`, `archived` or `all`. |
| `sort` | `expected`, `delivered`, `updated` or `added`. |
| `search` | Looks in names, shops, carriers, tracking numbers and scans. |
| `limit` | 1 to 50, 20 unless given. |

```yaml
action: peek.get_parcels
data:
  status: delivered
  sort: delivered
  limit: 1
response_variable: latest
```
