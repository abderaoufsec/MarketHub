"""Root pytest configuration and shared fixtures for the backend test suite.

The suite runs against the **same PostgreSQL configuration as the app**
(never SQLite): later phases rely on Postgres features such as full-text
search, ``select_for_update()`` and trigram indexes. pytest-django creates a
dedicated ``test_<DB_NAME>`` database for every run.

Environment: tests read the same configuration as the application
(`backend/.env.local` or exported variables — see `backend/.env.example`).
"""

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from tests.factories import (
    AddressFactory,
    InventoryFactory,
    ProductFactory,
    SellerFactory,
    StoreFactory,
    UserFactory,
)


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------
@pytest.fixture
def api_client() -> APIClient:
    """Unauthenticated DRF test client."""
    return APIClient()


@pytest.fixture
def buyer(db):
    """A verified, non-seller user."""
    return UserFactory()


@pytest.fixture
def seller(db):
    """A verified user with the seller flag (no store yet)."""
    return SellerFactory()


@pytest.fixture
def store(db, seller):
    """An active store owned by the ``seller`` fixture."""
    return StoreFactory(owner=seller)


@pytest.fixture
def product(db, store):
    """A product that belongs to the ``store`` fixture."""
    return ProductFactory(store=store)


@pytest.fixture
def inventory(db, product):
    """10 units of stock for the ``product`` fixture."""
    return InventoryFactory(product=product, stock_quantity=10)


@pytest.fixture
def address(db, buyer):
    """A default shipping address for the ``buyer`` fixture."""
    return AddressFactory(user=buyer)


@pytest.fixture
def buyer_client(buyer):
    """DRF client authenticated as the ``buyer`` fixture.

    Each authenticated client gets its *own* APIClient instance: sharing one
    would make the last ``force_authenticate`` call win for every fixture,
    silently re-authenticating tests that use both a buyer and a seller.
    """
    client = APIClient()
    client.force_authenticate(user=buyer)
    return client


@pytest.fixture
def seller_client(seller):
    """DRF client authenticated as the ``seller`` fixture (owner of ``store``)."""
    client = APIClient()
    client.force_authenticate(user=seller)
    return client


# ---------------------------------------------------------------------------
# Test-environment guards (Phase 7)
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_rate_limit_state():
    """DRF throttling and the failed-login backoff share the Django cache.

    Clearing it before every test keeps rate-limited endpoints order-
    independent: the suite runs in one process, so a leftover counter from a
    previous test would otherwise produce spurious 429s.
    """
    cache.clear()


@pytest.fixture(autouse=True)
def _disable_ssl_redirect(settings):
    """With ``DEBUG=false`` (the CI posture) ``SECURE_SSL_REDIRECT`` is on,
    but the test client speaks plain HTTP and would be 301-redirected away
    from every endpoint. Production redirection is asserted in
    ``core/test_settings_config.py`` instead.
    """
    settings.SECURE_SSL_REDIRECT = False
