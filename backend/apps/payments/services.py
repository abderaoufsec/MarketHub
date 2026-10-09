import uuid
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from .models import Transaction, PlatformCommissionLedger


def process_simulated_payment(order):
    """
    Simulate payment processing for MVP
    
    Args:
        order: Order instance
    
    Returns:
        dict: Payment result with success status and transaction details
    """
    try:
        with transaction.atomic():
            # Generate unique transaction ID
            transaction_id = f"SIM-{uuid.uuid4().hex[:12].upper()}"
            
            # Create transaction record
            payment_transaction = Transaction.objects.create(
                order=order,
                transaction_id=transaction_id,
                amount=order.total_amount,
                gateway_used='SIMULATED',
                payment_status='SUCCESSFUL'  # Simulated always succeeds
            )
            
            # Calculate platform commission
            commission_rate = Decimal(str(settings.PLATFORM_COMMISSION_RATE))
            commission_amount = order.total_amount * commission_rate
            net_payout = order.total_amount - commission_amount
            
            # Create commission ledger entry
            PlatformCommissionLedger.objects.create(
                transaction=payment_transaction,
                order_total=order.total_amount,
                commission_rate=commission_rate,
                commission_amount=commission_amount,
                net_payout_to_seller=net_payout,
                payout_status='PENDING'
            )
            
            return {
                'success': True,
                'transaction_id': transaction_id,
                'amount': float(order.total_amount),
                'commission': float(commission_amount),
                'net_payout': float(net_payout)
            }
    
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


def process_refund(order):
    """
    Process refund for an order (simulated)
    
    Args:
        order: Order instance
    
    Returns:
        dict: Refund result
    """
    try:
        # Get original transaction
        original_transaction = order.transactions.filter(
            payment_status='SUCCESSFUL'
        ).first()
        
        if not original_transaction:
            return {
                'success': False,
                'error': 'No successful transaction found for this order'
            }
        
        with transaction.atomic():
            # Create refund transaction
            refund_transaction_id = f"REF-{uuid.uuid4().hex[:12].upper()}"
            
            refund_transaction = Transaction.objects.create(
                order=order,
                transaction_id=refund_transaction_id,
                amount=-order.total_amount,  # Negative amount for refund
                gateway_used='SIMULATED',
                payment_status='SUCCESSFUL'
            )
            
            # Update commission ledger
            if hasattr(original_transaction, 'commission'):
                original_transaction.commission.payout_status = 'FAILED'
                original_transaction.commission.save()
            
            return {
                'success': True,
                'transaction_id': refund_transaction_id,
                'refund_amount': float(order.total_amount)
            }
    
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }
