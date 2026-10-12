"""Reusable permission classes (Phase 7 of docs/todo.md).

Replaces the ad-hoc ``if not request.user.is_seller`` checks scattered through
the views. Collection-level checks (``has_permission``) run before the view;
object-level checks (``has_object_permission``) run inside ``get_object()`` for
class-based views, so a foreign object can never be mutated even if the
queryset filter is ever loosened.
"""

from rest_framework.permissions import BasePermission


class IsSeller(BasePermission):
    """The user has opted into the seller role."""

    message = "Seller account required."
    #: DRF 3.16 hands this to ``PermissionDenied(code=…)``, so the 403 lands in
    #: the Phase 9 envelope as ``{"code": "seller_required", …}`` instead of
    #: the generic ``permission_denied`` (the sentence alone cannot be
    #: branched on, and it is translated).
    code = "seller_required"

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_seller)


class IsStoreOwner(BasePermission):
    """The user is a seller **and** owns a store.

    For object checks the object may be the ``Store`` itself or anything that
    hangs off one (``Product``, ``Order``, ``Inventory`` via ``.store``).
    """

    message = "You do not own this store."
    #: Same envelope contract as ``IsSeller.code`` — and deliberately *not*
    #: ``store_owner_required``: this code also covers the object-level check
    #: (a store you do not own), which is a "not yours" answer, not a
    #: "you are no seller" one.
    code = "not_store_owner"

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_seller and hasattr(user, "store"))

    def has_object_permission(self, request, view, obj):
        store = getattr(obj, "store", obj)
        owner_id = getattr(store, "owner_id", None)
        return owner_id is not None and owner_id == request.user.pk


class IsListingOwner(IsStoreOwner):
    """Ownership rule for listings/products — semantic alias of
    ``IsStoreOwner`` used at call sites that mutate a listing."""

    message = "You can only modify your own listings."
    #: Distinct from ``IsStoreOwner.code`` so a client can tell "wrong store"
    #: from "wrong listing" without parsing the (translated) message.
    code = "not_listing_owner"
