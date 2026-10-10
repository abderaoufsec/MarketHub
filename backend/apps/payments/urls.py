from django.urls import path

from . import views

urlpatterns = [
    # Transaction endpoints
    path("transactions/", views.TransactionListView.as_view(), name="transaction-list"),
    # Payment simulation endpoints
    path("simulate/", views.simulate_payment, name="simulate-payment"),
    path("refund/<int:order_id>/", views.process_payment_refund, name="process-refund"),
    path("status/<int:order_id>/", views.payment_status, name="payment-status"),
    # Seller commission endpoints
    path(
        "seller/commissions/", views.SellerCommissionListView.as_view(), name="seller-commissions"
    ),
]
