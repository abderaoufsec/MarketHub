"""
Payments Admin Configuration - Safe Version
"""
from django.contrib import admin
from .models import Transaction, PlatformCommissionLedger


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    """Transaction Management Admin"""
    list_display = [
        'id',
        'transaction_id',
        'order',
        'amount',
        'gateway_used',
        'payment_status',
        'transaction_timestamp'
    ]
    list_filter = ['payment_status', 'gateway_used', 'transaction_timestamp']
    search_fields = ['transaction_id', 'order__id']
    ordering = ['-transaction_timestamp']
    readonly_fields = ['transaction_timestamp']


@admin.register(PlatformCommissionLedger)
class PlatformCommissionLedgerAdmin(admin.ModelAdmin):
    """Platform Commission Tracking Admin"""
    list_display = [
        'id',
        'transaction',
        'order_total',
        'commission_rate',
        'commission_amount',
        'net_payout_to_seller',
        'payout_status'
    ]
    list_filter = ['payout_status']
    search_fields = ['transaction__transaction_id', 'transaction__order__id']
    ordering = ['-id']
