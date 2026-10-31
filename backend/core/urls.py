from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

# The whole API, mounted once under /api/v1/ (core/versioning.py). Deliberately
# a *literal* segment rather than a `<str:version>` kwarg: DRF hands URL kwargs
# to every view, and ~40 of them are function-based `@api_view`s that would all
# have to accept a `version` argument they never use. The versioning class
# reports "v1" as the default, so `request.version` is still correct.
API_V1_URLPATTERNS = [
    path("auth/", include("apps.users.urls")),
    path("geography/", include("apps.geography.urls")),
    path("catalog/", include("apps.catalog.urls")),
    path("stores/", include("apps.stores.urls")),
    path("media/", include("apps.media.urls")),
    path("products/", include("apps.products.urls")),
    path("inventory/", include("apps.inventory.urls")),
    path("orders/", include("apps.orders.urls")),
    path("payments/", include("apps.payments.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    # Machine-readable docs (Phase 9). They are deliberately *outside* the
    # versioned prefix: the contract for v1 is described by /api/schema/.
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "api/redoc/",
        SpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),
    path("api/v1/", include((API_V1_URLPATTERNS, "v1"))),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
