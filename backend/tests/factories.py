"""Shared factory_boy factories for the backend test suite (Phase 3).

Every test should build its data through these factories instead of hand
rolled ``Model.objects.create()`` calls, so that new required fields only
break one place.
"""
from decimal import Decimal

import factory
from django.contrib.auth import get_user_model

from apps.inventory.models import Inventory, InventoryAuditLog
from apps.orders.models import Cart, CartItem, Order, OrderItem
from apps.payments.models import Transaction
from apps.products.models import Product, ProductImage, ProductReview, Wishlist
from apps.stores.models import Store
from apps.users.models import Address

User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f'buyer{n}@example.com')
    username = factory.Sequence(lambda n: f'user{n}')
    first_name = 'Test'
    last_name = 'User'
    # Default to a verified buyer so login-based tests are not blocked by the
    # email-verification flow. Registration tests override this.
    is_verified = True
    is_seller = False
    is_active = True

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        """Hash the raw password after the row is created."""
        raw = extracted or 'Str0ng!Passw0rd'
        self.set_password(raw)
        return raw


class SellerFactory(UserFactory):
    email = factory.Sequence(lambda n: f'seller{n}@example.com')
    is_seller = True


class StoreFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Store

    owner = factory.SubFactory(SellerFactory)
    store_name = factory.Sequence(lambda n: f'Store {n}')
    description = 'A store created by StoreFactory.'
    category = 'electronics'
    is_active = True


class ProductFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Product

    store = factory.SubFactory(StoreFactory)
    name = factory.Sequence(lambda n: f'Product {n}')
    description = 'A product created by ProductFactory.'
    base_price = Decimal('100.00')
    category = 'electronics'
    is_available = True
    low_stock_threshold = 5


class ProductImageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProductImage

    product = factory.SubFactory(ProductFactory)
    image_url = 'https://cdn.example.com/image.jpg'
    is_primary = True
    sort_order = 0


class ProductReviewFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProductReview

    product = factory.SubFactory(ProductFactory)
    user = factory.SubFactory(UserFactory)
    rating = 5
    comment = 'Great product.'
    is_approved = True


class WishlistFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Wishlist

    user = factory.SubFactory(UserFactory)
    product = factory.SubFactory(ProductFactory)


class InventoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Inventory

    product = factory.SubFactory(ProductFactory)
    attribute_config = factory.LazyFunction(dict)
    stock_quantity = 10


class InventoryAuditLogFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = InventoryAuditLog

    product = factory.SubFactory(ProductFactory)
    inventory = None
    quantity_delta = 1
    action_type = 'INITIAL_STOCK'
    reason = 'Seed stock'
    previous_quantity = 0
    new_quantity = 1


class AddressFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Address

    user = factory.SubFactory(UserFactory)
    address_line1 = '12 Rue de la Liberté'
    city = 'Blida'
    state_province = 'Blida'
    postal_code = '09000'
    country = 'DZ'
    is_default = True


class CartFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Cart

    user = factory.SubFactory(UserFactory)


class CartItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CartItem

    cart = factory.SubFactory(CartFactory)
    product = factory.SubFactory(ProductFactory)
    quantity = 1
    selected_attributes = factory.LazyFunction(dict)
    price_at_time_of_addition = Decimal('100.00')


class OrderFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Order

    user = factory.SubFactory(UserFactory)
    store = factory.SubFactory(StoreFactory)
    total_amount = Decimal('100.00')
    shipping_address = factory.SubFactory(AddressFactory)
    order_status = 'PENDING'
    payment_status = 'PENDING'


class OrderItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = OrderItem

    order = factory.SubFactory(OrderFactory)
    product = factory.SubFactory(ProductFactory)
    quantity = 1
    unit_price_at_purchase = Decimal('100.00')


class TransactionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Transaction

    order = factory.SubFactory(OrderFactory)
    transaction_id = factory.Sequence(lambda n: f'SIM-TEST{n:012d}')
    amount = Decimal('100.00')
    gateway_used = 'SIMULATED'
    payment_status = 'SUCCESSFUL'
