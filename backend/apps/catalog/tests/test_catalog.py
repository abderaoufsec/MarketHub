"""Category tree, attribute validation and the dynamic-form contract (Phase 12).

Three layers, mirroring how the phase is wired:

1. **Model** — mptt tree operations and :meth:`Category.effective_attribute_definitions`
   (own + ancestors', deeper winning on key collision), ``display_name``
   following ``Accept-Language``.
2. **Validation** — :func:`apps.catalog.validation.validate_attributes`, the one
   rule set shared by the API, the admin and (later) the listing wizard. Strict
   by design: unknown keys rejected, inactive definitions ignored, booleans
   ``True``/``False`` only.
3. **API** — ``GET /api/v1/catalog/categories/`` (tree + localized labels +
   subtree product counts) and the product write contract (``category_id`` +
   ``attributes_json`` errors nested per key so the dynamic form can highlight
   the offending inputs).

``?category=`` subtree filtering and the ``?attr_*`` filter matrix live with
the rest of the catalogue filters in ``apps/products/tests/test_products.py``;
this module covers the pieces only the catalog app owns.
"""

import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.translation import override
from rest_framework.test import APIClient

from apps.catalog.models import AttributeDefinition, Category
from apps.catalog.validation import validate_attributes
from tests.factories import (
    AttributeDefinitionFactory,
    CategoryFactory,
    ProductFactory,
    SellerFactory,
    StoreFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

TREE_URL = "/api/v1/catalog/categories/"
SELLER_CREATE_URL = "/api/v1/products/seller/create/"


@pytest.fixture
def seller_client(db):
    """Authenticated client whose seller owns a store (product create needs one).

    The store rides along as ``client.store`` so tests can build products in
    *this* seller's store — using conftest's separate ``store`` fixture would
    authenticate a different owner and 403.
    """
    store = StoreFactory(owner=SellerFactory())
    client = APIClient()
    client.force_authenticate(user=store.owner)
    client.store = store
    return client


# ---------------------------------------------------------------------------
# Model: tree + effective definitions
# ---------------------------------------------------------------------------
def test_tree_walk_ancestors_and_descendants():
    vehicles = CategoryFactory(slug="vehicles")
    cars = CategoryFactory(slug="cars", parent=vehicles)
    suvs = CategoryFactory(slug="suv", parent=cars)

    assert list(cars.get_ancestors()) == [vehicles]
    assert set(suvs.get_descendants(include_self=True)) == {suvs}
    assert list(vehicles.get_descendants().values_list("id", flat=True)) == [cars.id, suvs.id]


def test_effective_definitions_inherit_from_ancestors():
    """A child form asks for its own fields *and* every ancestor's — the
    "Cars" form must include brand/model defined on "Vehicles"."""
    vehicles = CategoryFactory(slug="vehicles")
    cars = CategoryFactory(slug="cars", parent=vehicles)
    AttributeDefinitionFactory(category=vehicles, key="brand", type="text")
    AttributeDefinitionFactory(category=cars, key="mileage", type="number")

    keys = {definition.key for definition in cars.effective_attribute_definitions()}
    assert keys == {"brand", "mileage"}


def test_deeper_definition_wins_on_key_collision():
    """A child may re-type an inherited field: ``year`` on "Vehicles" becomes
    the child's own ``year`` definition with its stricter labels/limits."""
    vehicles = CategoryFactory(slug="vehicles")
    cars = CategoryFactory(slug="cars", parent=vehicles)
    parent_def = AttributeDefinitionFactory(
        category=vehicles, key="year", type="number", label_fr="Année (n'importe laquelle)"
    )
    child_def = AttributeDefinitionFactory(category=cars, key="year", type="year", label_fr="Année")

    effective = cars.effective_attribute_definitions()
    assert [definition.key for definition in effective] == ["year"]
    assert effective[0].id == child_def.id
    assert effective[0].type == AttributeDefinition.Type.YEAR
    assert parent_def.id != child_def.id


def test_effective_definitions_skip_inactive_nodes_and_defs():
    vehicles = CategoryFactory(slug="vehicles")
    cars = CategoryFactory(slug="cars", parent=vehicles)
    AttributeDefinitionFactory(category=vehicles, key="brand", is_active=False)
    AttributeDefinitionFactory(category=vehicles, key="fuel", is_active=True)

    keys = {definition.key for definition in cars.effective_attribute_definitions()}
    assert keys == {"fuel"}


def test_effective_definitions_are_ordered_for_a_form():
    """``order`` first, then key — a stable, admin-controlled render order."""
    category = CategoryFactory(slug="ordered")
    AttributeDefinitionFactory(category=category, key="zebra", order=0)
    AttributeDefinitionFactory(category=category, key="alpha", order=0)
    AttributeDefinitionFactory(category=category, key="middle", order=1)

    assert [definition.key for definition in category.effective_attribute_definitions()] == [
        "alpha",
        "zebra",
        "middle",
    ]


def test_display_name_follows_accept_language_with_french_fallback():
    # name_en blank by contract (the factory fills one, so pass it explicitly)
    category = CategoryFactory(slug="phones", name_fr="Téléphones", name_ar="هواتف", name_en="")

    with override("fr"):
        assert category.display_name == "Téléphones"
    with override("ar"):
        assert category.display_name == "هواتف"
    # name_en is blank → French fallback, never a hole.
    with override("en"):
        assert category.display_name == "Téléphones"

    category.name_en = "Phones"
    category.save(update_fields=["name_en"])
    with override("en"):
        assert category.display_name == "Phones"


def test_attribute_clean_rejects_bad_keys_and_enum_choices():
    category = CategoryFactory()
    definition = AttributeDefinitionFactory(category=category, key="good_key")

    definition.key = "Bad Key"
    with pytest.raises(DjangoValidationError) as exc:
        definition.clean()
    assert "key" in exc.value.message_dict

    definition.key = "good_key"
    definition.type = AttributeDefinition.Type.ENUM
    definition.choices = []
    with pytest.raises(DjangoValidationError) as exc:
        definition.clean()
    assert "choices" in exc.value.message_dict

    definition.choices = [
        {"value": "manual", "label_fr": "Manuelle"},
        {"value": "manual", "label_fr": "Manuelle bis"},
    ]
    with pytest.raises(DjangoValidationError) as exc:
        definition.clean()
    assert "unique" in exc.value.message_dict["choices"][0].lower()

    # Choices on a non-enum attribute are a schema smell, not data.
    definition.type = AttributeDefinition.Type.TEXT
    definition.choices = [{"value": "x"}]
    with pytest.raises(DjangoValidationError) as exc:
        definition.clean()
    assert "choices" in exc.value.message_dict


# ---------------------------------------------------------------------------
# Validation: the six types + strictness rules
# ---------------------------------------------------------------------------
def test_text_rules():
    category = CategoryFactory()
    AttributeDefinitionFactory(category=category, key="colour", type="text")

    assert validate_attributes(category, {"colour": "  red  "}) == {"colour": "red"}
    # Optional left blank stores nothing (0/False are answers; "" is not).
    assert validate_attributes(category, {"colour": ""}) == {}

    with pytest.raises(DjangoValidationError) as exc:
        validate_attributes(category, {"colour": 42})
    assert exc.value.message_dict["colour"] == ["Must be text."]

    with pytest.raises(DjangoValidationError) as exc:
        validate_attributes(category, {"colour": "x" * 256})
    assert "255" in exc.value.message_dict["colour"][0]


def test_number_rules_and_string_coercion():
    category = CategoryFactory()
    AttributeDefinitionFactory(category=category, key="km", type="number")

    assert validate_attributes(category, {"km": 12000}) == {"km": 12000}
    # Numeric strings coerce — forms submit text; "12 000" is not a number.
    assert validate_attributes(category, {"km": "45000"}) == {"km": 45000}
    assert validate_attributes(category, {"km": "45.5"}) == {"km": 45.5}
    assert validate_attributes(category, {"km": 0}) == {"km": 0}

    for bad in ("abc", True, [1]):
        with pytest.raises(DjangoValidationError) as exc:
            validate_attributes(category, {"km": bad})
        assert exc.value.message_dict["km"] == ["Must be a number."]


def test_year_rules():
    category = CategoryFactory()
    AttributeDefinitionFactory(category=category, key="year", type="year")

    assert validate_attributes(category, {"year": 2019}) == {"year": 2019}
    assert validate_attributes(category, {"year": "2020"}) == {"year": 2020}

    for bad, needle in ((1899, "1900"), (2101, "2100"), (2019.5, "1900")):
        with pytest.raises(DjangoValidationError) as exc:
            validate_attributes(category, {"year": bad})
        assert needle in exc.value.message_dict["year"][0]


def test_boolean_is_strictly_a_boolean():
    category = CategoryFactory()
    AttributeDefinitionFactory(category=category, key="negotiable", type="boolean")

    assert validate_attributes(category, {"negotiable": True}) == {"negotiable": True}
    assert validate_attributes(category, {"negotiable": False}) == {"negotiable": False}

    # "true" strings are a client bug we want to *see*, not guess about.
    for bad in ("true", 1, "false"):
        with pytest.raises(DjangoValidationError) as exc:
            validate_attributes(category, {"negotiable": bad})
        assert exc.value.message_dict["negotiable"] == ["Must be true or false."]


def test_enum_rules():
    category = CategoryFactory()
    AttributeDefinitionFactory(
        category=category,
        key="gearbox",
        type="enum",
        choices=[
            {"value": "manual", "label_fr": "Manuelle"},
            {"value": "auto", "label_fr": "Automatique"},
        ],
    )

    assert validate_attributes(category, {"gearbox": "auto"}) == {"gearbox": "auto"}
    with pytest.raises(DjangoValidationError) as exc:
        validate_attributes(category, {"gearbox": "cvt"})
    assert "auto" in exc.value.message_dict["gearbox"][0]


def test_range_rules():
    category = CategoryFactory()
    AttributeDefinitionFactory(category=category, key="budget", type="range")

    assert validate_attributes(category, {"budget": {"min": 100, "max": 200}}) == {
        "budget": {"min": 100, "max": 200}
    }
    # Textual bounds coerce; the pair is what's stored.
    assert validate_attributes(category, {"budget": {"min": "100", "max": "200"}}) == {
        "budget": {"min": 100, "max": 200}
    }

    with pytest.raises(DjangoValidationError) as exc:
        validate_attributes(category, {"budget": {"min": 200, "max": 100}})
    assert "minimum cannot exceed" in exc.value.message_dict["budget"][0]

    for bad in ({"min": 1}, {"min": 1, "max": 2, "step": 3}, [1, 2], "1-2"):
        with pytest.raises(DjangoValidationError) as exc:
            validate_attributes(category, {"budget": bad})
        assert exc.value.message_dict["budget"] == ["Must be a {min, max} pair."]


def test_unknown_keys_missing_required_and_inactive_are_strict():
    category = CategoryFactory(slug="cars")
    AttributeDefinitionFactory(category=category, key="km", type="number", required=True)
    AttributeDefinitionFactory(category=category, key="retired", is_active=False)

    # Unknown key → rejected by name (a typo'd filter key is a bug report).
    with pytest.raises(DjangoValidationError) as exc:
        validate_attributes(category, {"colour": "red"})
    assert exc.value.message_dict["colour"] == ["Unknown attribute for 'cars'."]

    # Inactive definitions are ignored: values under them are unknown *and*
    # turning a field off must not demand keys nobody can supply anymore.
    with pytest.raises(DjangoValidationError) as exc:
        validate_attributes(category, {"retired": "x"})
    assert exc.value.message_dict["retired"] == ["Unknown attribute for 'cars'."]

    # Missing required — the *active* required key, and only it: the inactive
    # ``retired`` definition must not appear in the demand either.
    with pytest.raises(DjangoValidationError) as exc:
        validate_attributes(category, {})
    assert exc.value.message_dict == {"km": ["This attribute is required."]}

    # Both problems at once: every key gets its own message.
    with pytest.raises(DjangoValidationError) as exc:
        validate_attributes(category, {"colour": "red"})
    assert set(exc.value.message_dict) == {"colour", "km"}


def test_validation_without_a_category():
    # Non-empty attributes cannot be checked against nothing.
    with pytest.raises(DjangoValidationError) as exc:
        validate_attributes(None, {"km": 1})
    assert exc.value.messages == ["Attributes require a category to validate against."]

    assert validate_attributes(None, {}) == {}
    assert validate_attributes(None, None) == {}

    with pytest.raises(DjangoValidationError) as exc:
        validate_attributes(CategoryFactory(), ["not", "an", "object"])
    assert exc.value.messages == ["Attributes must be an object."]


def test_valid_attributes_are_cleaned_not_passed_through():
    category = CategoryFactory()
    AttributeDefinitionFactory(category=category, key="km", type="number")
    AttributeDefinitionFactory(category=category, key="colour", type="text")
    AttributeDefinitionFactory(category=category, key="empty_key", type="text")

    cleaned = validate_attributes(
        category, {"km": "12000", "colour": "  blue  ", "empty_key": None}
    )
    # Values are coerced and trimmed; an optional field left blank stores
    # nothing at all — the payload round-trips as the cleaned subset.
    assert cleaned == {"km": 12000, "colour": "blue"}


# ---------------------------------------------------------------------------
# API: the tree endpoint
# ---------------------------------------------------------------------------
def test_tree_endpoint_shape_and_counts(api_client):
    vehicles = CategoryFactory(slug="vehicles", name_fr="Véhicules")
    cars = CategoryFactory(slug="cars", parent=vehicles)
    AttributeDefinitionFactory(
        category=cars, key="brand", type="text", filterable=True, label_fr="Marque"
    )
    ProductFactory(category=cars, is_available=True)
    ProductFactory(category=cars, is_available=False)  # unavailable: not counted
    ProductFactory(category=vehicles, is_available=True)

    response = api_client.get(TREE_URL)

    assert response.status_code == 200
    roots = {node["slug"]: node for node in response.data}
    # Inactive roots never reach the public tree.
    inactive = CategoryFactory(slug="hidden-root", is_active=False)
    assert inactive.slug not in roots

    vehicles_node = roots["vehicles"]
    # product_count covers the whole subtree: cars(1 available) + vehicles(1).
    assert vehicles_node["product_count"] == 2
    assert [child["slug"] for child in vehicles_node["children"]] == ["cars"]
    # Definitions are inlined on the node that owns them (inheritance is
    # applied client-side from the tree — see the serializer docstring).
    assert vehicles_node["attribute_definitions"] == []
    assert [
        definition["key"] for definition in vehicles_node["children"][0]["attribute_definitions"]
    ] == ["brand"]


def test_tree_endpoint_hides_inactive_children_recursively(api_client):
    vehicles = CategoryFactory(slug="vehicles")
    hidden = CategoryFactory(slug="hidden", parent=vehicles, is_active=False)
    CategoryFactory(slug="deep", parent=hidden)

    response = api_client.get(TREE_URL)

    slugs = {node["slug"] for node in response.data}
    assert "vehicles" in slugs
    assert "hidden" not in slugs
    # The whole subtree disappears with its inactive parent.
    body = response.content.decode("utf-8")
    assert "deep" not in body


def test_tree_endpoint_localizes_names_and_labels(api_client):
    vehicles = CategoryFactory(
        slug="vehicles", name_fr="Véhicules", name_ar="مركبات", name_en="Vehicles"
    )
    AttributeDefinitionFactory(
        category=vehicles,
        key="brand",
        label_fr="Marque",
        label_ar="العلامة",
        label_en="Brand",
    )

    english = api_client.get(TREE_URL, HTTP_ACCEPT_LANGUAGE="en")
    arabic = api_client.get(TREE_URL, HTTP_ACCEPT_LANGUAGE="ar")

    assert english.data[0]["name"] == "Vehicles"
    assert english.data[0]["attribute_definitions"][0]["label"] == "Brand"
    assert arabic.data[0]["name"] == "مركبات"
    assert arabic.data[0]["attribute_definitions"][0]["label"] == "العلامة"


def test_tree_endpoint_enums_carry_a_localized_choice_label(api_client):
    CategoryFactory(slug="cars").attribute_definitions.create(
        key="gearbox",
        label_fr="Boîte",
        label_ar="ناقل الحركة",
        type=AttributeDefinition.Type.ENUM,
        choices=[
            {"value": "manual", "label_fr": "Manuelle", "label_ar": "يدوي"},
        ],
    )

    response = api_client.get(TREE_URL, HTTP_ACCEPT_LANGUAGE="fr")
    choice = response.data[0]["attribute_definitions"][0]["choices"][0]

    assert choice["value"] == "manual"
    assert choice["label"] == "Manuelle"
    assert choice["label_ar"] == "يدوي"


# ---------------------------------------------------------------------------
# API: the product write contract
# ---------------------------------------------------------------------------
def product_payload(**overrides):
    payload = {
        "name": "Renault Clio",
        "description": "Bien entretenu, papiers en règle.",
        "base_price": "2500000",
        "attributes_json": {},
    }
    payload.update(overrides)
    return payload


def test_product_create_requires_an_active_category(seller_client):
    # Missing on create: a listing nobody can file is not publishable.
    response = seller_client.post(SELLER_CREATE_URL, product_payload(), format="json")
    assert response.status_code == 400
    assert response.data["code"] == "validation_error"
    assert response.data["details"]["category_id"] == ["A category is required."]

    # Present but inactive: the FK queryset only holds active nodes, so the
    # deactivated subtree is rejected the same way an unknown id is.
    inactive = CategoryFactory(slug="retired", is_active=False)
    response = seller_client.post(
        SELLER_CREATE_URL, product_payload(category_id=inactive.id), format="json"
    )
    assert response.status_code == 400
    assert "category_id" in response.data["details"]


def test_product_create_validates_attributes_per_key(seller_client):
    category = CategoryFactory(slug="cars")
    AttributeDefinitionFactory(category=category, key="km", type="number", required=True)

    response = seller_client.post(
        SELLER_CREATE_URL,
        product_payload(category_id=category.id, attributes_json={"bogus": 1, "km": "lots"}),
        format="json",
    )

    assert response.status_code == 400
    # Per-key messages under ``attributes_json`` — this is what lets the
    # dynamic form highlight the offending inputs by key.
    errors = response.data["details"]["attributes_json"]
    assert errors["bogus"] == ["Unknown attribute for 'cars'."]
    assert errors["km"] == ["Must be a number."]

    # Happy path: cleaned values are stored and echoed back.
    ok = seller_client.post(
        SELLER_CREATE_URL,
        product_payload(category_id=category.id, attributes_json={"km": "45000"}),
        format="json",
    )
    assert ok.status_code == 201
    assert ok.data["attributes_json"] == {"km": 45000}
    assert ok.data["category"]["slug"] == "cars"
    assert ok.data["category"]["name"]  # localized display name, present


def test_product_create_inherits_attributes_from_ancestors(seller_client):
    vehicles = CategoryFactory(slug="vehicles")
    cars = CategoryFactory(slug="cars", parent=vehicles)
    AttributeDefinitionFactory(category=vehicles, key="brand", type="text", required=True)
    AttributeDefinitionFactory(category=cars, key="mileage", type="number")

    # The child form's inherited field is enforced server-side too.
    missing = seller_client.post(
        SELLER_CREATE_URL,
        product_payload(category_id=cars.id, attributes_json={"mileage": 100}),
        format="json",
    )
    assert missing.status_code == 400
    assert missing.data["details"]["attributes_json"]["brand"] == ["This attribute is required."]

    ok = seller_client.post(
        SELLER_CREATE_URL,
        product_payload(category_id=cars.id, attributes_json={"brand": "Renault", "mileage": 100}),
        format="json",
    )
    assert ok.status_code == 201
    assert ok.data["attributes_json"] == {"brand": "Renault", "mileage": 100}


def test_product_update_revalidates_stored_attributes_on_refile(seller_client):
    """Filing a listing into a new category must not leave it carrying keys
    the new subtree never asked for."""
    old = CategoryFactory(slug="old-category")
    new = CategoryFactory(slug="new-category")
    AttributeDefinitionFactory(category=old, key="legacy_key", type="text")
    AttributeDefinitionFactory(category=new, key="fresh_key", type="text", required=True)

    product = ProductFactory(
        store=seller_client.store, category=old, attributes_json={"legacy_key": "kept"}
    )

    # Re-file without touching attributes (PATCH: the other fields stay as
    # they are): stored keys must still validate under the new subtree.
    response = seller_client.patch(
        f"/api/v1/products/seller/{product.id}/",
        {"category_id": new.id},
        format="json",
    )
    assert response.status_code == 400
    assert response.data["details"]["attributes_json"]["fresh_key"] == [
        "This attribute is required."
    ]
    assert response.data["details"]["attributes_json"]["legacy_key"] == [
        "Unknown attribute for 'new-category'."
    ]

    # Same-subtree update leaves the stored attributes alone.
    ok = seller_client.patch(
        f"/api/v1/products/seller/{product.id}/",
        {"attributes_json": {"legacy_key": "changed"}},
        format="json",
    )
    assert ok.status_code == 200
    assert ok.data["attributes_json"] == {"legacy_key": "changed"}


def test_subtree_filter_shows_descendant_products(api_client):
    """``?category=vehicles`` must show the Clio filed under "cars" — the
    sidebar filter is on the parent, the listings are on the children."""
    vehicles = CategoryFactory(slug="vehicles")
    cars = CategoryFactory(slug="cars", parent=vehicles)
    motorcycles = CategoryFactory(slug="motorcycles", parent=vehicles)
    electronics = CategoryFactory(slug="electronics-root")

    ProductFactory(name="Clio", category=cars)
    ProductFactory(name="Jawa", category=motorcycles)
    ProductFactory(name="Laptop", category=electronics)

    response = api_client.get("/api/v1/products/", {"category": "vehicles"})
    assert {product["name"] for product in response.data["results"]} == {"Clio", "Jawa"}

    # Unknown or deactivated slug → empty page, not a 404 (stale bookmarks).
    assert api_client.get("/api/v1/products/", {"category": "no-such"}).data["results"] == []
    CategoryFactory(slug="retired", is_active=False)
    assert api_client.get("/api/v1/products/", {"category": "retired"}).data["results"] == []


def test_category_filter_and_attr_filters_compose(api_client):
    vehicles = CategoryFactory(slug="vehicles")
    AttributeDefinitionFactory(category=vehicles, key="km", type="number", filterable=True)
    cars = CategoryFactory(slug="cars", parent=vehicles)
    ProductFactory(name="Low", category=cars, attributes_json={"km": 5000})
    ProductFactory(name="High", category=cars, attributes_json={"km": 90000})
    ProductFactory(name="Outside", attributes_json={"km": 90000})

    response = api_client.get("/api/v1/products/", {"category": "vehicles", "attr_km_min": 10000})

    assert {product["name"] for product in response.data["results"]} == {"High"}
