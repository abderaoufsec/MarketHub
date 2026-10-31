from django.urls import path

from . import views

urlpatterns = [
    path("images/", views.ImageUploadView.as_view(), name="media-image-list"),
    # Before <int:pk>/ would not collide, but keep the literal routes first
    # so every reader sees them as one block.
    path("images/presign/", views.PresignView.as_view(), name="media-image-presign"),
    path("images/import/", views.ImportView.as_view(), name="media-image-import"),
    path("images/<int:pk>/", views.ImageDetailView.as_view(), name="media-image-detail"),
]
