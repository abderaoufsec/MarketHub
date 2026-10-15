from django.conf import settings
from django.db import models
from django.utils.text import slugify


class Store(models.Model):
    """
    Represents a seller's storefront.
    Each seller can have one store.
    """

    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="store",
        limit_choices_to={"is_seller": True},
    )
    store_name = models.CharField(max_length=200, unique=True)
    store_slug = models.SlugField(max_length=250, unique=True, db_index=True)
    description = models.TextField()
    # Phase 12: the 9 hardcoded CATEGORY_CHOICES became a FK into the catalog
    # tree (the data migration maps each legacy value onto its root
    # category). Nullable only for unmapped legacy rows; the API requires it
    # on create.
    category = models.ForeignKey(
        "catalog.Category",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="stores",
    )
    logo_url = models.URLField(blank=True, null=True)
    banner_image_url = models.URLField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "stores"
        ordering = ["-created_at"]
        indexes = [
            # The two real filters, each paired with the ordering every store
            # list uses. ``store_slug`` is dropped here: SlugField already
            # carries db_index=True, so this was a second index on the same
            # column that every store write had to maintain.
            models.Index(fields=["is_active", "-created_at"], name="stores_active_newest"),
            models.Index(fields=["category", "-created_at"], name="stores_category_newest"),
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
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="following_stores"
    )
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="followers")
    followed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "store_followers"
        unique_together = ["user", "store"]
        ordering = ["-followed_at"]

    def __str__(self):
        return f"{self.user.email} follows {self.store.store_name}"
