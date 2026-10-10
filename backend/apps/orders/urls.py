from django.urls import path

from . import views

urlpatterns = [
    # Cart endpoints
    path("cart/", views.get_cart, name="cart-get"),
    path("cart/add/", views.add_to_cart, name="cart-add"),
    path("cart/items/<int:item_id>/", views.update_cart_item, name="cart-item-update"),
    path("cart/items/<int:item_id>/remove/", views.remove_cart_item, name="cart-item-remove"),
    path("cart/clear/", views.clear_cart, name="cart-clear"),
    # Checkout
    path("checkout/", views.checkout, name="checkout"),
    # Buyer order endpoints
    path("", views.OrderListView.as_view(), name="order-list"),
    path("<int:pk>/", views.OrderDetailView.as_view(), name="order-detail"),
    # Seller order endpoints
    path("seller/list/", views.SellerOrderListView.as_view(), name="seller-order-list"),
    path(
        "seller/<int:order_id>/update-status/",
        views.update_order_status,
        name="order-update-status",
    ),
]
