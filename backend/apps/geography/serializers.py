from rest_framework import serializers

from .models import Commune, Wilaya


class WilayaSerializer(serializers.ModelSerializer):
    """Public wilaya payload for the location picker.

    ``name`` is the *display* name in the request's language (ar/fr/en — the
    ``Accept-Language`` header the SPA sends); the raw per-language names ride
    along so a client can render a fixed-language list without a second call.
    """

    name = serializers.CharField(source="display_name", read_only=True)

    class Meta:
        model = Wilaya
        fields = ["id", "code", "name", "name_fr", "name_ar", "name_en", "is_active"]
        read_only_fields = fields


class CommuneSerializer(serializers.ModelSerializer):
    """Public commune payload; ``wilaya`` is the wilaya *code*, not the id —
    codes are stable across environments, ids are not."""

    name = serializers.CharField(source="display_name", read_only=True)
    wilaya = serializers.CharField(source="wilaya.code", read_only=True)

    class Meta:
        model = Commune
        fields = ["id", "code", "name", "name_fr", "name_ar", "name_en", "wilaya", "is_active"]
        read_only_fields = fields
