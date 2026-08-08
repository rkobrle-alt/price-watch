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

Catalog mode uses a 20-percent default alert threshold. A provider original
price is preferred as the reference; otherwise the highest prior
same-currency observation is used. Durable SQLite reservations prevent an
unchanged qualifying product price from repeatedly sending email.

## Development

The project requires Python 3.13 or newer.

Run the complete test suite:

```text
python -m pytest
```

Architecture decisions, implementation stories and the roadmap are located in
`docs/`.
