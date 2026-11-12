from django.urls import path

from . import views

urlpatterns = [
    path("", views.SearchView.as_view(), name="search"),
    path("suggestions/", views.suggestions, name="search-suggestions"),
    path("recent/", views.RecentSearchesView.as_view(), name="search-recent"),
    path("saved/", views.SavedSearchListCreateView.as_view(), name="saved-search-list"),
    path(
        "saved/<int:pk>/",
        views.SavedSearchDetailView.as_view(),
        name="saved-search-detail",
    ),
]
