# STORY-028: Home Assistant Production Readiness

## Objective

Implement ADR-0029 and release v0.28.0 so a Supervisor-requested stop is
reported as a successful, prompt Home Assistant App shutdown without changing
monitoring, persistence or recovery semantics.

## Scope

- install and restore a process-local `SIGTERM` handler around the Home
  Assistant App execution boundary;
- distinguish Supervisor termination from interactive `KeyboardInterrupt`;
- preserve completed-cycle diagnostics when termination occurs during the
  scheduler run;
- document the managed-App stop, restart and state-preservation acceptance
  check;
- update release metadata to 0.28.0.

Do not modify Core, Domain, Provider SDK, Rule Engine, scheduler contracts,
persistence formats, SQLite schema version 4, catalog behavior, notification
rules, digest timing, sensor entity IDs or migration archive format. Do not add
automatic restore, retries, another process supervisor, port, ingress or host
permission.

## Files

Create:

```text
applications/homeassistant/lifecycle.py
tests/unit/homeassistant_app/test_lifecycle.py
```

Modify the Home Assistant process boundary and its tests; App operator docs,
changelog and version metadata; packaging/version assertions.

## Public API

No public API changes.

`applications.homeassistant.run`, `applications.homeassistant.main` and all
existing package exports retain their signatures. The termination exception,
handler and context manager are private implementation details and are not
exported through `applications.homeassistant.__init__`.

## Shutdown Behavior

The process adapter installs the `SIGTERM` handler immediately before calling
the existing `run()` function and restores the preceding handler in a
`finally` path.

The handler raises one private `BaseException` subtype on the main Python
thread. During scheduler execution, `run()` catches only that exact internal
signal, writes the existing `watch stopped` outcome using completed cycle and
error counters, and returns `0`. If termination occurs after handler
installation but before scheduler execution, `main()` writes
`shutdown complete: before monitoring` and returns `0`.

`KeyboardInterrupt` continues to write `watch stopped` and return `130`.
Known operational, configuration and unexpected failure behavior remains
unchanged. Shutdown does not delete, rewrite, export or import state.

## Recovery Acceptance

The existing ADR-0028 Home Assistant backup and checksummed migration archive
remain authoritative. After installing v0.28.0, the operator verifies:

1. the managed App completes a healthy catalog cycle;
2. an explicit App stop does not produce a new application error;
3. the App restarts successfully;
4. the catalog observation count does not move backwards;
5. notification and daily-digest reservations remain effective;
6. existing Home Assistant sensor entity IDs remain available.

The retained backup and migration archive are not deleted by this story.

## Validation and Errors

The internal signal mechanism accepts no public input. Existing public invalid
argument types continue to raise `TypeError`. Handler installation or
restoration failures are unexpected process failures and propagate.

## Tests

Add tests for:

- `SIGTERM` conversion to the private termination signal;
- restoration of the preceding handler after success and failure;
- termination during scheduler delay returning `0` with completed counters;
- termination before monitoring returning `0` with the startup shutdown
  outcome;
- unchanged `KeyboardInterrupt` exit code `130`;
- unchanged known and unexpected failure mappings;
- version consistency and complete operator instructions;
- complete regression suite at 100 percent statement and branch coverage.

## Acceptance Criteria

- the managed container responds promptly to Supervisor `SIGTERM`;
- a requested stop exits with code `0`;
- completed-cycle counters are reported when monitoring had begun;
- the preceding signal handler is restored for programmatic callers and tests;
- Ctrl+C and all established error exit codes remain backward compatible;
- stop and restart preserve catalog history and notification reservations;
- no public API or dependency direction changes;
- all public APIs remain typed, documented and exported through `__init__.py`;
- no TODOs, placeholders, skipped tests, commented code or dead code remain;
- all tests pass with 100 percent statement and branch coverage.
