from rest_framework import serializers

from core.i18n import choice_label

from .models import PlatformCommissionLedger, Transaction


class TransactionSerializer(serializers.ModelSerializer):
    """Serializer for Transaction model"""

    payment_status_label = serializers.SerializerMethodField()
    gateway_used_label = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = [
            "id",
            "order",
            "transaction_id",
            "amount",
            "gateway_used",
            "gateway_used_label",
            "payment_status",
            "payment_status_label",
            "transaction_timestamp",
        ]
        read_only_fields = ["id", "transaction_timestamp"]

    def get_payment_status_label(self, obj) -> str:
        return choice_label(Transaction.PAYMENT_STATUS_CHOICES, obj.payment_status)

    def get_gateway_used_label(self, obj) -> str:
        return choice_label(Transaction.GATEWAY_CHOICES, obj.gateway_used)


class PlatformCommissionLedgerSerializer(serializers.ModelSerializer):
    """Serializer for PlatformCommissionLedger model"""

    transaction_id = serializers.CharField(source="transaction.transaction_id", read_only=True)
    payout_status_label = serializers.SerializerMethodField()

    class Meta:
        model = PlatformCommissionLedger
        fields = [
            "id",
            "transaction",
            "transaction_id",
            "order_total",
            "commission_rate",
            "commission_amount",
            "net_payout_to_seller",
            "payout_status",
            "payout_status_label",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_payout_status_label(self, obj) -> str:
        return choice_label(PlatformCommissionLedger.PAYOUT_STATUS_CHOICES, obj.payout_status)
