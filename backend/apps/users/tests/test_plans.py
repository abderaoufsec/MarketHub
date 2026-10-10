"""Plan-based listing quotas (stub introduced in Phase 2, real plans in 21)."""
import pytest
from django.test import override_settings

from apps.users import plans
from tests.factories import SellerFactory, UserFactory

pytestmark = pytest.mark.django_db


def test_default_plan_is_free():
    assert plans.get_plan(UserFactory()) == plans.FREE
    assert plans.get_plan(None) == plans.FREE


def test_free_plan_quota_follows_settings():
    user = UserFactory()

    with override_settings(MAX_PRODUCTS_PER_SELLER=3):
        assert plans.get_product_quota(user) == 3
        assert plans.can_create_product(user, 2) is True
        assert plans.can_create_product(user, 3) is False


def test_business_plan_is_unlimited():
    user = UserFactory()
    user.plan = plans.BUSINESS

    assert plans.get_product_quota(user) is None
    assert plans.can_create_product(user, 10_000) is True


def test_unknown_plan_falls_back_to_free_quota():
    user = UserFactory()
    user.plan = 'enterprise'

    with override_settings(MAX_PRODUCTS_PER_SELLER=7):
        assert plans.get_product_quota(user) == 7


def test_plan_choices_cover_all_codes():
    assert {code for code, _ in plans.PLAN_CHOICES} == {
        plans.FREE,
        plans.PRO,
        plans.BUSINESS,
    }
    assert plans.get_product_quota(SellerFactory()) == plans.get_product_quota(
        UserFactory()
    )
