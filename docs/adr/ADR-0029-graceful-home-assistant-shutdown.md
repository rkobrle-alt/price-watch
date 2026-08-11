# ADR-0029: Graceful Home Assistant Process Shutdown

## Status

Accepted

## Context

The Home Assistant App runs indefinitely and currently handles an interactive
`KeyboardInterrupt`, but its Python process does not distinguish the
Supervisor's `SIGTERM` stop request from an abnormal process termination. A
normal operator stop can therefore end with a non-zero signal status and be
reported as an App error even though monitoring was healthy.

The monitoring scheduler, persistence contracts and business workflows do not
own operating-system process lifecycle. Shutdown must not introduce signal or
clock access into Core, change error semantics, or add another long-running
service.

## Decision

The `applications.homeassistant` process adapter installs a temporary handler
for `SIGTERM` immediately around the existing `run()` invocation. The handler
raises an internal termination signal which interrupts either an active cycle
or the fixed-delay wait on the main thread.

The existing Home Assistant application boundary maps that internal signal to
a graceful result:

- during monitoring, it writes the established `watch stopped` outcome with
  the completed-cycle counters and returns exit code `0`;
- before monitoring has been composed, the outer process adapter writes a
  concise shutdown outcome and returns exit code `0`;
- the previously installed process signal handler is always restored.

Interactive `KeyboardInterrupt` retains exit code `130`. Known operational
failures retain exit code `1`, configuration failures retain exit code `2`,
and unexpected programming failures continue to propagate.

No Core, Domain, Provider SDK, Rule Engine, scheduler, persistence or public
API changes are introduced. The signal handler and termination type are
private process-adapter details.

## Recovery Verification

The checksummed migration archive and Home Assistant backup established by
ADR-0028 remain the supported recovery mechanisms. This decision adds no new
state format or restore path. Production acceptance must verify that a managed
App stop and restart preserves the existing state and resumes monitoring.

## Dependency Direction

```text
Home Assistant Supervisor SIGTERM
    -> applications.homeassistant process adapter
    -> existing applications.homeassistant run boundary
```

Operating-system signal handling remains at the executable application edge.
Core and Infrastructure do not import Applications and remain unchanged.

## Alternatives Considered

### Let Docker terminate the process by default

Rejected because a normal requested stop remains indistinguishable from an
abnormal signal termination in the process result.

### Treat SIGTERM as KeyboardInterrupt

Rejected because exit code `130` describes an interactive interrupt rather
than a successful Supervisor-requested stop.

### Add cancellation to the scheduler or Core

Rejected because the App has one serial process and the operating-system
lifecycle is not a reusable business or scheduling contract.

### Add a shell init system

Rejected because the Python process is already PID 1 and can directly handle
the one required termination signal without another runtime layer.

## Consequences

A requested Home Assistant stop terminates promptly and successfully while
preserving all established failure mappings. A termination signal can
interrupt an in-progress side effect; existing transactional and context
manager cleanup remains responsible for rollback, and the next start resumes
from durable state.
