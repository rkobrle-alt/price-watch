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
The digest includes the current yellow Lidl Czech Republic daily offer and a
validated Lidl link when the storefront publishes one.

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

Version 0.27.0 supports installation and later updates through the Price Watch
GitHub App repository. Existing `local_price_watch` users must use the
documented checksummed export/import hand-off because Home Assistant assigns
the repository installation a separate persistent App identity. The local App
is retained, stopped, until the migrated installation has been verified.

Version 0.28.0 handles a Home Assistant Supervisor stop as a successful,
prompt shutdown. Restart continues from the same persistent catalog and
notification-reservation state.

Version 0.29.0 adds the current Lidl Czech Republic daily offer to the daily
discount digest. A temporary offer retrieval failure is retried on a later
cycle without interrupting product monitoring.

Version 0.30.0 adds durable operational health and daily-digest diagnostics.
One or two consecutive failed cycles are degraded; the third is failed and
sends one operational alert. A later healthy cycle sends one recovery message.
