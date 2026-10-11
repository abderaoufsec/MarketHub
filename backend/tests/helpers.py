"""Shared test helpers."""

from contextlib import contextmanager

from rest_framework.throttling import SimpleRateThrottle

_MISSING = object()


@contextmanager
def throttle_rate(scope: str, rate: str):
    """Temporarily set the throttle rate for one scope.

    DRF's ``SimpleRateThrottle`` snapshots ``DEFAULT_THROTTLE_RATES`` into a
    *class attribute* at import time, so ``override_settings`` never reaches
    it — the only way to change a rate mid-test is to mutate the very dict
    the throttle reads (which is the settings dict itself).
    """
    rates = SimpleRateThrottle.THROTTLE_RATES
    previous = rates.get(scope, _MISSING)
    rates[scope] = rate
    try:
        yield
    finally:
        if previous is _MISSING:
            rates.pop(scope, None)
        else:
            rates[scope] = previous
