# ADR-0040: Personal daily watch preferences

## Status

Accepted under explicit authorization to implement, test, publish and deploy
v1.6.0. Defaults preserve existing output, selection and delivery behavior.

## Settings and ownership

Use native Supervisor App options, stored in the existing options.json:
favorite_product_urls: list of Lidl product links; hidden_product_urls: list of
links; target_prices: list of {url, amount: decimal string, currency: CZK|EUR
(default CZK)}; included_categories: list of category names; watch_category_rules:
list of {name, keywords: list of words/phrases}. Product lists and category filter
default empty. Provide conservative editable defaults for zahrada,
akumulatory_nabijecky, prislusenstvi, pracovni_odevy; unmatched names are ostatni.
No concrete favorite or target is invented for the user. Saving/restarting the
App applies settings, as for existing options. Add Czech/English field labels
and an operator example. Reject invalid/unknown option fields, duplicate product
identities within a list, conflicting target entries, invalid amounts/currencies,
unknown category filters and category-name collisions.

The Lidl Infrastructure adapter maps URLs by validated terminal p<digits> ID,
not the mutable name slug. Require HTTPS, Czech Lidl host, no credentials or
nondefault port and an individual /p/<slug>/p<digits> path. Tracking query and
fragment do not change identity. Match only the Lidl provider. Unknown favorites
and targets are allowed before discovery: seed their references into the catalog
only when the identity is absent. Do not overwrite a newer canonical catalog URL.
Hidden references are never seeded solely for personal watching. Monitoring and
historical observations remain retained when a preference is removed.

Core adds immutable WatchProductPreference (resolved ProductId, favorite,
target_price, hidden), WatchCategoryRule, DigestWatchPreferences, WatchTargetStatus,
DigestWatchPolicy and DigestWatchPreferenceSource. Infrastructure resolves URLs
to IDs using current observations, preserving the provider-neutral Core boundary.
HA option parsing remains deterministic and never opens a database/network.

## Selection and classification

Hidden wins over every other preference. Unavailable/missing resources remain
excluded. An explicit favorite or target rule includes its available product even
without the default reference discount and overrides category filtering. Other
offers must satisfy the existing discount threshold and the selected categories.
An empty category filter allows all; multiple selected categories are ORed.
Categories are transparent name-derived groups, not asserted retailer taxonomy.
Match whole normalized words/phrases, case- and diacritic-insensitively. Multiple
categories may match a name. Custom rules replace the defaults; ostatni is reserved.

Targets compare exact Money in the same currency; never convert currencies.
Reached requires current price <= target and an available observation within
one hour inclusive, not future-dated. Old/failed checks are unverified, not reached.
Different currency is explicitly incomparable. Watched offers above target remain
visible as waiting, without falsely calling them discounted. All of these are
parts of the same daily email; do not add immediate or repeat target emails.
Existing separate individual-alert settings retain their independent semantics.

Apply selection before extra digest refresh and price-history analysis. Prioritize
stale explicit watches within the existing 200-product refresh budget, then ordinary
eligible offers, oldest first. Re-resolve preferences after refresh; successful
sold-out/missing resources disappear normally. Budget-excluded watches retain the
existing stale warning and cannot claim a reached target.

## Presentation, baselines and compatibility

Only active preferences change output: reached targets first, other favorite/
target watches next, then new and other ordinary discounts. Keep 1.5 value ordering
inside these groups. Show favorite, target status and name-derived categories.
Use a personal-offer count header rather than calling every watch a discount.
Use a truthful no-matching-offers message when filters remove everything.

DailyDiscountDigest appends watch_preferences=None and baseline_product_ids=None;
engine.generate appends watch_preferences=None. None/empty defaults retain old
calls and output. Resolved preference IDs must be a subset of supplied observations
(not only the final selected set, since hidden rules must also be represented).
Append optional watch_preference_source to DailyDigestWorkflow and compose it only
when configured. Append optional watch_preferences to DigestFreshnessPolicy.select.

Novelty is evaluated only among displayed products satisfying the reference discount
threshold. Persist that subset as the candidate baseline; nonsale watched products
must not hide a later entry into the discount set. Legacy None baselines use all
digest products exactly as before. Reliable preparation, banner fallback, acceptance
and uncertainty preserve all new metadata and still prevent duplicate sends.

No new database schema, network endpoint, permission, credential or scheduler.
Additive APIs are exported with validation/docstrings. Use existing error boundaries
and preparation compensation; invalid preferences must not silently widen selection.

## Alternatives

A separate web UI is a later dashboard milestone. Unlabelled automatic taxonomy
would invent retailer data. Matching mutable slugs breaks watches unnecessarily.
Treating stale prices as target hits or sending additional immediate emails would
misrepresent evidence or violate current delivery policy. Permanent catalog removal
for hidden offers would destroy useful history; hiding affects the personal digest.
