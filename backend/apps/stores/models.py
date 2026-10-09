from django.db import models
from django.utils.text import slugify
from django.conf import settings

class Store(models.Model):
    """
    Represents a seller's storefront.
    Each seller can have one store.
    """
    CATEGORY_CHOICES = [
        ('electronics', 'Electronics'),
        ('fashion', 'Fashion'),
        ('home', 'Home & Garden'),
        ('books', 'Books'),
        ('sports', 'Sports & Outdoors'),
        ('toys', 'Toys & Games'),
        ('food', 'Food & Beverages'),
        ('beauty', 'Beauty & Personal Care'),
        ('other', 'Other'),
    ]
    
    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='store',
        limit_choices_to={'is_seller': True}
    )
    store_name = models.CharField(max_length=200, unique=True)
    store_slug = models.SlugField(max_length=250, unique=True, db_index=True)
    description = models.TextField()
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    logo_url = models.URLField(blank=True, null=True)
    banner_image_url = models.URLField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'stores'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['store_slug']),
            models.Index(fields=['category']),
        ]
    
    def __str__(self):
        return self.store_name
    
    def save(self, *args, **kwargs):
        if not self.store_slug:
            self.store_slug = slugify(self.store_name)
        super().save(*args, **kwargs)


class StoreFollower(models.Model):
    """
    Model to track users following stores
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='following_stores'
    )
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='followers'
    )
    followed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'store_followers'
        unique_together = ['user', 'store']
        ordering = ['-followed_at']
    
    def __str__(self):
        return f"{self.user.email} follows {self.store.store_name}"
