# Operational Reporting

ADR-0031 owns real-time durable health. ADR-0034 adds a separate reporting
policy without changing health classification or Home Assistant sensor
contracts.

```text
completed catalog check
    |
    +--> OperationalMonitoringWorkflow --> durable current health
    |
    +--> WeeklyOperationalSummaryWorkflow
            |
            +--> current Europe/Prague weekly bucket
            +--> prior complete bucket eligibility
            +--> weekly summary channel when due
```

Core receives explicit dates, times and timestamps. It aggregates immutable
weekly values and formats deterministic content. Applications decide when to
invoke the workflows. SQLite stores buckets and Home Assistant performs email
delivery.

Immediate operational delivery and weekly reporting are independent policies.
Disabling immediate delivery never disables classification, persistence,
logging or sensor publication. Product alerts and the daily discount digest
use their existing independent channels and reservations.

Each weekly bucket is keyed by its Monday start date. The immediately
preceding completed bucket is eligible from the current Monday's configured
time through the rest of that week, so a delayed start can catch up. Empty
buckets do not send. A successful retained delivery mark prevents a duplicate
after restart; ordinary channel failures clear the mark for retry.
