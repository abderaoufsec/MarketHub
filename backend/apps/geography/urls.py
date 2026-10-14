from django.urls import path

from . import views

urlpatterns = [
    path("wilayas/", views.WilayaListView.as_view(), name="wilaya-list"),
    path(
        "wilayas/<str:code>/communes/",
        views.CommuneListView.as_view(),
        name="commune-list",
    ),
]
