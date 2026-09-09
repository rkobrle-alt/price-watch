# STORY-036: Isolate Malformed Product HTTP Responses

## Status

Implementation-ready for 1.2.2 under ADR-0007. This repairs the existing
operational error boundary without redesigning architecture or public APIs.

## Problem

A production response beginning with `;HTTP/1.1 200 OK` raised
`http.client.BadStatusLine` outside the text HTTP client's catch boundary,
terminating the monitoring process rather than reporting a failed product.

## Scope and implementation

In `infrastructure.http.urllib_client`, catch BadStatusLine and its subclasses
(including RemoteDisconnected) explicitly. Preserve the original cause and
raise the existing HttpClientError with `failed to retrieve <url>
[HTTP protocol error]`. Do not append the invalid response line or body.

Keep the existing one-retry policy for IncompleteRead. Do not retry malformed
status lines. Do not catch all HTTPException or Exception values: unrelated
programming errors must continue to propagate. Provider conversion and
partial-success processing remain unchanged. No new public exports, Core,
Provider SDK, parser, binary-client, database, notification or option changes.

## Tests and acceptance

- Cover failure while opening and reading a response, preserving cause and
  one attempt per malformed response, without exposing raw response text.
- Cover RemoteDisconnected and an actual HTTPResponse parsing the observed
  invalid status line.
- Verify a later valid product is parsed after one malformed product.
- Verify unrelated RuntimeError still propagates.
- Keep existing IncompleteRead retry tests passing.
- Run the full suite and architectural gates with 100% statement and branch
  coverage; update operator notes and synchronized version identity to 1.2.2.
- Save reviewed changes in logical commits. Release publication and HA
  deployment are separate from preparing this patch.
