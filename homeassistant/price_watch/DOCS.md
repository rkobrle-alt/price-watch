# Price Watch Home Assistant App

## Catalog mode

New installations enable `catalog_enabled`. Price Watch reads only the
robots-advertised Lidl Czech Republic product sitemap, discovers Parkside and
Parkside Performance candidates and refreshes one bounded product batch per
cycle.

`catalog_batch_size` controls the maximum number of product pages in one cycle.
Never-refreshed products are selected first; later selection starts with the
oldest recorded refresh attempt. This order is durable across App restarts.
The first cycle performs sitemap discovery. Later discovery occurs every
`catalog_discovery_interval_cycles` cycles.

Catalog mode includes tools, garden equipment, batteries, chargers,
accessories and spare parts whose canonical Lidl URL is a Parkside candidate.
The product page remains authoritative for the actual brand and product data.

## Explicit mode

Existing installations without `catalog_enabled` continue to monitor their
configured `product_urls`. To select explicit mode intentionally, set
`catalog_enabled` to false and provide one or more Lidl Czech Republic Parkside
product page URLs. Catalog-only batch options are not used in this mode.

## Notifications and scheduling

The default notification entity is
`notify.gmail_parkside_kobrle_fomei_com`, matching the existing SMTP
integration. Change it if Home Assistant exposes another notify entity.

`interval_seconds` controls the fixed delay after every completed cycle. The
first cycle starts immediately. `price_drop_percentage` and
`price_drop_amount` remain optional exact decimal strings. Catalog mode
defaults to 20 percent and requires the product to be available. It prefers a
provider original price and otherwise compares with the highest prior price in
the same currency. The same product, rule type, currency and current price is
reserved durably and does not produce another email.

In catalog mode, `daily_digest_enabled` optionally sends one summary per
Europe/Prague calendar date. `daily_digest_time` uses exact 24-hour `HH:MM`
local time and defaults to `08:00`. The first completed cycle at or after that
time sends the digest. Later cycles and App restarts on the same date do not
repeat it. The digest uses `price_drop_percentage`, includes only available
products with an approved reference price, and sends an explicit empty summary
when none qualify.

`individual_notifications_enabled` controls immediate per-product price-drop
and back-in-stock messages in catalog mode. It defaults to `true` when omitted
so existing option documents remain compatible. New packaged installations
set it to `false`, leaving the daily digest as the only email. Disabling it
does not disable discovery, refresh, history, discount calculations or status
entities.

## Persistence

Catalog mode stores membership, refresh ordering, complete append-only
observations, notification reservations and daily digest reservations in
`/data/catalog.sqlite3`.
Explicit mode stores its latest
snapshots in `/data/state.json`. Supervisor preserves both App-owned paths
across restarts and upgrades.

A valid schema-version-1 catalog database is migrated transactionally through
versions 2, 3 and 4. Valid version-2 and version-3 databases continue through
the remaining migrations. Price Watch performs no automatic history deletion.

SQLite reservation and Home Assistant SMTP delivery cannot share one atomic
transaction. Ordinary reported delivery failures release the reservation for
retry. A hard process stop after reservation but before delivery can suppress
that one message; this trade-off prevents repeated email after a successful
delivery followed by a state-write failure.

## Security

The App requests Home Assistant Core API access only. Supervisor injects the
API token at runtime. The token and SMTP credentials are not App options and
are never stored by Price Watch. The App adds no ingress, exposed port or host
access.

Version 0.27.0 additionally maps Home Assistant's shared directory writable.
Price Watch uses only `/share/price-watch-migration`, and only after an
explicit export command or a fully confirmed import configuration. It does not
scan the directory for automatic imports.

Version 0.27.1 selects the exported state from the configured monitoring mode.
An inactive state artifact left by an earlier mode transition is ignored and
is never read, exported, modified or deleted.

## Managed repository installation and migration

For a new installation, add this repository URL in the Home Assistant App
store and install Price Watch:

```text
https://github.com/rkobrle-alt/price-watch
```

Home Assistant gives a local App and a GitHub-repository App different full
slugs and different persistent `/data` directories. Adding the repository does
not convert `local_price_watch` in place. Use the following hand-off for an
existing installation.

1. Update the local App to 0.27.1 and create a Home Assistant full or partial
   backup containing `local_price_watch`.
2. In Developer Tools, call `hassio.addon_stdin` with:

   ```yaml
   addon: local_price_watch
   input: >-
     {"command":"export_migration","confirmation":"EXPORT_MIGRATION"}
   ```

3. Wait for `migration export complete` in the App log. Record the complete
   filename and SHA-256. The ZIP is in `/share/price-watch-migration`; keep an
   independent copy and inspect its `options.json`.
4. Stop, but do not uninstall, `local_price_watch`.
5. Add the repository URL above, reload the App store, install the repository
   Price Watch App and copy the exported operational settings into its
   configuration.
6. Add these three values exactly, using the filename rather than a path:

   ```yaml
   migration_import_file: price-watch-migration-YYYYMMDDTHHMMSSffffffZ.zip
   migration_import_sha256: <64 lowercase hexadecimal characters from the log>
   migration_import_confirmation: IMPORT_MIGRATION
   ```

7. Start the repository App. Import finishes before its first monitoring
   cycle. Verify an import-success log, a normal catalog cycle, the previous
   observation count in `sensor.price_watch_storage`, catalog counts and the
   next daily digest. Repeated starts with the same values are safe.
8. Remove all three `migration_import_*` settings after the successful import
   and first-cycle verification, then restart the repository App. The imported
   state remains in its `/data` directory and subsequent starts no longer
   depend on the shared migration bundle.
9. Update dashboard scripts using `hassio.addon_stdin` to the full App slug
   displayed for the repository installation. Sensor entity IDs do not
   change.
10. Keep the stopped local App and backup through an acceptance period. Remove
   them only after the managed installation is confirmed healthy.

The import refuses a path, incorrect checksum, different options, damaged
state, unexpected archive content or any unrelated existing state. It never
overwrites `options.json`. To roll back, stop the repository App and restart
the unchanged local App. Do not run both installations simultaneously because
they publish the same sensor states and may send duplicate mail.

## Operation

Start the App and inspect its log for catalog or explicit cycle summaries.
Temporary sitemap failures are reported but do not prevent refresh of already
known catalog entries. Provider page failures are isolated within the selected
batch. Persistence, rule and notification failures stop the process visibly.

After each completed cycle, the App updates `sensor.price_watch_status` and a
monetary sensor for every successfully refreshed product. Product entity IDs
use `sensor.price_watch_product_<product UUID hex>` and remain stable for the
same Lidl product.

Catalog mode also updates one aggregate `sensor.price_watch_catalog`. Its state
is `ok` when the current cycle has no catalog or provider errors and `degraded`
otherwise. Its attributes show the total retained catalog references, observed
products, currently available products, products meeting the configured
percentage discount, the exact percentage threshold, and the durable times of
the last successful discovery and refresh attempt. This single summary can be
added to a dashboard without adding every product sensor.

For a more useful dashboard overview, catalog mode also publishes:

- `sensor.price_watch_discounted_products`, whose numeric state is the number
  of currently available products meeting the configured percentage discount;
- `sensor.price_watch_catalog_errors`, whose numeric state is the current
  provider plus catalog error count;
- `sensor.price_watch_last_checked`, whose timestamp state is the latest
  completed catalog-cycle time.

The discounted-products attributes include retained, observed and available
counts together with successfully delivered and durably suppressed individual
alert counts. The established `sensor.price_watch_catalog` state remains
`ok/degraded` for backward compatibility.

If percentage monitoring is disabled in favor of a fixed price amount, the
percentage threshold is unavailable and the qualifying percentage count is
zero.

## Storage diagnostics and backup

Catalog mode publishes `sensor.price_watch_storage`. Its state is `ok` after a
successful read and `warning` when Price Watch reports a catalog persistence
failure before stopping. Attributes contain the total observation count,
distinct observed-product count, first and last inserted observation times and
allocated SQLite bytes. The values are diagnostics only: Price Watch performs
no automatic deletion, compaction or vacuum. The
`reclaimable_size_bytes` attribute reports allocated free pages which SQLite
can reuse after explicit retention; it does not imply that the file shrank.

The catalog database remains `/data/catalog.sqlite3`. Include the Price Watch
App in a Home Assistant full or partial backup before maintenance or a future
retention migration. Restore it through the Home Assistant backup workflow;
do not replace the database while the App is running. Version 0.23.0 does not
execute maintenance backups itself and does not change schema version 4.

Version 0.24.0 provides a separate CLI `maintenance` command for operators who
have deliberately stopped every writer and can access the catalog database.
Without `--apply` it only previews removable and protected counts. Apply
requires a distinct new backup file and preserves the latest state and
historical-high price for every product and currency. The Home Assistant App
never invokes this command, exposes no deletion option and performs no
automatic vacuum. Do not run retention directly against `/data/catalog.sqlite3`
while the App is running.

To see the impact of a retention window without changing the database, add a
positive optional `retention_preview_days` value in the App configuration and
restart the App. After a successful catalog cycle,
`sensor.price_watch_maintenance` uses the removable observation count as its
state and reports the exact cutoff, total, retained and protected counts as
attributes. With version 0.26.0 the sensor reports `apply_available: true`.
Omitting the option preserves the previous behavior and does not create the
sensor or enable an apply command.

Normal monitoring invokes only the read-only planner. It never schedules
retention, creates a maintenance backup, deletes observations or vacuums
SQLite. To apply a reviewed non-zero plan from Home Assistant, create a script
with this action:

```yaml
sequence:
  - action: hassio.addon_stdin
    data:
      addon: local_price_watch
      input: >-
        {"command":"apply_retention","confirmation":"APPLY_RETENTION","expected_removable_observation_count":{{ states('sensor.price_watch_maintenance') | int(-1) }}}
mode: single
```

Expose that script on the dashboard only after reviewing the maintenance
sensor. Calling it sends the displayed removable count once. The App obtains a
fresh plan while holding the same lock as catalog synchronization. If the
count changed, the command is rejected without creating a backup or deleting
anything. A matching zero count is a successful no-op. A matching positive
count creates a unique complete database backup below
`/data/retention-backups` before applying the existing retention policy. The
sensor is refreshed after each accepted outcome.

The confirmation text is intentionally exact and case-sensitive. Do not build
an automation or schedule around this script. Retention removes historical
observations selected by the documented policy; restoring them requires the
generated App-data backup or a Home Assistant backup. The operation preserves
the latest observation and historical-high price observations for each product
and currency, and does not delete catalog references or notification
reservations. The separate stopped-App CLI maintenance flow remains available.

The REST-created product states are not entity-registry-backed. To test email
delivery independently, call `notify.send_message` for the configured notify
entity in Home Assistant Developer Tools.
