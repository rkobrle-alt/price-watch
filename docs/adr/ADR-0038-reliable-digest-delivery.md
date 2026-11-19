# ADR-0038: Recoverable preparation and explicit delivery uncertainty

## Status

Accepted under the user's explicit authorization to implement, test, publish
and deploy improvements 4 and 5. Target release: 1.4.0.

## Decision and scope

Preserve existing DailyDigestWorkflow calls and legacy reserve-before-send
behavior when no delivery store is supplied. Managed HA catalog composition
enables a new durable delivery collaborator and the policy below.

Schema 9 adds digest_delivery_attempts(calendar_date, phase, updated_at,
product_count, promotion_included, promotion_missing). Calendar date is unique.
Phases are ready, preparing, sending, accepted, uncertain and legacy_reserved.
Migrate all existing reservations to legacy_reserved without asserting delivery
or retrying them. Preserve history, reservations, baselines and lifecycle data.

One Supervisor App process and its existing operation lock are the sole writer.
At its first workflow invocation, recover preparing entries to ready and release
their reservations/candidate baselines. Recover sending entries to uncertain
and discard their candidate baselines, retaining the no-resend reservation.
This is process-start recovery, not lease expiry or concurrent-worker takeover.
The new store/workflow must not be shared across independent live workers.

For an eligible date, atomically claim ready→preparing and reserve that date.
Prepare products and stage the comparison baseline before changing to sending.
Persist sending and candidate metadata before invoking the notify service.
After its successful response, persist accepted; that acknowledges the HA call,
not inbox delivery. Preparation exceptions release safely for a later cycle.
Definite pre-execution rejection releases safely; retry on the next normal cycle.
Every other dispatch exception or crash retains uncertain and cannot auto-resend.
If persistence fails after handoff, do not release: restart marks it uncertain.
Baseline lookup excludes new unaccepted attempt dates; uncertain attempts must
not alter future new/returning-product comparison. Legacy baseline behavior is
retained. Ordinary accepted/legacy dates continue returning already_sent.

Infrastructure classifies only HTTP 401/403 and connection-refused/DNS failures
as known pre-execution rejection; timeouts, dropped responses, 5xx and arbitrary
channel exceptions are ambiguous. Typed errors cross Infrastructure/Core
boundaries; do not parse messages or expose credentials/response bodies.

Core exports DigestDeliveryPhase, DigestDeliveryRecord, DigestDeliveryStore
and DigestPromotionPolicy. The store exposes recover(timestamp), claim(date,
timestamp), transition(date, expected, phase, timestamp, product_count=0,
promotion_included=False, promotion_missing=False) and latest(). Validate types,
date/timestamp awareness, counts, phase transitions and persisted values.
SQLite writes use transactions and compare expected phases; mismatch is an
explicit persistence error, never permission to dispatch. Store failures use
DailyDigestReservationError. Existing exported names and call forms survive.

DailyDigestResult adds delivery_retry and delivery_uncertain outcomes
and a promotion_missing flag for SENT only. Health surfaces delivery_retry and
delivery_uncertain as explicit failure kinds. HA publishes the latest ledger
phase/date/metadata on sensor.price_watch_digest_delivery. An accepted phase
is not a guarantee that the destination mailbox received the message.

## Banner fallback

Retry operational PromotionError failures on ordinary cycles until 30 minutes
after the configured local delivery time. At/after that boundary, send the
discount digest with a Czech notice that today's Lidl promotion could not be
verified. Absent banners returning None are normal and need no warning.
Do not reuse an earlier day's banner or invent an offer. Persist fallback
metadata for diagnostics; no second email is sent if the banner later recovers.
The deadline is tied to the scheduled date/time, so a late startup does not
start another indefinite waiting period. Policy uses supplied aware times.

## Trade-offs and migration

SMTP/HA supplies no end-to-end idempotency key or mailbox receipt. Automatically
resending uncertain requests risks duplicates; labelling a reservation sent
conceals uncertainty. Explicit uncertainty is the chosen boundary. A complete
message outbox would not remove that boundary and is unnecessary for safe
preparation recovery. No automatic resend, user messaging or manual-clear UI is
added for uncertain dates. A later explicitly authorized investigation can
verify external evidence before any resend. Legacy ambiguous dates are not
silently reclassified as accepted.

Sequential schema 8→9 migration is transactional. Preserve a pre-update App
backup; old binaries cannot read schema 9. Restore requires separate explicit
authorization if needed. This ADR supersedes the crash boundary and promotion
blocking policy in ADR-0020/0030/0035 for the managed reliable composition only.

Evidence timestamps retain the supplied monitoring-cycle time, matching current
observation/digest timestamp semantics. They do not assert exact response or
mailbox-receipt times.
