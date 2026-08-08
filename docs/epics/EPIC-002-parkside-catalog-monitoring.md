# EPIC-002: Parkside Catalog Monitoring

## Goal

Automatically discover and monitor the complete Parkside and Parkside
Performance offer on Lidl Czech Republic.

The monitored scope includes power, cordless and hand tools, garden tools and
equipment, batteries, chargers, work and consumable accessories and spare
parts represented in the Lidl product catalog.

## User Outcome

The operator does not maintain individual Lidl product URLs. Price Watch
discovers new products, retains their price and availability history and sends
an email when a product becomes at least 20 percent cheaper. An optional daily
digest summarizes currently discounted available products.

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
