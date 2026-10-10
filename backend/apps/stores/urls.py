from django.urls import path

from . import views

urlpatterns = [
    # Public endpoints
    path("", views.StoreListView.as_view(), name="store-list"),
    path("<slug:store_slug>/", views.StoreDetailView.as_view(), name="store-detail"),
    # Seller endpoints
    path("seller/create/", views.create_store, name="store-create"),
    path("seller/my-store/", views.my_store, name="my-store"),
    path("seller/stats/", views.store_stats, name="store-stats"),
]
