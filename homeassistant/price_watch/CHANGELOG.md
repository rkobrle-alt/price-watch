# Changelog

## 0.17.0

- Discover Parkside catalog candidates from the published Lidl sitemap.
- Refresh one durable, fairly ordered product batch per cycle.
- Store catalog membership and exact observation history in SQLite.
- Migrate valid catalog schema version 1 databases transactionally to version 2.
- Preserve the existing explicit URL and JSON persistence mode.
## 0.14.0

- Publish cycle health as `sensor.price_watch_status`.
- Publish exact monetary product sensor states after completed cycles.
- Continue monitoring when status publication alone fails.
## 0.13.1

- Use the verified SMTP-backed Home Assistant notify entity by default.
- Preserve configurable notification delivery for other installations.

## 0.13.0

- Add continuous Lidl Parkside monitoring.
- Persist comparison state in Supervisor-managed App storage.
- Deliver notifications through a configurable Home Assistant notify entity.
