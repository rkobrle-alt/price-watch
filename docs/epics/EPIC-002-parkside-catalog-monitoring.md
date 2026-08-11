# EPIC-002: Parkside Catalog Monitoring

## Goal

Automatically discover and monitor the complete Parkside and Parkside
Performance offer on Lidl Czech Republic.

The monitored scope includes power, cordless and hand tools, garden tools and
equipment, batteries, chargers, work and consumable accessories and spare
parts represented in the Lidl product catalog.

## User Outcome

The operator does not maintain individual Lidl product URLs. Price Watch
discovers new products, retains their price and availability history and can
send an email when a product becomes at least 20 percent cheaper. An optional
daily digest summarizes currently discounted available products. Catalog
installations may disable individual alerts and use only that daily digest.

## Architecture Constraints

- discovery uses only the robots-advertised Lidl product sitemap
- search and pagination crawling remain prohibited
- Lidl product pages remain authoritative for brand and product data
- Core remains deterministic and independent of HTTP, persistence and Home
  Assistant
- catalog, history and delivery side effects belong to Infrastructure
- Applications own discovery, refresh and digest orchestration
- existing explicit-URL CLI and Home Assistant configuration remain backward
  compatible until an intentional migration is approved

## Delivery Sequence

1. sitemap-based Parkside catalog discovery
2. durable catalog membership and observation history
3. bounded, serial catalog refresh workflow with immediate processing of new
   references
4. 20-percent alert reference and delivery deduplication
5. optional calendar-based daily digest
6. Home Assistant catalog health and summary representations
7. dashboard-ready operational overview and diagnostics
8. digest-only notification policy
9. non-destructive observation storage diagnostics
10. manual backup-protected observation retention
11. optional Home Assistant retention preview
12. explicit backup-protected Home Assistant retention command
13. managed Home Assistant repository distribution with state-preserving
    migration
14. graceful managed-App shutdown and restart acceptance

Each step requires its own accepted ADR when it introduces a new persistence,
workflow, rule or scheduling contract.

ADR-0016 and STORY-015 define and implement step 1. ADR-0017 and STORY-016
define step 2 using durable catalog membership and exact SQLite observation
history while leaving workflow composition unchanged. ADR-0018 and STORY-017
define step 3 using durable refresh-attempt ordering, bounded Application
orchestration and an opt-in Home Assistant catalog mode.
ADR-0019 and STORY-018 define step 4 using original-price then historical-high
reference selection and durable logical-price reservations.
ADR-0020 and STORY-019 define step 5 using latest persisted product states,
Europe/Prague calendar eligibility and one durable reservation per local date.
ADR-0021 and STORY-020 define step 6 using durable provider-neutral catalog
statistics and one aggregate Home Assistant catalog-health representation.
ADR-0022 and STORY-021 define step 7 by projecting the already computed
catalog outcome into backward-compatible native Home Assistant overview
states without changing Core or persistence.
ADR-0023 and STORY-022 define step 8 as a Home Assistant composition option
which can suppress all individual rules while retaining the daily digest.
ADR-0024 and STORY-023 define step 9 as read-only observation growth and
storage-health publication without approving retention or deletion.
ADR-0025 and STORY-024 define step 10 as explicit CLI-only retention which
preserves current state and historical-high price references, requires a
pre-deletion backup and is never scheduled by Home Assistant.
ADR-0026 and STORY-025 define step 11 as an opt-in read-only projection of a
selected retention window in Home Assistant while retaining CLI-only apply.
ADR-0027 and STORY-026 define step 12 as a one-shot Supervisor-stdin command
which replans, rejects stale confirmation and serializes backup-protected apply
with normal monitoring.
ADR-0028 and STORY-027 define step 13 as an explicit checksummed hand-off from
the local App identity to the GitHub-repository identity before its first
monitoring cycle.
ADR-0029 and STORY-028 define step 14 as process-edge `SIGTERM` handling with a
successful exit and an explicit check that restart preserves durable state.

## Discount Semantics

The target policy is a current price at most 80 percent of its reference
price. ADR-0019 defines the durable order as the reliable current original
price when available, otherwise the highest prior same-currency observed
price.

The same logical product price and currency must not generate repeated alert
emails during normal operation. ADR-0019 documents the unavoidable crash
boundary between durable reservation and Home Assistant delivery.

## Done When

- newly published Parkside products are discovered without configured URLs
- every accepted product retains durable price and availability observations
- catalog refresh remains bounded and does not use prohibited endpoints
- a qualifying 20-percent price reduction produces one actionable email
- unchanged prices do not repeat that email
- the daily digest can be enabled or disabled and uses Europe/Prague calendar
  time
- Home Assistant reports catalog health and useful aggregate counts
- Home Assistant can display qualifying discounts, current errors and the
  latest completed check directly on a dashboard
- catalog email delivery can be configured as one daily digest without
  individual product messages
- observation growth and SQLite health are visible without modifying history
- historical growth can be reduced manually without changing current state or
  the durable historical-high discount reference
- a selected retention window can be assessed in Home Assistant without
  enabling destructive maintenance there
- a reviewed current plan can be applied from an explicit Home Assistant
  action without enabling scheduled or restart-triggered deletion
- future App versions can be installed and updated from the managed repository
  without discarding catalog history or reservation state
- a Supervisor-requested stop exits successfully and a restart resumes from
  the same durable catalog and reservation state
