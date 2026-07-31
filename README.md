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

## Development

The project requires Python 3.13 or newer.

Run the complete test suite:

```text
python -m pytest
```

Architecture decisions, implementation stories and the roadmap are located in
`docs/`.
