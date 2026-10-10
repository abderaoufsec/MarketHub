from django.db import transaction
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.inventory.services import reserve_inventory_for_order
from apps.payments.services import process_simulated_payment
from apps.products.models import Product
from apps.users.models import Address

from .models import Cart, CartItem, Order, OrderItem
from .serializers import (
    AddToCartSerializer,
    CartItemSerializer,
    CartSerializer,
    CheckoutSerializer,
    OrderSerializer,
)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_cart(request):
    """Get user's cart"""
    cart, _created = Cart.objects.get_or_create(user=request.user)
    serializer = CartSerializer(cart)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_to_cart(request):
    """Add item to cart"""
    serializer = AddToCartSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    cart, _created = Cart.objects.get_or_create(user=request.user)

    product = Product.objects.get(id=serializer.validated_data["product_id"])
    quantity = serializer.validated_data["quantity"]
    selected_attributes = serializer.validated_data.get("selected_attributes", {})

    # Check if item already in cart
    cart_item, item_created = CartItem.objects.get_or_create(
        cart=cart,
        product=product,
        selected_attributes=selected_attributes,
        defaults={"quantity": quantity, "price_at_time_of_addition": product.base_price},
    )

    if not item_created:
        # Update quantity if item already exists
        cart_item.quantity += quantity
        cart_item.save()

    return Response(
        CartItemSerializer(cart_item).data,
        status=status.HTTP_201_CREATED if item_created else status.HTTP_200_OK,
    )


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def update_cart_item(request, item_id):
    """Update cart item quantity"""
    try:
        cart_item = CartItem.objects.get(id=item_id, cart__user=request.user)
    except CartItem.DoesNotExist:
        return Response({"error": "Cart item not found"}, status=status.HTTP_404_NOT_FOUND)

    quantity = request.data.get("quantity")
    if not quantity or int(quantity) < 1:
        return Response({"error": "Invalid quantity"}, status=status.HTTP_400_BAD_REQUEST)

    cart_item.quantity = int(quantity)
    cart_item.save()

    return Response(CartItemSerializer(cart_item).data)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def remove_cart_item(request, item_id):
    """Remove item from cart"""
    try:
        cart_item = CartItem.objects.get(id=item_id, cart__user=request.user)
        cart_item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    except CartItem.DoesNotExist:
        return Response({"error": "Cart item not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def clear_cart(request):
    """Clear all items from cart"""
    try:
        cart = Cart.objects.get(user=request.user)
        cart.items.all().delete()
        return Response({"message": "Cart cleared"}, status=status.HTTP_200_OK)
    except Cart.DoesNotExist:
        return Response({"message": "Cart is already empty"}, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def checkout(request):
    """Process checkout and create order"""
    serializer = CheckoutSerializer(data=request.data, context={"request": request})
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    try:
        cart = Cart.objects.get(user=request.user)
    except Cart.DoesNotExist:
        return Response({"error": "Cart is empty"}, status=status.HTTP_400_BAD_REQUEST)

    if not cart.items.exists():
        return Response({"error": "Cart is empty"}, status=status.HTTP_400_BAD_REQUEST)

    # Group items by store
    items_by_store = {}
    for item in cart.items.all():
        store = item.product.store
        if store.id not in items_by_store:
            items_by_store[store.id] = {"store": store, "items": []}
        items_by_store[store.id]["items"].append(item)

    # Get shipping address
    shipping_address = Address.objects.get(
        id=serializer.validated_data["shipping_address_id"], user=request.user
    )

    orders = []

    with transaction.atomic():
        # Create order for each store
        for store_data in items_by_store.values():
            store = store_data["store"]
            items = store_data["items"]

            # Calculate total
            total_amount = sum(item.subtotal for item in items)

            # Create order
            order = Order.objects.create(
                user=request.user,
                store=store,
                total_amount=total_amount,
                shipping_address=shipping_address,
                shipping_method=serializer.validated_data.get("shipping_method", "standard"),
                order_status="PENDING",
                payment_status="PENDING",
            )

            # Create order items and prepare inventory data
            inventory_items = []
            for cart_item in items:
                OrderItem.objects.create(
                    order=order,
                    product=cart_item.product,
                    quantity=cart_item.quantity,
                    unit_price_at_purchase=cart_item.price_at_time_of_addition,
                    selected_attributes=cart_item.selected_attributes,
                )

                inventory_items.append(
                    {
                        "product": cart_item.product,
                        "quantity": cart_item.quantity,
                        "selected_attributes": cart_item.selected_attributes,
                    }
                )

            # Reserve inventory
            try:
                reserve_inventory_for_order(inventory_items)
            except ValueError as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

            # Process payment (simulated)
            payment_result = process_simulated_payment(order)

            if payment_result["success"]:
                order.payment_status = "SUCCESSFUL"
                order.order_status = "PROCESSING"
                order.save()
            else:
                order.payment_status = "FAILED"
                order.save()
                return Response(
                    {"error": "Payment failed", "details": payment_result.get("error")},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            orders.append(order)

        # Clear cart after successful checkout
        cart.items.all().delete()

    return Response(
        {
            "message": "Order(s) placed successfully",
            "orders": OrderSerializer(orders, many=True).data,
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


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def update_order_status(request, order_id):
    """Update order status (seller only)"""
    if not request.user.is_seller or not hasattr(request.user, "store"):
        return Response(
            {"error": "Only sellers can update order status"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        order = Order.objects.get(id=order_id, store=request.user.store)
    except Order.DoesNotExist:
        return Response({"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND)

    new_status = request.data.get("order_status")
    tracking_number = request.data.get("tracking_number")

    if new_status:
        if new_status not in dict(Order.STATUS_CHOICES):
            return Response({"error": "Invalid order status"}, status=status.HTTP_400_BAD_REQUEST)
        order.order_status = new_status

    if tracking_number:
        order.tracking_number = tracking_number

    order.save()

    return Response(OrderSerializer(order).data)
