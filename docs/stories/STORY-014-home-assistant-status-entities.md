# STORY-014: Home Assistant Status Entities

## Goal

Expose the latest Price Watch cycle and successfully fetched product states in
Home Assistant according to ADR-0015, without changing monitoring business
logic or introducing another deployment technology.

---

## Scope

This story includes:

- a Home Assistant state-update client contract
- REST state updates in the existing standard-library client
- deterministic cycle and product status publication
- Home Assistant App composition and non-fatal status failure handling
- operator documentation and packaging regression checks
- unit, architecture and boundary integration tests

This story does not include:

- changes to Core, Domain, Provider SDK, Rule Engine, State Store or the
  synchronization workflow
- custom Home Assistant integrations or entity-registry ownership
- MQTT, ingress, ports, dashboards or frontend code
- manual synchronization or test-notification actions
- notification retry or deduplication

---

## Package Structure

Create or modify:

```text
infrastructure/homeassistant/
    __init__.py
    client.py
    status.py
    urllib_client.py

applications/homeassistant/
    composition.py
    main.py

tests/unit/homeassistant/
    test_public_api.py
    test_status.py
    test_urllib_client.py

tests/unit/homeassistant_app/
    test_composition.py
    test_main.py
    test_packaging.py

tests/integration/test_homeassistant_app.py
```

Documentation affected by ADR-0015 must be updated before implementation.

---

## Public API

Export through `infrastructure.homeassistant`:

- existing `HomeAssistantClient`
- new `HomeAssistantStateClient`
- existing `HomeAssistantError`
- existing `UrllibHomeAssistantClient`
- new `HomeAssistantStatusPublisher`

The new signatures must exactly match ADR-0015. Existing public signatures and
exports remain backward compatible. Every public object has explicit typing
and documentation.

No new public API is exported from `applications.homeassistant`.

---

## REST State Updates

`UrllibHomeAssistantClient.set_state()` must:

- accept only a lowercase `sensor.<object_id>` entity ID
- require a non-blank string state
- require a Mapping with string keys for attributes
- serialize deterministic UTF-8 JSON with exactly `attributes` and `state`
- POST to `{base_url}/states/{entity_id}` using the existing bearer token,
  timeout and user agent
- read and close every successful response
- accept both state creation and update responses without interpreting their
  bodies
- translate `HTTPError`, `URLError` and operational `OSError` into
  `HomeAssistantError` with chaining
- leave JSON serialization errors as caller failures

The existing `call_service()` behavior must remain unchanged.

---

## Status Publication

`HomeAssistantStatusPublisher` must implement every entity name, state,
attribute and ordering rule from ADR-0015 exactly.

It must validate the entire call before the first client invocation. Duplicate
products are permitted and are published in supplied order because the
synchronization result already defines completed processing order.

The publisher stores no mutable cycle state, reads no clock, generates no
identifier, logs nothing and catches no `HomeAssistantError`.

---

## Home Assistant Application Integration

The composition root creates one `UrllibHomeAssistantClient` and shares it
between `HomeAssistantNotificationChannel` and
`HomeAssistantStatusPublisher`. The publisher receives the canonical
application version.

After each successful `SynchronizationWorkflow.run()` call, the process:

1. flattens successful products from `fetch_results` in result order
2. calls `publish_cycle()` with the caller-supplied cycle timestamp and exact
   notification and provider-error counts
3. writes the existing synchronization summary including
   `status_published=true`

If `publish_cycle()` raises `HomeAssistantError`, the process:

- writes `status error: MESSAGE` to stderr
- still writes the synchronization summary with `status_published=false`
- records one status-error cycle
- permits the scheduler to continue

Finite execution returns `1` when at least one provider-error cycle or status-
error cycle occurred. Its final summary includes both counters. Interruption
includes both counters and returns `130` as before.

Notification delivery errors and all other approved failure semantics remain
unchanged.

---

## Packaging and Operator Documentation

The App keeps only `homeassistant_api: true`; no permission, port, ingress,
mount, device or service dependency is added.

Documentation explains:

- `sensor.price_watch_status`
- deterministic per-product price sensor IDs
- available attributes
- the distinction between state representations and registry-backed entities
- restart as the current manual immediate-sync mechanism
- direct notify-entity testing as the current email test mechanism

No secret, token or SMTP credential may appear in a state or log.

---

## Tests

Tests must cover:

- structural compatibility of both Home Assistant client Protocols
- exact request URL, method, headers, timeout and JSON body
- create/update success responses and every defined failure translation
- every invalid `set_state()` public argument
- exact status and product entity IDs, states, attributes and ordering
- exact `Decimal` string preservation and optional image behavior
- timezone and count validation before any side effect
- publisher error propagation and absence of mutable state
- one shared REST client in the App composition
- successful publication and exact process summaries
- non-fatal status failure across later scheduler cycles
- finite exit status, interruption and existing operational failures
- unchanged App permissions and absence of new deployment surfaces
- dependency direction and public exports
- end-to-end publication through fake HTTP boundaries without network or wait

Target coverage:

- 100% statement coverage
- 100% branch coverage

No skipped tests are allowed.

---

## Acceptance Criteria

- ADR-0015 and all prior accepted ADRs are followed.
- a completed App cycle publishes current product prices and cycle health to
  Home Assistant.
- exact money never passes through `float`.
- stable Product IDs produce stable Home Assistant entity IDs.
- status publication occurs only after workflow notification and persistence
  behavior completes.
- an observability failure is visible but does not stop later monitoring.
- Core, Domain and reusable workflow contracts remain unchanged.
- existing notification and CLI behavior remains backward compatible.
- the App requests no additional permission or network surface.
- all public APIs are exported through `__init__.py`.
- no TODOs, placeholders, pass statements, commented code or dead code remain.
- all tests pass with 100% statement and branch coverage.
- all changes are visible in Git and organized into logical commits.
