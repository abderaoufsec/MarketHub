"""Email delivery for new chat messages (Phase 16).

Delivery is best-effort: a broken SMTP server must never turn "send message"
into a 500 after the message row was committed. Phase 22 replaces this direct
send with a queued task and a real notification centre; the function signature
stays the same.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.utils.translation import gettext as _
from django.utils.translation import override

from apps.users.email import recipient_language

logger = logging.getLogger("apps.messaging.notifications")


def _preview(message) -> str:
    if message.body:
        return message.body.strip()[:300]
    if message.kind == "IMAGE":
        return _("Sent a photo")
    if message.kind == "OFFER":
        return _("Sent a price offer")
    return _("New message")


def send_new_message_email(message) -> bool:
    """Email the recipient once. Returns False when skipped or delivery fails."""
    conversation = message.conversation
    recipient = conversation.other_user_for(message.sender)
    if recipient is None or not recipient.email:
        return False
    base = getattr(settings, "FRONTEND_URL", "http://localhost:3000").rstrip("/")
    link = f"{base}/messages/{conversation.pk}"
    sender_name = message.sender.get_full_name() or message.sender.username
    listing = conversation.listing
    try:
        with override(recipient_language(recipient)):
            send_mail(
                _("New message about {listing}").format(listing=listing.name),
                _(
                    "{sender} sent you a message about {listing}:\n\n"
                    "{preview}\n\n"
                    "Reply here: {link}\n\n"
                    "Stay safe: never pay in advance or share verification codes."
                ).format(
                    sender=sender_name,
                    listing=listing.name,
                    preview=_preview(message),
                    link=link,
                ),
                settings.DEFAULT_FROM_EMAIL,
                [recipient.email],
                fail_silently=False,
            )
        return True
    except Exception:
        logger.exception("new-message email failed for message %s", message.pk)
        return False
