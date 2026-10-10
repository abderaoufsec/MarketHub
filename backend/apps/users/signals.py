from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import EmailVerificationToken, User


@receiver(post_save, sender=User)
def send_verification_email(sender, instance, created, **kwargs):
    """
    Send verification email when a new user is created.
    """
    if created and not instance.is_verified:
        # Create verification token
        expires_at = timezone.now() + timedelta(hours=24)
        token = EmailVerificationToken.objects.create(user=instance, expires_at=expires_at)

        # Send verification email
        verification_url = f"{settings.SITE_URL}/verify-email/{token.token}"
        subject = "Verify your MarketHub account"
        message = f"""
        Hello {instance.get_full_name()},

        Thank you for registering with MarketHub!

        Please verify your email address by clicking the link below:
        {verification_url}

        This link will expire in 24 hours.

        If you didn't create this account, please ignore this email.

        Best regards,
        The MarketHub Team
        """

        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [instance.email],
            fail_silently=True,
        )
