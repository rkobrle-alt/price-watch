"""Missing pages must not masquerade as stale purchasable offers."""

import pytest

from core.notifications import DigestFreshnessPolicy
from core.provider import ProviderProductNotFoundError, ProviderTransportError
from tests.unit.notifications.test_daily_digest import _product, _snapshot


def test_missing_filter_matches_exact_url_and_retains_transient_failures() -> None:
    snapshots = tuple(_snapshot(_product(i, f"Tool {i}", "20")) for i in (1, 2, 10))
    missing = ProviderProductNotFoundError("missing", snapshots[0].product.url)
    # Message content is deliberately indistinguishable; only typed evidence counts.
    transient = ProviderTransportError(f"{snapshots[1].product.url} [HTTP 404]")
    policy = DigestFreshnessPolicy()
    assert policy.after_refresh(snapshots, (missing, transient)) == snapshots[1:]
    assert policy.after_refresh(snapshots, ()) == snapshots
    assert policy.after_refresh((), (missing,)) == ()


@pytest.mark.parametrize("url", [None, 1])
def test_missing_error_rejects_non_string_url(url: object) -> None:
    with pytest.raises(TypeError, match="url"):
        ProviderProductNotFoundError("missing", url)  # type: ignore[arg-type]


def test_missing_error_rejects_blank_url() -> None:
    with pytest.raises(ValueError, match="blank"):
        ProviderProductNotFoundError("missing", "  ")


@pytest.mark.parametrize(("snapshots", "errors"), [([], ()), ((object(),), ()), ((), []), ((), (object(),))])
def test_filter_rejects_invalid_collections(snapshots: object, errors: object) -> None:
    with pytest.raises(TypeError):
        DigestFreshnessPolicy().after_refresh(snapshots, errors)  # type: ignore[arg-type]
