from datetime import datetime, timedelta, timezone
from app.services import recent_price_change

NOW = datetime(2026, 9, 20, tzinfo=timezone.utc)
def row(price, days):
    return {'price': price, 'observed_at': (NOW - timedelta(days=days)).isoformat() if days is not None else None}

def test_recent_drop_survives_metadata_refresh():
    result = recent_price_change([row(320000, 60), row(300000, 12), row(300000, 1)], NOW)
    assert result['amount'] == -20000
    assert result['percent'] == -6.2
    assert result['observed_at'] == row(300000, 12)['observed_at']

def test_old_change_does_not_become_recent_on_refresh():
    assert recent_price_change([row(320000, 90), row(300000, 31), row(300000, 0)], NOW) is None

def test_increase_and_window_boundary():
    assert recent_price_change([row(300000, 60), row(320000, 30)], NOW)['amount'] == 20000

def test_unknown_or_future_dates_do_not_claim_recent_change():
    for days in (None, -1):
        assert recent_price_change([row(320000, 60), row(300000, days)], NOW) is None

def test_first_observation_is_not_change():
    assert recent_price_change([row(300000, 0)], NOW) is None

def test_latest_change_replaces_earlier_event():
    result = recent_price_change([row(320000, 60), row(300000, 12), row(310000, 2)], NOW)
    assert result['previous_price'] == 300000
    assert result['amount'] == 10000
