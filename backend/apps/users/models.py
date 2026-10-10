import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    """
    Custom User model extending Django's AbstractUser.
    Supports both Buyer and Seller roles.
    """

    email = models.EmailField(_("email address"), unique=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    is_seller = models.BooleanField(
        default=False, help_text="Designates whether this user is a seller"
    )
    is_verified = models.BooleanField(
        default=False, help_text="Designates whether email is verified"
    )
    profile_picture = models.URLField(blank=True, null=True, help_text="Profile picture URL")
    bio = models.TextField(blank=True, null=True, help_text="User biography")

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username", "first_name", "last_name"]

    class Meta:
        db_table = "users"
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["is_seller"]),
        ]

    def __str__(self):
        return self.email


class Address(models.Model):
    """
    Model to store shipping and billing addresses for users.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="addresses")
    address_line1 = models.CharField(max_length=255)
    address_line2 = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100)
    state_province = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "addresses"
        verbose_name_plural = "Addresses"
        ordering = ["-is_default", "-created_at"]

    def __str__(self):
        return f"{self.user.email} - {self.city}, {self.country}"

    def save(self, *args, **kwargs):
        # Ensure only one default address per user
        if self.is_default:
            Address.objects.filter(user=self.user, is_default=True).update(is_default=False)
        super().save(*args, **kwargs)


class EmailVerificationToken(models.Model):
    """
    Model to store email verification tokens for users.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="verification_tokens")
    token = models.CharField(max_length=64, unique=True, default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    class Meta:
        db_table = "email_verification_tokens"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} - {self.token[:10]}..."

    def is_expired(self):
        return timezone.now() > self.expires_at
