"""Catalogue and search filters, shared by the list, search and feed views.

Phase 12 put the category/attribute filters in ``products.views``; Phase 15
made them a first-class part of search (facets need to re-run the pipeline
while excluding one filter) and moved them here. The public behaviour is
unchanged - the same query parameters, the same 400s on typos - so this is a
move, not a rewrite.

Filter groups are named so a facet can ask for "everything except me":

``category``, ``location``, ``price``, ``attributes``, ``condition``,
``seller_type``, ``verified``, ``photos``, ``posted``, ``in_stock``.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db.models import DecimalField, Exists, OuterRef, Q
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import ValidationError

from apps.catalog.models import AttributeDefinition, Category

from .models import ProductImage

NUMERIC_ATTRIBUTE_TYPES = {AttributeDefinition.Type.NUMBER, AttributeDefinition.Type.YEAR}

#: Casts of ``attributes_json`` values need an explicit precision: a bare
#: ``DecimalField()`` renders ``CAST(… AS numeric(None, None))``, which
#: PostgreSQL rejects outright ("invalid input syntax for type integer:
#: none" - it reads the ``None`` modifiers as input). 20 digits is far beyond
#: any attribute value; 6 decimals keeps fractional bounds exact.
ATTRIBUTE_DECIMAL_FIELD = DecimalField(max_digits=20, decimal_places=6)

POSTED_WINDOWS = {
    "today": timedelta(days=1),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


def apply_category_filter(queryset, query_params):
    """``?category=<slug>`` matches the node and every descendant.

    An unknown or deactivated slug yields an empty page, not a 404 - a stale
    bookmark should not error. Returns ``(queryset, subtree_ids)``: the
    attribute filter needs the subtree, and ``None`` means "no category
    filter" (any filterable definition is valid).
    """
    category_slug = query_params.get("category")
    if not category_slug:
        return queryset, None
    root = Category.objects.filter(slug=category_slug, is_active=True).first()
    subtree_ids = (
        list(root.get_descendants(include_self=True).values_list("id", flat=True))
        if root is not None
        else []
    )
    return queryset.filter(category_id__in=subtree_ids), subtree_ids


def apply_attribute_filters(queryset, query_params, subtree_ids=None, skip_key=None):
    """``?attr_<key>=``, ``?attr_<key>_min=``, ``?attr_<key>_max=``.

    Unknown or non-filterable keys raise a 400 instead of being ignored: a
    typo'd filter that silently returns everything is a bug report weeks
    later. ``skip_key`` lets a facet count the values of one attribute without
    its own selection (the usual "OR inside a facet" behaviour).
    """
    definitions = AttributeDefinition.objects.filter(is_active=True, filterable=True)
    if subtree_ids is not None:
        definitions = definitions.filter(category_id__in=subtree_ids)
    filterable = {definition.key: definition for definition in definitions}

    for param, raw_value in query_params.items():
        if not param.startswith("attr_"):
            continue
        body = param[len("attr_") :]
        modifier = ""
        for candidate in ("_min", "_max"):
            if body.endswith(candidate):
                body, modifier = body[: -len(candidate)], candidate

        definition = filterable.get(body)
        if definition is None:
            raise ValidationError(
                {param: _("Unknown or non-filterable attribute for this category.")}
            )
        if skip_key is not None and body == skip_key:
            continue

        if not modifier:
            if definition.type in NUMERIC_ATTRIBUTE_TYPES:
                # The query string is text; comparing it to the stored jsonb
                # *number* would be string ≠ number forever. Compare through
                # the same numeric cast the bounds use - an unparseable value
                # falls through to the jsonb exact match, which never equals a
                # number, so a bogus filter yields an empty page, not a 500.
                try:
                    number = Decimal(raw_value)
                except InvalidOperation:
                    number = None
                if number is not None:
                    exact_alias = f"attr_{body}_exact"
                    queryset = queryset.annotate(
                        **{
                            exact_alias: Cast(
                                KeyTextTransform(body, "attributes_json"),
                                ATTRIBUTE_DECIMAL_FIELD,
                            )
                        }
                    )
                    queryset = queryset.filter(**{exact_alias: number})
                    continue
            value = raw_value
            if definition.type == AttributeDefinition.Type.BOOLEAN:
                if raw_value not in ("true", "false"):
                    raise ValidationError({param: _("Must be true or false.")})
                value = raw_value == "true"
            queryset = queryset.filter(**{f"attributes_json__{body}": value})
            continue

        # Numeric / range bounds: cast the stored jsonb and compare. The cast
        # must be *annotated* - `filter(low__lte=…)` names a field or an
        # annotation, never a local variable - and each modifier gets its own
        # alias so `?attr_x_min=` and `?attr_x_max=` in one request do not
        # collide on a duplicate annotation name.
        if definition.type == AttributeDefinition.Type.RANGE:
            low_alias = f"attr_{body}{modifier}_low"
            high_alias = f"attr_{body}{modifier}_high"
            queryset = queryset.annotate(
                **{
                    low_alias: Cast(
                        KeyTextTransform("min", KeyTextTransform(body, "attributes_json")),
                        ATTRIBUTE_DECIMAL_FIELD,
                    ),
                    high_alias: Cast(
                        KeyTextTransform("max", KeyTextTransform(body, "attributes_json")),
                        ATTRIBUTE_DECIMAL_FIELD,
                    ),
                }
            )
            # Overlap: the posting's range intersects [min, max].
            queryset = (
                queryset.filter(**{f"{high_alias}__gte": raw_value})
                if modifier == "_min"
                else queryset.filter(**{f"{low_alias}__lte": raw_value})
            )
            continue

        if definition.type not in NUMERIC_ATTRIBUTE_TYPES:
            raise ValidationError(
                {param: _("Only number, year and range attributes accept bounds.")}
            )
        numeric_alias = f"attr_{body}{modifier}_value"
        queryset = queryset.annotate(
            **{
                numeric_alias: Cast(
                    KeyTextTransform(body, "attributes_json"), ATTRIBUTE_DECIMAL_FIELD
                ),
            }
        )
        queryset = (
            queryset.filter(**{f"{numeric_alias}__gte": raw_value})
            if modifier == "_min"
            else queryset.filter(**{f"{numeric_alias}__lte": raw_value})
        )

    return queryset


def apply_catalog_filters(queryset, query_params, skip_category=False, skip_attr=None):
    """Category subtree + dynamic attributes - the Phase 12 contract."""
    queryset, subtree_ids = (
        (queryset, None) if skip_category else apply_category_filter(queryset, query_params)
    )
    return apply_attribute_filters(queryset, query_params, subtree_ids, skip_key=skip_attr)


def apply_location_filters(queryset, query_params):
    """Phase 13 location filters: ``?wilaya=<id>`` and ``?commune=<id>``.

    Same philosophy as ``?category=``: an unknown id yields an empty page,
    and a non-numeric one (a stale bookmark, a hand-edited URL) yields an
    empty page too rather than a 500 from the ORM's int cast - the filter
    form is the thing that must be correct, not every link that ever carried
    the parameter.
    """
    wilaya = query_params.get("wilaya")
    commune = query_params.get("commune")
    if wilaya is not None:
        queryset = queryset.filter(wilaya_id=int(wilaya)) if wilaya.isdigit() else queryset.none()
    if commune is not None:
        queryset = (
            queryset.filter(commune_id=int(commune)) if commune.isdigit() else queryset.none()
        )
    return queryset


def apply_price_filters(queryset, query_params):
    """``?min_price=`` / ``?max_price=``, tolerant of non-numeric input."""
    for param, lookup in (("min_price", "base_price__gte"), ("max_price", "base_price__lte")):
        raw = query_params.get(param)
        if raw in (None, ""):
            continue
        try:
            value = Decimal(raw)
        except InvalidOperation:
            raise ValidationError({param: _("Enter a valid price.")}) from None
        queryset = queryset.filter(**{lookup: value})
    return queryset


def apply_condition_filter(queryset, query_params):
    """``?condition=new|used|…`` - a first-class alias for the attribute.

    Condition is defined per category in Phase 12 (a phone's "Comme neuf", a
    car's "Occasion"), so it is stored in ``attributes_json.condition``. The
    facet and the filter share this one key; unknown values return an empty
    page, not a 400: the values are category data, not an API enum.
    """
    condition = query_params.get("condition")
    if condition:
        queryset = queryset.filter(attributes_json__condition=condition)
    return queryset


def apply_seller_type_filter(queryset, query_params):
    """``?seller_type=store|individual``."""
    seller_type = query_params.get("seller_type")
    if not seller_type:
        return queryset
    if seller_type == "store":
        return queryset.filter(store__isnull=False)
    if seller_type == "individual":
        return queryset.filter(store__isnull=True)
    raise ValidationError({"seller_type": _("Must be store or individual.")})


def apply_verified_filter(queryset, query_params):
    """``?verified=true`` - the seller proved an email or a phone (Phase 8)."""
    verified = parse_bool(query_params, "verified")
    if verified is None:
        return queryset
    predicate = Q(seller__phone_verified_at__isnull=False) | Q(seller__is_verified=True)
    return queryset.filter(predicate) if verified else queryset.exclude(predicate)


def apply_photos_filter(queryset, query_params):
    """``?with_photos=true`` - at least one photo, via EXISTS (no join)."""
    with_photos = parse_bool(query_params, "with_photos")
    if with_photos is None:
        return queryset
    exists = Exists(ProductImage.objects.filter(product=OuterRef("pk")))
    return queryset.filter(exists) if with_photos else queryset.filter(~exists)


def apply_posted_filter(queryset, query_params):
    """``?posted=today|7d|30d``."""
    posted = query_params.get("posted")
    if not posted:
        return queryset
    window = POSTED_WINDOWS.get(posted)
    if window is None:
        raise ValidationError({"posted": _("Must be today, 7d or 30d.")})
    return queryset.filter(created_at__gte=timezone.now() - window)


def apply_in_stock_filter(queryset, query_params):
    """``?in_stock=true`` - store products with stock left.

    Classifieds have no inventory rows; asking for stock excludes them by
    definition, which is why the UI offers this only as an explicit choice
    and never as a default.
    """
    in_stock = parse_bool(query_params, "in_stock")
    if in_stock is None or not in_stock:
        return queryset
    if "total_stock" not in queryset.query.annotations:
        queryset = queryset.with_stock()
    return queryset.filter(total_stock__gt=0)


def apply_search_filters(queryset, query_params, skip=(), skip_attr=None):
    """Apply every non-text filter; ``skip`` names groups to leave out.

    ``skip_attr`` is the attribute key a facet is counting: its own selection
    is ignored while every other filter still applies (OR inside a facet).
    """
    queryset = apply_catalog_filters(
        queryset,
        query_params,
        skip_category="category" in skip,
        skip_attr=skip_attr,
    )
    if "location" not in skip:
        queryset = apply_location_filters(queryset, query_params)
    if "price" not in skip:
        queryset = apply_price_filters(queryset, query_params)
    if "condition" not in skip:
        queryset = apply_condition_filter(queryset, query_params)
    if "seller_type" not in skip:
        queryset = apply_seller_type_filter(queryset, query_params)
    if "verified" not in skip:
        queryset = apply_verified_filter(queryset, query_params)
    if "photos" not in skip:
        queryset = apply_photos_filter(queryset, query_params)
    if "posted" not in skip:
        queryset = apply_posted_filter(queryset, query_params)
    if "in_stock" not in skip:
        queryset = apply_in_stock_filter(queryset, query_params)
    return queryset


def parse_bool(query_params, name):
    """``None`` when absent; a bool when ``true``/``false``; 400 otherwise."""
    raw = query_params.get(name)
    if raw is None or raw == "":
        return None
    if raw == "true":
        return True
    if raw == "false":
        return False
    raise ValidationError({name: _("Must be true or false.")})
