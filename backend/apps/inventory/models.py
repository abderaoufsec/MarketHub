from django.db import models
from apps.products.models import Product

class Inventory(models.Model):
    """
    Tracks stock levels for products and their variations
    """
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='inventory')
    attribute_config = models.JSONField(default=dict, blank=True, null=True)
    stock_quantity = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'inventory'
        unique_together = ['product', 'attribute_config']
    
    def __str__(self):
        return f"{self.product.name} - Stock: {self.stock_quantity}"
    
    @property
    def is_in_stock(self):
        return self.stock_quantity > 0
    
    @property
    def is_low_stock(self):
        return 0 < self.stock_quantity <= self.product.low_stock_threshold


class InventoryAuditLog(models.Model):
    """
    Tracks all changes to inventory for accountability
    """
    ACTION_CHOICES = [
        ('SALE', 'Sale'),
        ('RETURN', 'Return'),
        ('MANUAL_ADJUSTMENT', 'Manual Adjustment'),
        ('INITIAL_STOCK', 'Initial Stock'),
        ('RESTOCK', 'Restock'),
    ]
    
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='inventory_logs')
    inventory = models.ForeignKey(Inventory, on_delete=models.CASCADE, related_name='audit_logs', null=True)
    quantity_delta = models.IntegerField(help_text='Positive for additions, negative for reductions')
    action_type = models.CharField(max_length=30, choices=ACTION_CHOICES)
    reason = models.TextField(blank=True, null=True)
    previous_quantity = models.IntegerField()
    new_quantity = models.IntegerField()
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'inventory_audit_log'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['product']),
        ]
    
    def __str__(self):
        return f"{self.product.name} - {self.action_type} ({self.quantity_delta})"
