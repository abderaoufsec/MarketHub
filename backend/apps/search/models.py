"""Saved searches, alerts and search analytics (Phase 15 of docs/todo.md).

Two persistent facts make search a product rather than a text box:

* :class:`SavedSearch` - the filters a buyer wants to keep watching, the
  delivery channels and cadence. ``params`` is the same query-string dict the
  search endpoint accepts, so replaying an alert is just re-running search.
* :class:`SearchQuery` - what people searched for and whether it found
  anything. Zero-result rows are the synonym backlog (Phase 25 reads them),
  and recent rows power the autocomplete for signed-in buyers.

Nothing here stores free text from a listing: analytics are aggregate and
attributable to an account (or anonymous), never to a person's browsing
history beyond their own searches.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class SavedSearch(models.Model):
    """One user's saved query plus how they want to hear about new matches."""

    class Frequency(models.TextChoices):
        INSTANT = "INSTANT", "Instant"
        DAILY = "DAILY", "Daily digest"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="saved_searches",
    )
    name = models.CharField(max_length=120, blank=True)
    #: The canonical query params (no cursor/page_size). Values are strings so
    #: a saved search is exactly a URL someone can share.
    params = models.JSONField(default=dict)
    frequency = models.CharField(max_length=10, choices=Frequency.choices, default=Frequency.DAILY)
    notify_email = models.BooleanField(default=True)
    notify_sms = models.BooleanField(default=False)
    notify_whatsapp = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    last_notified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "saved_searches"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="saved_search_user_newest"),
            models.Index(fields=["is_active", "frequency"], name="saved_search_active_frequency"),
        ]

    def __str__(self) -> str:
        return self.name or f"Saved search #{self.pk}"

    @property
    def query_string(self) -> str:
        """``a=1&b=2`` for linking straight back into ``/search``."""
        from urllib.parse import urlencode

        return urlencode(
            {key: value for key, value in self.params.items() if value not in (None, "")}
        )

    @property
    def has_channel(self) -> bool:
        return self.notify_email or self.notify_sms or self.notify_whatsapp


class SearchQuery(models.Model):
    """One search request, stored for suggestions and the synonym backlog."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="search_queries",
    )
    #: What was typed (trimmed, original script) and its normalized form.
    query = models.CharField(max_length=200, blank=True)
    normalized = models.CharField(max_length=200, blank=True)
    filters = models.JSONField(default=dict, blank=True)
    result_count = models.PositiveIntegerField(default=0)
    zero_results = models.BooleanField(default=False)
    locale = models.CharField(max_length=8, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "search_queries"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"], name="search_query_newest"),
            models.Index(fields=["normalized"], name="search_query_normalized"),
            models.Index(fields=["zero_results", "-created_at"], name="search_query_zero_newest"),
        ]

    def __str__(self) -> str:
        return self.query or "(filters only)"
