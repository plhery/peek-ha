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

## `peek.archive_parcel`

Moves a parcel to the archive. You can restore it in Peek.

| Field | |
| --- | --- |
| `parcel` | Required. The parcel's `id` or its tracking number. |

```yaml
action: peek.archive_parcel
data:
  parcel: 1Z4E7W960398127345
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
