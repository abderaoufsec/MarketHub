from django.urls import path

from . import views

urlpatterns = [
    path("", views.InventoryListView.as_view(), name="inventory-list"),
    path("<int:pk>/", views.InventoryDetailView.as_view(), name="inventory-detail"),
    path(
        "product/<int:product_id>/update/", views.update_product_inventory, name="inventory-update"
    ),
    path("low-stock/", views.low_stock_items, name="inventory-low-stock"),
    path("audit-log/", views.InventoryAuditLogListView.as_view(), name="inventory-audit-log"),
]
