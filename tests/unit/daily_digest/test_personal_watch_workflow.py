"""Personal resolution is repeated after refresh and fails before delivery."""

from dataclasses import replace
from datetime import time, timedelta
from decimal import Decimal

import pytest

from applications.daily_digest import DailyDigestWorkflow, DailyDigestConfig, DailyDigestStatus
from core.domain import Percentage
from core.notifications import DailyDiscountDigestEngine
from core.state import StateSnapshot
from core.watch import DigestWatchPreferences, WatchProductPreference
from tests.unit.daily_digest.test_workflow import _Reader, _Reservations, _Channel, _Baselines, _PRAGUE, _TIMESTAMP, _DATE
from tests.unit.daily_digest.test_freshness_workflow import _Refresher
from tests.unit.notifications.test_personal_watch import product


def build(source, reader, reservations, channel, baseline, refresher=None):
    return DailyDigestWorkflow(reader, reservations, DailyDiscountDigestEngine(), channel,
        DailyDigestConfig(time(8), Percentage(Decimal(20))), _PRAGUE,
        baseline_store=baseline, watch_preference_source=source, product_refresher=refresher)


def test_resolves_again_after_stock_changes_and_stages_sale_ids_only() -> None:
    favorite, hidden, ordinary = product(1, reference=None, discount="0"), product(2), product(3)
    reader = _Reader(tuple(StateSnapshot(p, _TIMESTAMP - timedelta(days=1)) for p in (favorite, hidden, ordinary)))
    baseline, reservations, channel = _Baselines(()), _Reservations(), _Channel()
    refresher = _Refresher(reader, baseline)
    refresher.updated = (StateSnapshot(favorite, _TIMESTAMP), StateSnapshot(replace(ordinary, availability=False), _TIMESTAMP))
    class Source:
        def __init__(self):
            self.calls = []
        def resolve(self, snapshots):
            self.calls.append(snapshots)
            rules = tuple(WatchProductPreference(s.product.id, favorite=s.product.id == favorite.id, hidden=s.product.id == hidden.id)
                for s in snapshots if s.product.id in (favorite.id, hidden.id))
            return DigestWatchPreferences(rules)
    source = Source()
    assert build(source, reader, reservations, channel, baseline, refresher).run(_TIMESTAMP).status is DailyDigestStatus.SENT
    assert len(source.calls) == 2
    assert source.calls[-1] == refresher.updated
    assert refresher.calls == [(favorite, ordinary)]
    assert channel.digests[0].products == (favorite,)
    assert baseline.stage_calls == [(_DATE, ())]


def test_bad_preference_source_cannot_send_and_releases_preparation() -> None:
    reader, reservations, channel, baseline = _Reader(), _Reservations(), _Channel(), _Baselines()
    with pytest.raises(TypeError, match="resolve"):
        build(object(), reader, reservations, channel, baseline)
    class Source:
        def resolve(self, snapshots):
            return object()
    with pytest.raises(TypeError, match="DigestWatchPreferences"):
        build(Source(), reader, reservations, channel, baseline).run(_TIMESTAMP)
    assert reservations.release_calls == [_DATE]
    assert baseline.release_calls == [_DATE]
    assert channel.digests == []
