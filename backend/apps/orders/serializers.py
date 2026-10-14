from rest_framework import serializers

from apps.products.serializers import ProductListSerializer
from apps.users.serializers import AddressSerializer
from core.i18n import choice_label

from .models import Cart, CartItem, Order, OrderItem


class CartItemSerializer(serializers.ModelSerializer):
    """Serializer for CartItem model"""

    product = ProductListSerializer(read_only=True)
    product_id = serializers.IntegerField(write_only=True)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = CartItem
        fields = [
            "id",
            "product",
            "product_id",
            "quantity",
            "selected_attributes",
            "price_at_time_of_addition",
            "subtotal",
            "created_at",
        ]
        read_only_fields = ["id", "price_at_time_of_addition", "created_at"]


class CartSerializer(serializers.ModelSerializer):
    """Serializer for Cart model"""

    items = CartItemSerializer(many=True, read_only=True)
    total_items = serializers.IntegerField(read_only=True)
    total_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Cart
        fields = ["id", "items", "total_items", "total_price", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class AddToCartSerializer(serializers.Serializer):
    """Serializer for adding items to cart"""

    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, default=1)
    selected_attributes = serializers.JSONField(default=dict, required=False)

    def validate_product_id(self, value):
        from apps.products.models import Product

        if not Product.objects.filter(id=value, is_available=True).exists():
            raise serializers.ValidationError("Product not found or not available")
        return value


class UpdateCartItemSerializer(serializers.Serializer):
    """Serializer for changing the quantity of an existing cart line.

    ``int(quantity)`` on raw input (docs/todo.md §0.3 #2) turned "lots" into an
    HTTP 500; DRF answers 400 with a field error instead.
    """

    quantity = serializers.IntegerField(min_value=1)


class OrderItemSerializer(serializers.ModelSerializer):
    """Serializer for OrderItem model"""

    product_name = serializers.CharField(source="product.name", read_only=True)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "product",
            "product_name",
            "quantity",
            "unit_price_at_purchase",
            "selected_attributes",
            "subtotal",
        ]


class OrderSerializer(serializers.ModelSerializer):
    """Serializer for Order model

    Phase 11: the raw status values stay (``order_status``/``payment_status``
    are what code branches on); the ``*_label`` twins are translated per
    request language via ``Accept-Language``.
    """

    items = OrderItemSerializer(many=True, read_only=True)
    shipping_address = AddressSerializer(read_only=True)
    store_name = serializers.CharField(source="store.store_name", read_only=True)
    order_status_label = serializers.SerializerMethodField()
    payment_status_label = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "user",
            "store",
            "store_name",
            "order_date",
            "total_amount",
            "shipping_address",
            "order_status",
            "order_status_label",
            "payment_status",
            "payment_status_label",
            "shipping_method",
            "tracking_number",
            "items",
        ]
        read_only_fields = ["id", "user", "store", "order_date"]

    def get_order_status_label(self, obj) -> str:
        return choice_label(Order.STATUS_CHOICES, obj.order_status)

    def get_payment_status_label(self, obj) -> str:
        return choice_label(Order.PAYMENT_STATUS_CHOICES, obj.payment_status)


class CheckoutSerializer(serializers.Serializer):
    """Serializer for checkout process"""

    shipping_address_id = serializers.IntegerField()
    shipping_method = serializers.CharField(max_length=100, required=False, default="standard")
    # Makes a retried checkout safe: sending the same key twice returns the
    # orders that were already created instead of charging the buyer again.
    idempotency_key = serializers.CharField(max_length=64, required=False, allow_blank=True)

    def validate_shipping_address_id(self, value):
        from apps.users.models import Address

        user = self.context["request"].user

        # docs/todo.md §0.3 #3: the raw Address.objects.get() in the view used
        # to raise DoesNotExist -> HTTP 500 for a foreign or unknown address.
        # Scoping the lookup to the buyer makes it a 400 here; ``place_order``
        # re-checks the same condition before it writes anything.
        if not Address.objects.filter(id=value, user=user).exists():
            raise serializers.ValidationError("Shipping address not found")

        return value
