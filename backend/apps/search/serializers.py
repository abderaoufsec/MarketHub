"""Serializers for the search API, saved searches and analytics rows."""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.products.serializers import (
    ProductListSerializer,
    ProductSearchPageSerializer,
)

from .models import SavedSearch, SearchQuery
from .services import get_search_service


class SearchResultSerializer(ProductListSerializer):
    """A catalogue card plus the distance the distance sort computed.

    ``distance_km`` is only present when the request sorted by distance; the
    annotation lives on the queryset, not the model, so every other endpoint
    keeps the exact card shape it had before Phase 15.
    """

    distance_km = serializers.SerializerMethodField()

    class Meta(ProductListSerializer.Meta):
        fields = [*ProductListSerializer.Meta.fields, "distance_km"]

    def get_distance_km(self, obj):
        metres = getattr(obj, "distance_m", None)
        return round(metres / 1000, 1) if metres is not None else None


class SearchMetaSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    sort = serializers.CharField()
    q = serializers.CharField(allow_blank=True)
    did_you_mean = serializers.CharField(allow_blank=True)
    used_fuzzy = serializers.BooleanField()
    relaxations = serializers.ListField(child=serializers.DictField())
    nearby_wilayas = serializers.ListField(child=serializers.DictField())
    filters = serializers.DictField()


class SearchPageSerializer(ProductSearchPageSerializer):
    results = SearchResultSerializer(many=True, read_only=True)
    facets = serializers.DictField()
    meta = SearchMetaSerializer()


class SavedSearchSerializer(serializers.ModelSerializer):
    """CRUD for a saved search.

    ``params`` is the search query-string as JSON; it is canonicalized through
    the *same* service validation the endpoint uses, so an alert can never
    store a filter the search page would reject. Defaults (daily digest,
    email) make the safe choice when the client sends only ``params``.
    """

    query_string = serializers.CharField(read_only=True)

    class Meta:
        model = SavedSearch
        fields = [
            "id",
            "name",
            "params",
            "frequency",
            "notify_email",
            "notify_sms",
            "notify_whatsapp",
            "is_active",
            "last_notified_at",
            "created_at",
            "updated_at",
            "query_string",
        ]
        read_only_fields = ["id", "last_notified_at", "created_at", "updated_at"]

    def validate_params(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError(_("Params must be an object."))
        try:
            return get_search_service().normalize_params(value)
        except serializers.ValidationError:
            raise
        except Exception as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate(self, attrs):
        attrs = super().validate(attrs)
        user = self.instance.user if self.instance is not None else self.context["request"].user
        email = attrs.get("notify_email", self.instance.notify_email if self.instance else True)
        sms = attrs.get("notify_sms", self.instance.notify_sms if self.instance else False)
        whatsapp = attrs.get(
            "notify_whatsapp", self.instance.notify_whatsapp if self.instance else False
        )
        if not (email or sms or whatsapp):
            raise serializers.ValidationError(
                {"notify_email": "Choose at least one delivery channel."}
            )
        if email and not user.email:
            raise serializers.ValidationError(
                {"notify_email": "Add an email address to your account first."}
            )
        if (sms or whatsapp) and not getattr(user, "phone_number", ""):
            raise serializers.ValidationError(
                {"notify_sms": "Add a phone number to your account first."}
            )
        return attrs


class SearchQuerySerializer(serializers.ModelSerializer):
    class Meta:
        model = SearchQuery
        fields = ["id", "query", "filters", "result_count", "zero_results", "created_at"]
        read_only_fields = fields


class SuggestionProductSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    canonical_path = serializers.CharField()
    primary_image = serializers.CharField(allow_null=True)
    category = serializers.CharField(allow_null=True)


class CategorySuggestionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    slug = serializers.SlugField()
    name = serializers.CharField()
