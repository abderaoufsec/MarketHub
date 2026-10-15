"""Category tree and dynamic attribute definitions (Phase 12 of docs/todo.md).

This is where classifieds sites win or lose: a "Cars" listing form must ask
for year/km/gearbox, a "Jobs" one for contract/salary — generated from data,
not from a hardcoded form per category.

- :class:`Category` — a translated tree (``django-mptt``) of the launch
  categories, seeded from ``fixtures/categories.json`` by ``manage.py
  load_categories``. Editing it in the admin changes the posting form and the
  filters with no deploy.
- :class:`AttributeDefinition` — the fields a category asks for: key, type
  (text/number/enum/boolean/year/range), labels in fr/ar/en, choices for
  enums, ``required`` for the form and ``filterable`` for the search
  sidebar. Values are stored per product in ``Product.attributes_json``
  (JSONB, GIN-indexed) and validated against the *effective* definitions —
  this category's plus every ancestor's, deeper overriding the same key — by
  :func:`apps.catalog.validation.validate_attributes`.

`Product.category` and `Store.category` became foreign keys to
:class:`Category` in this phase; the migrations map the legacy free-text
values by slug/name and leave unmatched rows ``NULL`` for the admin to fix.
"""

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from mptt.models import MPTTModel, TreeForeignKey

KEY_VALIDATOR = RegexValidator(
    r"^[a-z][a-z0-9_]*$",
    "Keys are lower_snake_case: start with a letter, then letters/digits/underscores.",
)


class Category(MPTTModel):
    """One node of the category tree.

    Names live in three columns (fr/ar/en) like the geography app's
    ``Wilaya``: ``display_name`` follows the request's ``Accept-Language``,
    French is the fallback and the guaranteed-complete language.
    ``django-mptt`` maintains ``lft``/``rght``/``tree_id``/``level`` and
    answers ``get_descendants()``/``get_ancestors()`` in one query each —
    the subtree filter on the catalogue and the inherited-attribute merge
    below both rely on it.
    """

    slug = models.SlugField(max_length=100, unique=True)
    name_fr = models.CharField(max_length=100)
    name_ar = models.CharField(max_length=100)
    name_en = models.CharField(max_length=100, blank=True)
    parent = TreeForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )
    # Icon *name* the SPA maps to a lucide component — no binary assets in a
    # reference table that admins edit.
    icon = models.CharField(max_length=64, blank=True)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class MPTTMeta:
        parent_attr = "parent"
        order_insertion_by = ["order", "slug"]

    class Meta:
        db_table = "categories"
        verbose_name = "Category"
        verbose_name_plural = "Categories"
        ordering = ["tree_id", "lft"]

    def __str__(self):
        return f"{self.name_fr} ({self.slug})"

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

    def effective_attribute_definitions(self):
        """Active definitions that apply to this category, ordered for a form.

        The form for a node asks for *its own* fields plus every ancestor's
        ("Cars" inherits brand/model/year from "Vehicles"). When the same
        ``key`` appears on several levels the **deeper** definition wins — a
        child can re-type or relax an inherited field, which is how real
        category trees customize their parents.

        One query: the ancestors' ids come from mptt's cached tree fields.
        """
        ids = [self.id, *list(self.get_ancestors().values_list("id", flat=True))]
        definitions = AttributeDefinition.objects.filter(
            category_id__in=ids, is_active=True
        ).select_related("category")
        # Shallow first so deeper definitions overwrite on key collision.
        by_key = {}
        for definition in sorted(definitions, key=lambda d: d.category.level):
            by_key[definition.key] = definition
        return sorted(by_key.values(), key=lambda d: (d.order, d.key))


class AttributeDefinition(models.Model):
    """One dynamic field a category asks for.

    ``key`` is what lands in ``Product.attributes_json`` and in the
    ``?attr_<key>=`` filter, so it is immutable-ish (unique per category) and
    lower_snake_case. Labels follow the same three-column pattern as
    ``Category``. ``choices`` is only meaningful for ``enum``: a list of
    ``{"value", "label_fr", "label_ar", "label_en"}`` dicts — values are the
    machine contract, labels are UI.
    """

    class Type(models.TextChoices):
        TEXT = "text", "Text"
        NUMBER = "number", "Number"
        ENUM = "enum", "Enum"
        BOOLEAN = "boolean", "Boolean"
        YEAR = "year", "Year"
        RANGE = "range", "Range"

    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name="attribute_definitions"
    )
    key = models.CharField(max_length=64, validators=[KEY_VALIDATOR])
    label_fr = models.CharField(max_length=100)
    label_ar = models.CharField(max_length=100)
    label_en = models.CharField(max_length=100, blank=True)
    type = models.CharField(max_length=16, choices=Type.choices)
    required = models.BooleanField(default=False)
    filterable = models.BooleanField(default=False)
    # Display hint only ("km", "m²", "DA/an"); never parsed.
    unit = models.CharField(max_length=16, blank=True)
    choices = models.JSONField(default=list, blank=True)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "attribute_definitions"
        verbose_name = "Attribute definition"
        verbose_name_plural = "Attribute definitions"
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["category", "key"], name="unique_attribute_key_per_category"
            )
        ]
        indexes = [
            # The effective-definitions query filters by category ids.
            models.Index(fields=["category", "is_active"], name="attrdefs_category_active"),
        ]

    def __str__(self):
        return f"{self.category.slug}.{self.key} ({self.type})"

    @property
    def display_label(self) -> str:
        """Label in the active request language, falling back to French."""
        from django.utils.translation import get_language

        lang = (get_language() or "fr").split("-")[0]
        if lang == "ar":
            return self.label_ar
        if lang == "en" and self.label_en:
            return self.label_en
        return self.label_fr

    def clean(self):
        """Structural rules the *values* validation in services.py cannot see.

        Raised as ``ValidationError`` so both the admin form and a future
        serializer share one rule set.
        """
        errors = {}
        try:
            KEY_VALIDATOR(self.key)
        except ValidationError as exc:
            errors["key"] = exc.messages

        if self.type == self.Type.ENUM:
            if not self.choices:
                errors["choices"] = "An enum attribute needs at least one choice."
            else:
                values = [choice.get("value") for choice in self.choices]
                if any(not value for value in values):
                    errors["choices"] = "Every choice needs a non-empty 'value'."
                elif len(values) != len(set(values)):
                    errors["choices"] = "Choice values must be unique."
                elif any(not isinstance(value, str) for value in values):
                    errors["choices"] = "Choice values must be strings."
        elif self.choices:
            errors["choices"] = "Only enum attributes may define choices."

        if errors:
            raise ValidationError(errors)
