"""Algerian geography — wilayas and communes (Phase 11 of docs/todo.md).

Algeria's administrative map moves: 48 wilayas (1984-2019), 58 (2019), and
**69 since the November 2025 / Law 26-06 reform**. Free-text "city / state"
fields cannot follow that; this app makes location *data*, loaded from a
reviewed fixture (`fixtures/geography.json`) instead of being typed by users.
"""

from django.db import models


class Wilaya(models.Model):
    """One of Algeria's 69 wilayas (provinces).

    ``code`` is the official two-digit number ("01" Adrar … "69" El Abiodh
    Sidi Cheikh) kept as a string so leading zeros survive. ``name_en`` is
    optional: no authoritative English list exists, and French names are what
    the international audience already reads.
    """

    code = models.CharField(max_length=4, unique=True)
    name_fr = models.CharField(max_length=100)
    name_ar = models.CharField(max_length=100)
    name_en = models.CharField(max_length=100, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "wilayas"
        verbose_name = "Wilaya"
        verbose_name_plural = "Wilayas"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} — {self.name_fr}"

    @property
    def display_name(self) -> str:
        """Name in the active request language, falling back to French."""
        from django.utils.translation import get_language

        lang = (get_language() or "fr").split("-")[0]
        if lang == "ar":
            return self.name_ar
        if lang == "en" and self.name_en:
            return self.name_en
        return self.name_fr


class Commune(models.Model):
    """One of the 1,541 official communes (municipalities).

    ``code`` is internal (``<wilaya code><index>``) — the official commune
    numbering is not published in a machine-readable form yet. A commune name
    is only unique *within* a wilaya ("Sidi Khaled" exists more than once).
    """

    code = models.CharField(max_length=8, unique=True)
    name_fr = models.CharField(max_length=100)
    name_ar = models.CharField(max_length=100)
    name_en = models.CharField(max_length=100, blank=True)
    wilaya = models.ForeignKey(Wilaya, on_delete=models.PROTECT, related_name="communes")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "communes"
        verbose_name = "Commune"
        verbose_name_plural = "Communes"
        ordering = ["name_fr", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["wilaya", "name_fr"], name="unique_commune_name_per_wilaya"
            )
        ]

    def __str__(self):
        return f"{self.name_fr} ({self.wilaya.code})"

    @property
    def display_name(self) -> str:
        """Name in the active request language, falling back to French."""
        from django.utils.translation import get_language

        lang = (get_language() or "fr").split("-")[0]
        if lang == "ar":
            return self.name_ar
        if lang == "en" and self.name_en:
            return self.name_en
        return self.name_fr
