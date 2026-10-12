"""Order endpoints (docs/todo.md Phase 6).

The views only translate HTTP ⇄ domain calls. Checkout itself lives in
``apps.orders.services.place_order``: it runs in one transaction and reports
failures by raising, so a rejected checkout can never commit an order.

Phase 9: every failure is **raised**, never returned as a hand-built
``{"error": …}`` dict — ``core.exceptions.api_exception_handler`` renders it
as the ``{code, message, details, request_id}`` envelope all ``/api/`` failures
share. Status codes are unchanged; only the body shape moved.
"""

from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.products.models import Product
from apps.users.permissions import IsStoreOwner
from core.exceptions import ApiError
from core.idempotency import idempotency_key

from .exceptions import InsufficientStockError, ProductUnavailableError
from .models import Cart, CartItem, Order
from .serializers import (
    AddToCartSerializer,
    CartItemSerializer,
    CartSerializer,
    CheckoutSerializer,
    OrderSerializer,
    UpdateCartItemSerializer,
)
from .services import place_order, refresh_cart_prices, stock_error_for


def _ensure_sellable(product, quantity, attributes):
    """Raise ``insufficient_stock`` when ``quantity`` units cannot be sold.

    Called before any cart write: an unsellable quantity must not create or
    grow a cart line that checkout would only reject later. Returns ``None``
    when the quantity *can* be sold. (Phase 9: this used to hand back a
    ``{"error": …, "code": "insufficient_stock"}`` Response; the envelope now
    comes from raising the same code the client already branches on.)
    """
    message = stock_error_for(product, attributes, quantity)
    if message is not None:
        raise InsufficientStockError(message)


@extend_schema(responses={200: CartSerializer})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_cart(request):
    """Get user's cart"""
    cart, _created = Cart.objects.get_or_create(user=request.user)
    serializer = CartSerializer(cart)
    return Response(serializer.data)


@extend_schema(
    request=AddToCartSerializer,
    responses={200: CartItemSerializer, 201: CartItemSerializer},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_to_cart(request):
    """Add item to cart"""
    serializer = AddToCartSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    cart, _created = Cart.objects.get_or_create(user=request.user)

    # The serializer already validated existence + availability; re-read with
    # the same filter so a product deleted mid-request answers 400, not 500.
    product = Product.objects.filter(
        id=serializer.validated_data["product_id"], is_available=True
    ).first()
    if product is None:
        raise ProductUnavailableError("Product not found or not available")

    quantity = serializer.validated_data["quantity"]
    selected_attributes = serializer.validated_data.get("selected_attributes", {}) or {}

    existing = CartItem.objects.filter(
        cart=cart, product=product, selected_attributes=selected_attributes
    ).first()
    desired_quantity = (existing.quantity if existing else 0) + quantity

    # Validate before writing (raises for an unsellable quantity).
    _ensure_sellable(product, desired_quantity, selected_attributes)

    if existing is not None:
        existing.quantity = desired_quantity
        existing.save(update_fields=["quantity", "updated_at"])
        return Response(CartItemSerializer(existing).data, status=status.HTTP_200_OK)

    cart_item = CartItem.objects.create(
        cart=cart,
        product=product,
        quantity=quantity,
        selected_attributes=selected_attributes,
        price_at_time_of_addition=product.base_price,
    )
    return Response(CartItemSerializer(cart_item).data, status=status.HTTP_201_CREATED)


@extend_schema(request=UpdateCartItemSerializer, responses={200: CartItemSerializer})
@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def update_cart_item(request, item_id):
    """Update cart item quantity"""
    try:
        cart_item = CartItem.objects.select_related("product").get(
            id=item_id, cart__user=request.user
        )
    except CartItem.DoesNotExist:
        # ``from None``: the DoesNotExist is an implementation detail of the
        # lookup, not a cause the client or the error log needs to chain to.
        raise NotFound("Cart item not found", code="cart_item_not_found") from None

    serializer = UpdateCartItemSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    quantity = serializer.validated_data["quantity"]

    _ensure_sellable(cart_item.product, quantity, cart_item.selected_attributes or {})

    cart_item.quantity = quantity
    cart_item.save(update_fields=["quantity", "updated_at"])

    return Response(CartItemSerializer(cart_item).data)


@extend_schema(responses={204: None})
@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def remove_cart_item(request, item_id):
    """Remove item from cart"""
    try:
        cart_item = CartItem.objects.get(id=item_id, cart__user=request.user)
    except CartItem.DoesNotExist:
        raise NotFound("Cart item not found", code="cart_item_not_found") from None

    cart_item.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(responses={200: OpenApiTypes.OBJECT})
@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def clear_cart(request):
    """Clear all items from cart"""
    try:
        cart = Cart.objects.get(user=request.user)
    except Cart.DoesNotExist:
        # Clearing an already-empty cart is a 200, not a failure: the buyer
        # got the state they asked for either way.
        return Response({"message": "Cart is already empty"}, status=status.HTTP_200_OK)

    cart.items.all().delete()
    return Response({"message": "Cart cleared"}, status=status.HTTP_200_OK)


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def update_cart_prices(request):
    """Accept the current catalogue prices for the buyer's cart.

    Checkout refuses to charge a stale price (docs/todo.md Phase 6); this is
    the recovery endpoint the "price changed" UI calls before retrying.
    """
    cart, _created = Cart.objects.get_or_create(user=request.user)
    updated = refresh_cart_prices(request.user)
    cart.refresh_from_db()
    return Response(
        {"updated": updated, "cart": CartSerializer(cart).data},
        status=status.HTTP_200_OK,
    )


@extend_schema(request=CheckoutSerializer, responses={201: OpenApiTypes.OBJECT})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def checkout(request):
    """Process checkout and create order(s).

    Payment happens here, inside the same transaction as the order and the
    stock reservation: there is a single authoritative payment path, and a
    failure anywhere leaves nothing behind. The ``Idempotency-Key`` header —
    or the Phase 6 body field of the same name — makes a retried request
    return the orders it already created instead of charging again.
    """
    serializer = CheckoutSerializer(data=request.data, context={"request": request})
    serializer.is_valid(raise_exception=True)

    # The standard header wins over the body field (core.idempotency), so a
    # client that only sends the header is replay-safe too. Domain failures
    # (empty_cart, price_changed, …) now propagate to the Phase 9 handler
    # instead of being caught here — the atomic block they exit still rolls
    # the whole checkout back.
    key = idempotency_key(request, body_value=serializer.validated_data.get("idempotency_key"))

    orders, is_replay = place_order(
        user=request.user,
        shipping_address_id=serializer.validated_data["shipping_address_id"],
        shipping_method=serializer.validated_data.get("shipping_method", "standard"),
        idempotency_key=key,
    )

    return Response(
        {
            "message": "Order(s) placed successfully",
            "orders": OrderSerializer(orders, many=True).data,
            "idempotent_replay": is_replay,
        },
        status=status.HTTP_201_CREATED,
    )


class OrderListView(generics.ListAPIView):
    """List user's orders"""

    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Order.objects.filter(user=self.request.user)
            .prefetch_related("items", "items__product")
            .select_related("store", "shipping_address")
        )


class OrderDetailView(generics.RetrieveAPIView):
    """Get order details"""

    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Order.objects.filter(user=self.request.user)
            .prefetch_related("items", "items__product")
            .select_related("store", "shipping_address")
        )


class SellerOrderListView(generics.ListAPIView):
    """List orders for seller's store"""

    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if not self.request.user.is_seller or not hasattr(self.request.user, "store"):
            return Order.objects.none()

        return (
            Order.objects.filter(store=self.request.user.store)
            .prefetch_related("items", "items__product")
            .select_related("shipping_address")
        )


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: OrderSerializer})
@api_view(["PUT"])
@permission_classes([IsAuthenticated, IsStoreOwner])
def update_order_status(request, order_id):
    """Update order status (own store only — enforced by ``IsStoreOwner``)."""
    try:
        order = Order.objects.get(id=order_id, store=request.user.store)
    except Order.DoesNotExist:
        raise NotFound("Order not found", code="order_not_found") from None

    new_status = request.data.get("order_status")
    tracking_number = request.data.get("tracking_number")

    if new_status:
        if new_status not in dict(Order.STATUS_CHOICES):
            raise ApiError("Invalid order status", code="invalid_order_status")
        order.order_status = new_status

    if tracking_number:
        order.tracking_number = tracking_number

    order.save()

    return Response(OrderSerializer(order).data)
