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

Catalog installations also publish non-destructive SQLite observation counts,
boundary timestamps and allocated size through
`sensor.price_watch_storage`.
Version 0.24.0 additionally reports reusable SQLite bytes after an explicitly
invoked external maintenance operation. Normal App cycles never delete or
compact history.

Version 0.25.0 can optionally publish a read-only retention plan through
`sensor.price_watch_maintenance`. Version 0.26.0 adds an explicit, confirmed
Home Assistant action for applying exactly the reviewed removable count after
a fresh validation and persistent backup. See `DOCS.md` before enabling the
action. Retention is never automatic and no vacuum is performed.
