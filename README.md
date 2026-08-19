# Price Watch Platform

Price Watch monitors products, compares their durable previous state, evaluates
price and availability rules and delivers notifications.

The platform follows Clean Architecture. Core remains independent of providers,
persistence, notification delivery, CLI and Home Assistant.

## Command-Line Usage

Show the version:

```text
python -m applications.cli version
```

Run one Lidl Parkside synchronization cycle:

```text
python -m applications.cli sync \
    --state-file data/price-watch-state.json \
    --url https://www.lidl.cz/example-product/p100000000
```

Monitor more products by repeating `--url`.

Optional price thresholds:

```text
--price-drop-percentage 10
--price-drop-amount 500.00
```

The first observation establishes the baseline. A later run uses the JSON
state file to detect a price decrease or an unavailable-to-available
transition.

Run the same workflow repeatedly, with the first cycle starting immediately:

```text
python -m applications.cli watch \
    --state-file data/price-watch-state.json \
    --url https://www.lidl.cz/example-product/p100000000 \
    --interval-seconds 300
```

Use `--max-cycles` for a finite run. Otherwise `watch` continues until Ctrl+C.

The same settings may be stored in a strict TOML file:

```toml
schema_version = 1

[provider.lidl]
product_urls = ["https://www.lidl.cz/example-product/p100000000"]
timeout_seconds = 10

[state]
file = "data/price-watch-state.json"

[rules.price_drop]
percentage = "10.00"

[scheduler]
interval_seconds = 300
```

Run it with `python -m applications.cli watch --config price-watch.toml`.
Relative state paths are interpreted from the configuration file directory.

Preview manual retention for a catalog SQLite database:

```text
python -m applications.cli maintenance \
    --database-file data/catalog.sqlite3 \
    --retention-days 90
```

Planning is read-only. Applying retention additionally requires both
`--apply` and a distinct, non-existing `--backup-file`. The backup contains the
complete pre-deletion database. Retention preserves recent observations, the
latest state of every product and every product/currency historical-high price.
Stop any process writing the database before applying maintenance.

Price Watch is also packaged as a Home Assistant App. Its catalog mode
automatically discovers Parkside candidates from the published Lidl sitemap
and refreshes a durable, bounded product batch every cycle. Catalog membership,
refresh order and exact observations are retained in SQLite. Existing App
option documents without `catalog_enabled` keep explicit URL monitoring and
JSON state. Actionable messages are delegated to an existing notify entity,
including the SMTP-backed `notify.gmail_parkside_kobrle_fomei_com`; Price Watch
stores neither its Supervisor token nor SMTP credentials. Completed cycles also
publish Home Assistant status and monetary product sensor states. The CLI
continues to use explicit URLs and console delivery.

Catalog installations additionally publish one aggregate catalog-health state
with retained, observed, available and qualifying-discount counts plus durable
last discovery and refresh-attempt times.

They also publish dashboard-ready states for the current qualifying-discount
count, current catalog/provider error count and latest completed check time.
The existing aggregate health state remains `ok` or `degraded`.

Catalog mode uses a 20-percent default alert threshold. A provider original
price is preferred as the reference; otherwise the highest prior
same-currency observation is used. Durable SQLite reservations prevent an
unchanged qualifying product price from repeatedly sending email.

New Home Assistant installations also enable one daily Parkside discount
digest at 08:00 Europe/Prague. It summarizes the latest available products
meeting the configured percentage, including an explicit empty result. A
durable local-date reservation prevents repeated daily email after later
cycles or App restart. Existing option documents remain opted out until
`daily_digest_enabled` is added.

The digest also includes the current yellow Lidl Czech Republic daily offer
and its validated Lidl link. A temporary retrieval or parsing failure delays
the digest for retry on a later monitoring cycle, while product monitoring
continues normally.

From version 0.31.0, the same daily email separates products newly entering
the qualifying discount set from discounts retained from the preceding
delivered baseline. The first digest after upgrade establishes that durable
baseline without marking every existing discount as new. A product which
leaves the set and later returns is highlighted as new again.

Catalog mode durably distinguishes a transient problem from a sustained
three-cycle incident. Home Assistant receives separate health and daily-digest
diagnostic sensors. A sustained failure produces one retryable operational
email, and a later healthy cycle produces one recovery email after the
incident alert was successfully delivered.

New packaged installations disable individual product notifications and send
qualifying discounts together in that one daily digest. Existing option
documents retain individual alerts unless
`individual_notifications_enabled: false` is configured. Monitoring, history
and dashboard states continue in either mode.

Catalog installations publish `sensor.price_watch_storage` with the exact
retained observation count, observed-product count, first and last inserted
observation times and allocated SQLite bytes. These diagnostics are read-only;
Price Watch does not automatically delete, compact or rewrite history.
After explicitly applied retention they also report reclaimable bytes which
SQLite can reuse without an automatic vacuum.

Catalog installations may opt into a read-only Home Assistant retention
preview by adding a positive `retention_preview_days` option. The resulting
`sensor.price_watch_maintenance` reports the selected cutoff and exact total,
removable, retained and protected observation counts. Version 0.26.0 permits
the reviewed count to be sent back through an explicit Home Assistant
`hassio.addon_stdin` action. The App replans under the same lock as monitoring,
rejects a changed count and creates a complete persistent backup before any
positive deletion. Retention is never scheduled and SQLite is never vacuumed.

## Home Assistant repository installation

New installations should add
`https://github.com/rkobrle-alt/price-watch` as a Home Assistant App
repository and install Price Watch from the App store. The repository manifest
uses the published amd64/aarch64 GHCR image, so later releases appear as normal
managed App updates.

An existing `local_price_watch` installation is a different Home Assistant App
identity and must not be uninstalled before migration. Version 0.27.1 provides
an explicit checksummed export to `/share/price-watch-migration` and a
pre-cycle import for the repository App. This preserves the catalog database,
price and availability history and notification reservations. Follow the
backup, migration, verification and rollback procedure in the packaged
`DOCS.md`; adding the repository alone does not transfer `/data`.

Version 0.28.0 treats a Supervisor-requested stop as a successful lifecycle
event. The packaged operator guide includes a stop/restart acceptance check
which verifies that catalog history and notification reservations remain
durable.

## Stable compatibility

Version 1.0.0 declares the verified monitoring behavior stable without
changing the 0.31.0 catalog, discount, email, persistence or Home Assistant
behavior. During the 1.x series, existing public Python exports, CLI commands,
valid App options, published entity contracts and supported persistence
formats remain compatible. Intentional incompatible changes require an
approved architecture decision, an applicable data migration and a new major
version. See `docs/architecture/versioning-and-compatibility.md` for the exact
contract.

## Development

The project requires Python 3.13 or newer.

Run the complete test suite:

```text
python -m pytest
```

Architecture decisions, implementation stories and the roadmap are located in
`docs/`.
