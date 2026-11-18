# STORY-039: Accept Lidl Plus promotion links

The 2026-11-18 live banner points to lidlplus.com. The existing host allowlist
rejects it and the digest remains promotion_unavailable. Extend the private
Infrastructure allowlist in accordance with the ADR-0030 amendment. Public
APIs, reservation semantics, storage and dependency direction remain unchanged.

Test the observed coupon link and reject lookalike hosts, subdomains, HTTP,
credentials and non-default ports. Run the complete suite with full coverage.
Publish patch 1.2.5, update the managed App and verify today's sent digest.

Readiness: implementation-ready; scope and acceptance criteria reviewed.
