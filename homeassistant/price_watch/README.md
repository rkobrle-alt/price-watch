# Price Watch

Price Watch automatically discovers Lidl Czech Republic Parkside catalog
candidates, refreshes products in durable bounded batches and delegates
notifications to a Home Assistant notify entity.
Available products at least 20 percent below their approved reference price
are included in the daily summary.

New installations send one daily discount digest at 08:00 Europe/Prague and
disable separate per-product email. Existing installations retain their
current behavior until `daily_digest_enabled` and
`individual_notifications_enabled` are configured.

Existing explicit product URL monitoring remains supported. See `DOCS.md` for
catalog, compatibility, persistence and operation details.
