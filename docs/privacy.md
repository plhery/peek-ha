# Privacy

- **Between Home Assistant and Peek.** Home Assistant talks to Peek only, at `peektracker.com`. It reads your parcels, and sends what you give the actions. Sign-in passes your browser through my.home-assistant.io, which forwards it to your Home Assistant; the one-time code it carries is useless without the secret (PKCE) that stays in Home Assistant.
- **In Home Assistant.** The sign-in's tokens are kept in Home Assistant's configuration, like every integration's. The sensors' `parcels` attributes are not recorded; the counts are, with long-term statistics. Parcel updates events, with the parcel's name, carrier, stage and latest place, are kept in Home Assistant's history like any event. Diagnostics leave out the tokens and every parcel's id, name, tracking number, shop, wording and place.
- **Assist.** Once a Peek entity is exposed, Assist gets a read-only tool, `peek__list_parcels`. What it returns (names, shops, carriers, stages, expected days and the latest scan's place) goes to the conversation agent you chose, which may be a cloud service.
- **Elsewhere.** The card runs in your browser and draws from Home Assistant's states; it loads nothing from anywhere else.
- **To remove it.** Delete Peek in **Settings › Devices & services**: Home Assistant gives the token back to Peek, which forgets the connection. If Peek can't be reached then, or to cut Home Assistant off from Peek itself, open **Settings › Assistants** in Peek and select **Disconnect** next to Home Assistant. Your parcels stay in Peek.

Peek's own privacy notice: <https://peektracker.com/privacy.html>.
