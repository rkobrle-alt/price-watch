# STORY-035: Product HTTP Error Diagnostics

## Status

Implementation-ready for patch 1.2.1. Implements the existing ADR-0007 error
boundary; no architecture or public Python API change is required.

## Scope

Improve human-readable errors from `UrllibTextHttpClient` only. Keep
`HttpClientError`, its original exception cause, the provider conversion to
`ProviderTransportError`, and all existing method signatures unchanged.
The binary catalog client, parser, Core, workflows and storage are out of scope.

Use a private helper in the existing text HTTP client module. Retain the
`failed to retrieve <url>` prefix and append a bracketed diagnostic:

- HTTP status code, including 404, 429 and 503;
- timeout, including TimeoutError wrapped by URLError;
- DNS error or TLS error, direct or wrapped by URLError;
- connection error, direct or wrapped;
- generic network error for other URLError reasons;
- decoding error for UnicodeError;
- I/O error for other caught OSError values;
- incomplete response after two attempts when the existing retry is exhausted.

Keep the current exception catch boundary and retry policy: only IncompleteRead
gets one retry. No retries for HTTP 404/429/503, timeout or parsing failures are
added. Do not mark products unavailable, delete data or change notifications.
Do not append response bodies, headers or arbitrary exception/reason text.
The requested URL remains in the established diagnostic prefix.

## Acceptance and tests

Network-free tests cover every diagnostic category, direct and wrapped network
errors, HTTP status preservation, cause identity, retry counts, and absence of
injected sensitive text or response data in the error message. An adapter test
must prove a real text-client error survives provider conversion with the URL
and HTTP code. Existing parser and partial-success behavior must remain intact.

Run the complete suite and dependency gates with 100% statement and branch
coverage. Update operator documentation and synchronized patch identity to
1.2.1. Prepare logical commits. Publication and HA deployment are separate
actions requiring user authorization.
