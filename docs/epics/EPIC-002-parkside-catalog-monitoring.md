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

## Discount Semantics

The target policy is a current price at most 80 percent of its reference
price. A later rule ADR must define the durable reference and fallback order.
The intended order is the reliable Lidl original price when available,
otherwise a historical price derived from stored observations.

The same logical product price must not generate repeated alert emails.

## Done When

- newly published Parkside products are discovered without configured URLs
- every accepted product retains durable price and availability observations
- catalog refresh remains bounded and does not use prohibited endpoints
- a qualifying 20-percent price reduction produces one actionable email
- unchanged prices do not repeat that email
- the daily digest can be enabled or disabled and uses Europe/Prague calendar
  time
- Home Assistant reports catalog health and useful aggregate counts
