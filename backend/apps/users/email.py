"""Verification and recovery email — Phase 8 of docs/todo.md.

**One flow only.** Registration used to send *two* incompatible emails: the
view built a ``uidb64/token`` link against ``FRONTEND_URL`` while a
``post_save`` receiver built a raw-uuid link against ``SITE_URL`` that no view
ever accepted (docs/todo.md §0.3). The receiver is gone; every verification
email now comes from :func:`send_verification_email`.

**Delivery is never fatal.** An SMTP outage must not turn a successful
registration or password reset into a 500 — each helper logs the failure and
returns ``False`` so the caller can carry on (the user can always press
"resend").
"""

import logging
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

logger = logging.getLogger("apps.users.email")


def _encode_user(user) -> str:
    return urlsafe_base64_encode(force_bytes(user.pk))


def email_verification_url(user) -> str:
    """``/verify-email/<uidb64>/<token>/`` on the frontend (GET link)."""
    token = default_token_generator.make_token(user)
    return f"{settings.FRONTEND_URL}/verify-email/{_encode_user(user)}/{token}/"


def password_reset_url(user) -> str:
    """``/reset-password/?uid=…&token=…`` on the frontend (GET link)."""
    query = urlencode(
        {"uid": _encode_user(user), "token": default_token_generator.make_token(user)}
    )
    return f"{settings.FRONTEND_URL}/reset-password/?{query}"


def _send(subject: str, message: str, recipient: str) -> bool:
    if not recipient:
        return False
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
        return True
    except Exception:  # an SMTP outage must never fail the request (BLE001 is
        # reviewed + globally allowed here: this is exactly the case it exists for)
        logger.exception("email delivery failed (to=%s subject=%r)", recipient, subject)
        return False


def send_verification_email(user) -> bool:
    """Send the single account-verification link. Non-fatal."""
    if not user.email or user.is_verified:
        return False
    link = email_verification_url(user)
    name = user.get_full_name() or user.username
    return _send(
        "Verify your MarketHub account",
        (
            f"Hello {name},\n\n"
            "Please confirm your email address to activate your MarketHub account:\n"
            f"{link}\n\n"
            "The link expires in 24 hours. If you did not create this account, "
            "you can ignore this message."
        ),
        user.email,
    )


def send_password_reset_email(user) -> bool:
    """Send the password-recovery link. Non-fatal."""
    link = password_reset_url(user)
    name = user.get_full_name() or user.username
    return _send(
        "Reset your MarketHub password",
        (
            f"Hello {name},\n\n"
            "Someone asked to reset the password of your MarketHub account:\n"
            f"{link}\n\n"
            "Choose a new password within 24 hours — the link stops working "
            "after that, and also as soon as the password changes. If this "
            "was not you, ignore this message and nothing changes."
        ),
        user.email,
    )


def send_password_changed_email(user) -> bool:
    """Security notice sent after any password change/reset. Non-fatal."""
    return _send(
        "Your MarketHub password was changed",
        (
            "Hello,\n\n"
            "The password of your MarketHub account was just changed. "
            "If this was not you, reset your password immediately and "
            "contact support@markethub.example."
        ),
        user.email,
    )
