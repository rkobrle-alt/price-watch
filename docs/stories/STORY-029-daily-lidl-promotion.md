# STORY-029: Daily Lidl Promotion

## Objective

Implement ADR-0030 and release v0.29.0 so the current yellow Lidl marketing
message and its link appear near the top of the daily Parkside discount email.

## Scope

- add provider-neutral immutable promotion data and source contract to Core;
- retrieve and parse the global Lidl Czech Republic marketing banner through
  the existing text HTTP boundary;
- request the promotion only for a newly eligible daily digest;
- format it before the existing discount threshold and products;
- retry a failed promotion lookup on a later catalog cycle without stopping
  monitoring or consuming the daily reservation;
- expose promotion inclusion and retry status in the existing cycle log;
- update documentation and release metadata to 0.29.0.

Do not modify Product, Provider SDK, Rule Engine, catalog discovery,
observation persistence, SQLite schema version 4, notification channel,
digest date identity, Home Assistant entity IDs, schedule or existing App
options. Do not add browser automation, JavaScript rendering, credentials,
another external API or a second email.

## Files

Create:

```text
core/promotions/__init__.py
core/promotions/model.py
core/promotions/source.py
core/promotions/exceptions.py
infrastructure/providers/lidl/promotion.py
tests/unit/promotions/test_promotions.py
tests/unit/providers/test_lidl_promotion.py
```

Modify the Core digest model/engine, daily-digest workflow and result,
Home Assistant digest composition and cycle summary, public exports, unit
tests, architecture checks, App documentation, changelog and version metadata.

## Public API

Implement exactly the APIs approved in ADR-0030. Existing positional calls to
`DailyDiscountDigest`, `DailyDiscountDigestEngine.generate` and
`DailyDigestWorkflow` remain valid. All new public objects are typed,
documented and exported through `__init__.py`.

## Lidl Parsing

`LidlMarketingPromotionSource` accepts an injected `TextHttpClient` and calls
it with the fixed `https://www.lidl.cz/` URL. The parser uses Python standard
library HTML facilities, not regular expressions over the complete document.

It selects the first `span` whose class tokens contain
`n-navigation__marketing-message--label`, combines its text chunks and
normalizes all whitespace runs to one ASCII space. The nearest surrounding
anchor supplies the optional link. Relative links resolve against the fixed
home page. Retained links must use HTTPS and the Czech Lidl host. A missing
label returns `None`; a blank label, non-string response, unsafe URL or parser
failure raises `PromotionError`.

## Digest Behavior

For a promotion with a URL, the exact inserted block is:

```text
Lidl daily offer: {promotion.text}
Offer URL: {promotion.url}
```

Without a URL, only the first line is inserted. The block follows the existing
date heading and precedes `Minimum discount`. Digest product selection,
ordering and formatting remain unchanged.

After the delivery time, the workflow reserves the date as before. When the
reservation is new and a source is configured, it calls `current()`. On
`PromotionError` it releases the reservation and returns
`PROMOTION_UNAVAILABLE` with zero products and no delivery. A later cycle may
retry. `None` proceeds without a promotion. A valid promotion is passed to the
engine and a successful result reports `promotion_included=True`.

The Home Assistant cycle summary appends
`digest_promotion=true|false` for `SENT`; the retry status is already explicit
as `digest_status=promotion_unavailable`.

## Validation and Errors

Invalid public argument types raise `TypeError`; invalid values raise
`ValueError`. External HTTP and banner data failures use `PromotionError`.
Only `PromotionError` receives the non-fatal retry mapping. Unexpected source
failures propagate and retain the reservation compensation behavior.

## Tests

Add tests for:

- immutable promotion validation and Protocol/public exports;
- current Lidl markup, nested text, entity decoding and whitespace;
- absolute and relative same-host links;
- missing labels and missing links;
- blank labels, unsafe links, non-text responses and HTTP failures;
- exact promoted non-empty and empty digest messages;
- backward-compatible digest calls without promotion;
- no lookup before due time or after an existing reservation;
- successful promotion, valid absence and retry outcome;
- reservation release and lack of snapshot/delivery side effects on lookup
  failure;
- unexpected failure propagation and existing compensation semantics;
- Home Assistant composition with the shared text client;
- exact cycle log fields, public API and dependency direction;
- complete regression suite at 100 percent statement and branch coverage.

## Acceptance Criteria

- the current global yellow Lidl message appears in the next eligible daily
  email with its Lidl URL when available;
- the same email still contains all qualifying Parkside product links;
- empty product digests also contain the promotion;
- a missing banner does not block the daily email;
- a temporary lookup failure neither sends an incomplete email nor stops
  catalog monitoring and is retried later;
- a sent date remains deduplicated exactly as before;
- no schema, option, Product, Provider SDK, Rule Engine or sensor change;
- public APIs are typed, documented and exported through `__init__.py`;
- no TODOs, placeholders, skipped tests, commented code or dead code remain;
- all tests pass with 100 percent statement and branch coverage.
