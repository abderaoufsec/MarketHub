from django.urls import path

from . import views

urlpatterns = [
    path(
        "conversations/",
        views.ConversationListCreateView.as_view(),
        name="conversation-list",
    ),
    path(
        "conversations/<int:pk>/",
        views.ConversationDetailView.as_view(),
        name="conversation-detail",
    ),
    path(
        "conversations/<int:pk>/messages/",
        views.ConversationMessagesView.as_view(),
        name="conversation-messages",
    ),
    path(
        "conversations/<int:pk>/read/",
        views.ConversationReadView.as_view(),
        name="conversation-read",
    ),
    path(
        "conversations/<int:pk>/offers/",
        views.ConversationOffersView.as_view(),
        name="conversation-offers",
    ),
    path(
        "offers/<int:pk>/<str:action>/",
        views.OfferActionView.as_view(),
        name="offer-action",
    ),
    path("users/<int:pk>/block/", views.BlockUserView.as_view(), name="user-block"),
    path("blocks/", views.BlockListView.as_view(), name="block-list"),
    path("reports/", views.ReportCreateView.as_view(), name="report-create"),
    path("unread-count/", views.UnreadCountView.as_view(), name="unread-count"),
]
