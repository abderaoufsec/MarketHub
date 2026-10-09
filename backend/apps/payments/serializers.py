from rest_framework import serializers
from .models import Transaction, PlatformCommissionLedger


class TransactionSerializer(serializers.ModelSerializer):
    """Serializer for Transaction model"""
    
    class Meta:
        model = Transaction
        fields = ['id', 'order', 'transaction_id', 'amount', 'gateway_used',
                  'payment_status', 'transaction_timestamp']
        read_only_fields = ['id', 'transaction_timestamp']


class PlatformCommissionLedgerSerializer(serializers.ModelSerializer):
    """Serializer for PlatformCommissionLedger model"""
    transaction_id = serializers.CharField(source='transaction.transaction_id', read_only=True)
    
    class Meta:
        model = PlatformCommissionLedger
        fields = ['id', 'transaction', 'transaction_id', 'order_total',
                  'commission_rate', 'commission_amount', 'net_payout_to_seller',
                  'payout_status', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
