# Development

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
node --test "tests/*.test.mjs"
```

`scripts/build_trucks.mjs` builds `custom_components/peek/frontend/peek-trucks.js`, the carriers' trucks, from Peek's brand data.

The screenshots in `images/` come from a local Home Assistant with synthetic parcels.
