from django.urls import path

from . import views

urlpatterns = [
    # Public / seller-facing
    path("safety-center/", views.SafetyCenterView.as_view(), name="safety-center"),
    path(
        "sellers/<int:user_id>/reputation/",
        views.SellerReputationView.as_view(),
        name="seller-reputation",
    ),
    path("verification/", views.MyVerificationView.as_view(), name="my-verification"),
    path(
        "store-verification/",
        views.MyStoreVerificationView.as_view(),
        name="my-store-verification",
    ),
    path("appeals/", views.AppealListCreateView.as_view(), name="appeal-list"),
    # Staff moderation
    path("admin/overview/", views.AdminOverviewView.as_view(), name="admin-trust-overview"),
    path(
        "admin/verifications/",
        views.AdminVerificationListView.as_view(),
        name="admin-verification-list",
    ),
    path(
        "admin/verifications/<int:pk>/action/",
        views.AdminVerificationActionView.as_view(),
        name="admin-verification-action",
    ),
    path("admin/reports/", views.AdminReportListView.as_view(), name="admin-report-list"),
    path(
        "admin/reports/<int:pk>/action/",
        views.AdminReportActionView.as_view(),
        name="admin-report-action",
    ),
    path("admin/appeals/", views.AdminAppealListView.as_view(), name="admin-appeal-list"),
    path(
        "admin/appeals/<int:pk>/action/",
        views.AdminAppealActionView.as_view(),
        name="admin-appeal-action",
    ),
    path("admin/blocklist/", views.AdminBlocklistView.as_view(), name="admin-blocklist"),
    path(
        "admin/blocklist/<int:pk>/",
        views.AdminBlocklistDetailView.as_view(),
        name="admin-blocklist-detail",
    ),
    path("admin/mass-action/", views.AdminMassActionView.as_view(), name="admin-mass-action"),
    path("admin/audit/", views.AdminAuditLogView.as_view(), name="admin-audit"),
    path(
        "admin/ban-evasion/",
        views.AdminBanEvasionView.as_view(),
        name="admin-ban-evasion",
    ),
]
