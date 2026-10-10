import logging

from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Transaction, PlatformCommissionLedger
from .serializers import TransactionSerializer, PlatformCommissionLedgerSerializer
from .services import process_simulated_payment, process_refund
from apps.orders.models import Order

logger = logging.getLogger(__name__)


class TransactionListView(generics.ListAPIView):
    """List transactions for user's orders"""
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Transaction.objects.filter(
            order__user=self.request.user
        ).select_related('order').order_by('-transaction_timestamp')


class SellerCommissionListView(generics.ListAPIView):
    """List commission records for seller"""
    serializer_class = PlatformCommissionLedgerSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        if not self.request.user.is_seller or not hasattr(self.request.user, 'store'):
            return PlatformCommissionLedger.objects.none()
        
        return PlatformCommissionLedger.objects.filter(
            transaction__order__store=self.request.user.store
        ).select_related('transaction', 'transaction__order').order_by('-created_at')


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def simulate_payment(request):
    """
    Simulate payment processing for an order
    
    Expected payload:
    {
        "order_id": 123,
        "payment_method": "credit_card"  # optional, for demonstration
    }
    """
    order_id = request.data.get('order_id')
    payment_method = request.data.get('payment_method', 'credit_card')
    
    if not order_id:
        return Response(
            {'error': 'order_id is required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Get the order
        order = Order.objects.get(id=order_id, user=request.user)
        
        # Check if order is already paid
        if order.payment_status == 'SUCCESSFUL':
            return Response(
                {'error': 'Order has already been paid'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if order is cancelled
        if order.order_status == 'CANCELLED':
            return Response(
                {'error': 'Cannot process payment for cancelled order'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Process simulated payment
        result = process_simulated_payment(order)
        
        if result['success']:
            # Update order payment status
            order.payment_status = 'SUCCESSFUL'
            order.order_status = 'PROCESSING'
            order.save()
            
            return Response(
                {
                    'message': 'Payment processed successfully',
                    'transaction_id': result['transaction_id'],
                    'amount_paid': result['amount'],
                    'commission': result['commission'],
                    'net_to_seller': result['net_payout'],
                    'payment_method': payment_method,
                    'order': {
                        'id': order.id,
                        'status': order.order_status,
                        'payment_status': order.payment_status
                    }
                },
                status=status.HTTP_200_OK
            )
        else:
            logger.error('Simulated payment failed for order %s: %s', order_id, result.get('error'))
            return Response(
                {'error': 'Payment processing failed. Please try again.'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    except Order.DoesNotExist:
        return Response(
            {'error': 'Order not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception:
        # Never expose internal error details to the client; log them instead.
        logger.exception('Unexpected error while handling payment request for order %s', order_id)
        return Response(
            {'error': 'An unexpected error occurred while processing the payment.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def process_payment_refund(request, order_id):
    """
    Process refund for an order
    Only order owner can request refund
    """
    try:
        order = Order.objects.get(id=order_id, user=request.user)
        
        # Check if order can be refunded
        if order.payment_status != 'SUCCESSFUL':
            return Response(
                {'error': 'Order payment was not successful, cannot refund'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if order.order_status == 'DELIVERED':
            return Response(
                {'error': 'Cannot refund delivered orders. Please contact support.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Process refund
        result = process_refund(order)
        
        if result['success']:
            # Update order status
            order.payment_status = 'FAILED'  # Mark payment as failed after refund
            order.order_status = 'CANCELLED'
            order.save()
            
            return Response(
                {
                    'message': 'Refund processed successfully',
                    'transaction_id': result['transaction_id'],
                    'refund_amount': result['refund_amount'],
                    'order': {
                        'id': order.id,
                        'status': order.order_status,
                        'payment_status': order.payment_status
                    }
                },
                status=status.HTTP_200_OK
            )
        else:
            logger.error('Refund failed for order %s: %s', order_id, result.get('error'))
            return Response(
                {'error': 'Refund processing failed. Please contact support.'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    except Order.DoesNotExist:
        return Response(
            {'error': 'Order not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception:
        # Never expose internal error details to the client; log them instead.
        logger.exception('Unexpected error while handling payment request for order %s', order_id)
        return Response(
            {'error': 'An unexpected error occurred while processing the payment.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def payment_status(request, order_id):
    """
    Get payment status for an order
    """
    try:
        order = Order.objects.get(id=order_id, user=request.user)
        
        # Get transactions for this order
        transactions = Transaction.objects.filter(order=order).order_by('-transaction_timestamp')
        
        latest_transaction = transactions.first()
        
        return Response(
            {
                'order_id': order.id,
                'payment_status': order.payment_status,
                'order_status': order.order_status,
                'total_amount': float(order.total_amount),
                'latest_transaction': TransactionSerializer(latest_transaction).data if latest_transaction else None,
                'transaction_count': transactions.count()
            },
            status=status.HTTP_200_OK
        )
    
    except Order.DoesNotExist:
        return Response(
            {'error': 'Order not found'},
            status=status.HTTP_404_NOT_FOUND
        )
