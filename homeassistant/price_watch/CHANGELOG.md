# Changelog

## 0.29.0

- Read the current Lidl Czech Republic daily marketing offer from the public
  storefront home page.
- Include the offer text and its validated Lidl link in the single daily
  discount digest.
- Retry the digest after a temporary or malformed promotion response instead
  of sending an incomplete summary.

## 0.28.0

- Treat a Home Assistant Supervisor stop as a graceful process shutdown.
- Preserve completed-cycle diagnostics and exit successfully on `SIGTERM`.
- Keep Ctrl+C and all established configuration and operational error codes.
- Document stop, restart and durable-state production acceptance checks.

## 0.27.1

- Selects the migration export state from the configured monitoring mode.
- Safely ignores an inactive legacy state artifact left by an earlier mode
  transition without reading, exporting, modifying or deleting it.

## 0.27.0

- Add managed Home Assistant repository installation and update guidance.
- Add a serialized, read-only migration export to the shared directory.
- Add explicit checksum-protected state import before the first managed-App
  monitoring cycle.
- Preserve catalog history, alert reservations and daily-digest reservations
  across the local-to-repository identity hand-off.
- Retain the stopped local App as the immediate migration rollback path.

## 0.26.0

- Add an explicit Supervisor-stdin action for a reviewed retention preview.
- Replan and reject stale removable counts before every possible mutation.
- Serialize maintenance with monitoring and back up persistent data first.
- Republish the maintenance sensor after every accepted command.
- Keep retention unscheduled and preserve schema version 4 without vacuum.

## 0.25.0

- Add an opt-in read-only retention preview for catalog installations.
- Publish exact plan counts through `sensor.price_watch_maintenance`.
- Keep retention apply, backup creation, deletion and vacuum outside the App.
- Preserve existing installations when the optional window is omitted.

## 0.24.0

- Add previewable, manually invoked SQLite observation retention.
- Require a complete new backup before every explicit apply operation.
- Preserve recent rows, latest product state and historical-high price rows.
- Report reclaimable SQLite bytes without automatic vacuum or App deletion.

## 0.23.0

- Add read-only SQLite observation counts and allocated-size diagnostics.
- Publish storage health through `sensor.price_watch_storage`.
- Attempt a warning state before propagating catalog persistence failures.
- Preserve schema version 4 and all retained history without compaction.

## 0.22.0

- Add a backward-compatible catalog option for individual notifications.
- Disable individual product email in new packaged installations.
- Keep one daily digest with all current qualifying discounts and URLs.
- Preserve catalog monitoring, history, status and existing option behavior.

## 0.21.0

- Publish a numeric count of currently qualifying discounted Parkside products.
- Publish current catalog/provider error count and latest completed check time.
- Expose delivered and suppressed individual-alert diagnostics.
- Preserve the existing `sensor.price_watch_catalog` health state contract.

## 0.20.0

- Publish one aggregate `sensor.price_watch_catalog` health representation.
- Report retained, observed, available and qualifying-discount product counts.
- Expose durable last discovery and refresh-attempt timestamps.
- Preserve fixed-amount-only catalog configurations and explicit mode.

## 0.19.1

- Treat Lidl schema.org `OnlineOnly` offers as available products.

## 0.19.0

- Add an optional daily digest of currently available qualifying discounts.
- Use Europe/Prague calendar time with a configurable `HH:MM` delivery time.
- Persist one digest reservation per local date in SQLite schema version 4.
- Include an explicit empty digest when no product currently qualifies.
- Package official IANA timezone data for consistent daylight-saving behavior.

## 0.18.0

- Compare catalog prices with provider original prices or historical highs.
- Default catalog price-drop alerts to 20 percent and available products.
- Persist logical-price notification reservations in SQLite.
- Suppress repeated email for an unchanged qualifying product price.
- Migrate valid SQLite schema versions 1 and 2 to version 3.

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
