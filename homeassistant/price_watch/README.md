# Price Watch

Price Watch automatically discovers Lidl Czech Republic Parkside catalog
candidates, refreshes products in durable bounded batches and delegates
notifications to a Home Assistant notify entity.
Available products at least 20 percent below their approved reference price
produce one durable logical-price alert.

New installations also send one daily discount digest at 08:00
Europe/Prague. Existing installations remain opted out until
`daily_digest_enabled` is configured.

Existing explicit product URL monitoring remains supported. See `DOCS.md` for
catalog, compatibility, persistence and operation details.
