# Price Watch Home Assistant App

## Configuration

Configure one or more Lidl Czech Republic Parkside product page URLs. The
default notification entity is `notify.gmail_parkside_kobrle_fomei_com`, matching the existing
SMTP integration. Change it if Home Assistant exposes the service under a
different notify entity ID.

`interval_seconds` controls the fixed delay after each completed cycle. The
first cycle runs immediately. `price_drop_percentage` and
`price_drop_amount` are optional decimal strings.

## Persistence

The first successful observation establishes a baseline in
`/data/state.json`. Supervisor preserves this App-owned file across restarts
and upgrades. Later observations can detect a lower price or a return to stock.

## Security

The App requests Home Assistant Core API access only. Supervisor injects the
API token at runtime. The token and SMTP credentials are not App options and
are never stored by Price Watch.

## Operation

Start the App and inspect its log for cycle summaries and provider errors. A
notification is sent only when an enabled rule matches a change from the
stored baseline.
