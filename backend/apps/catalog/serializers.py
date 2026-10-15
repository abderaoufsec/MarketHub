from rest_framework import serializers

from .models import AttributeDefinition, Category


class AttributeChoiceSerializer(serializers.Serializer):
    """One enum choice: machine ``value`` + the three UI labels."""

    value = serializers.CharField(read_only=True)
    label = serializers.SerializerMethodField()
    label_fr = serializers.CharField(read_only=True)
    label_ar = serializers.CharField(read_only=True)
    label_en = serializers.CharField(read_only=True)

    def get_label(self, obj) -> str:
        """Label in the request's language (fr fallback), like ``name``."""
        from django.utils.translation import get_language

        lang = (get_language() or "fr").split("-")[0]
        if lang == "ar":
            return obj.get("label_ar") or obj.get("label_fr", "")
        if lang == "en":
            return obj.get("label_en") or obj.get("label_fr", "")
        return obj.get("label_fr", "")


class AttributeDefinitionSerializer(serializers.ModelSerializer):
    """Public payload for the dynamic form and the filter sidebar.

    ``label`` follows ``Accept-Language`` (the SPA sends it from the locale
    cookie since Phase 11), the raw per-language labels ride along for a
    fixed-language render without a second call.
    """

    label = serializers.CharField(source="display_label", read_only=True)
    choices = AttributeChoiceSerializer(many=True, read_only=True)

    class Meta:
        model = AttributeDefinition
        fields = [
            "id",
            "key",
            "label",
            "label_fr",
            "label_ar",
            "label_en",
            "type",
            "required",
            "filterable",
            "unit",
            "choices",
            "order",
        ]
        read_only_fields = fields


class CategorySerializer(serializers.ModelSerializer):
    """One node of the tree, recursively.

    Children and this node's *own* attribute definitions are inlined: the
    seed tree is small (tens of nodes) and the posting form wants the whole
    picture in one call. Inheritance is applied client-side from the tree —
    see ``Category.effective_attribute_definitions`` for the server-side
    twin used for validation.
    """

    name = serializers.CharField(source="display_name", read_only=True)
    children = serializers.SerializerMethodField()
    attribute_definitions = AttributeDefinitionSerializer(many=True, read_only=True)
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            "id",
            "slug",
            "name",
            "name_fr",
            "name_ar",
            "name_en",
            "icon",
            "order",
            "children",
            "attribute_definitions",
            "product_count",
        ]
        read_only_fields = fields

    def get_children(self, obj) -> list:
        """Active children only — deactivating a node hides its whole
        subtree from the public tree without deleting anyone's data."""
        children = [child for child in obj.children.all() if child.is_active]
        serializer = CategorySerializer(children, many=True)
        return serializer.data

    def get_product_count(self, obj) -> int:
        """Products in this category *and its descendants*.

        Served from a prefetched ``descendant_product_count`` annotation when
        the view supplies one (the public tree endpoint does — one extra
        query, not one per node); ``0`` on an un-annotated instance rather
        than a query storm.
        """
        return getattr(obj, "descendant_product_count", 0)


class CategoryMiniSerializer(serializers.ModelSerializer):
    """The nested ``category`` object on product/store payloads.

    Deliberately tiny: the tree endpoint exists for anything that needs the
    whole shape.
    """

    name = serializers.CharField(source="display_name", read_only=True)

    class Meta:
        model = Category
        fields = ["id", "slug", "name"]
        read_only_fields = fields
