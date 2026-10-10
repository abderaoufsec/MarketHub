from django.db import models

from apps.orders.models import Order


class Transaction(models.Model):
    """Records payment attempts and confirmations"""

    PAYMENT_STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("SUCCESSFUL", "Successful"),
        ("FAILED", "Failed"),
    ]

    GATEWAY_CHOICES = [
        ("SIMULATED", "Simulated"),
        ("STRIPE", "Stripe"),
        ("PAYPAL", "PayPal"),
    ]

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="transactions")
    transaction_id = models.CharField(max_length=255, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    gateway_used = models.CharField(max_length=50, choices=GATEWAY_CHOICES, default="SIMULATED")
    payment_status = models.CharField(
        max_length=20, choices=PAYMENT_STATUS_CHOICES, default="PENDING"
    )
    transaction_timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "transactions"
        ordering = ["-transaction_timestamp"]
        indexes = [
            models.Index(fields=["-transaction_timestamp"]),
            models.Index(fields=["payment_status"]),
        ]

    def __str__(self):
        return f"Transaction {self.transaction_id} - {self.payment_status}"


class PlatformCommissionLedger(models.Model):
    """Records platform's commission from transactions"""

    PAYOUT_STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("PAID", "Paid"),
        ("FAILED", "Failed"),
    ]

    transaction = models.OneToOneField(
        Transaction, on_delete=models.CASCADE, related_name="commission"
    )
    order_total = models.DecimalField(max_digits=10, decimal_places=2)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=4)
    commission_amount = models.DecimalField(max_digits=10, decimal_places=2)
    net_payout_to_seller = models.DecimalField(max_digits=10, decimal_places=2)
    payout_status = models.CharField(
        max_length=20, choices=PAYOUT_STATUS_CHOICES, default="PENDING"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "platform_commission_ledger"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Commission for Transaction {self.transaction.transaction_id}"
