from django.urls import path

from .views import CategoryTreeView

app_name = "catalog"

urlpatterns = [
    path("categories/", CategoryTreeView.as_view(), name="category-tree"),
]
