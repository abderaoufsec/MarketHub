from django.urls import path

from . import views

urlpatterns = [
    # Transaction endpoints
    path("transactions/", views.TransactionListView.as_view(), name="transaction-list"),
    # Payment simulation endpoints
    path("simulate/", views.simulate_payment, name="simulate-payment"),
    # Class-based since Phase 9: the view mixes in IdempotentPostMixin, which
    # needs to wrap ``post`` (see apps/payments/views.py).
    path("refund/<int:order_id>/", views.ProcessRefundView.as_view(), name="process-refund"),
    path("status/<int:order_id>/", views.payment_status, name="payment-status"),
    # Seller commission endpoints
    path(
        "seller/commissions/", views.SellerCommissionListView.as_view(), name="seller-commissions"
    ),
]
