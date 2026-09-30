from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from core import views
from core.models import *

router = DefaultRouter()
for url, model in [
    ("teams", Team),
    ("roles", Role),
    ("memberships", Membership),
    ("source-records", SourceRecord),
    ("sync-runs", SyncRun),
    ("access-scopes", AccessScope),
    ("goals", Goal),
    ("skills", Skill),
    ("roadmaps", Roadmap),
    ("requirements", Requirement),
    ("reviews", Review),
    ("approvals", Approval),
    ("audit-events", AuditEvent),
    ("metric-definitions", MetricDefinition),
    ("snapshots", MetricSnapshot),
]:
    router.register(
        url,
        type(model.__name__ + "ViewSet", (views.ResourceViewSet,), {"model": model}),
        basename=url,
    )
for url, view in [
    ("report-jobs", views.ReportJobViewSet),
    ("work-items", views.WorkItemViewSet),
    ("employees", views.EmployeeViewSet),
    ("sources", views.SourceViewSet),
    ("identities", views.IdentityViewSet),
    ("contributions", views.ContributionViewSet),
    ("outcomes", views.OutcomeViewSet),
    ("assessments", views.AssessmentViewSet),
    ("corrections", views.CorrectionViewSet),
]:
    router.register(url, view, basename=url)
urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/session/", views.session),
    path("api/auth/login/", views.login_view),
    path("api/auth/logout/", views.logout_view),
    path("api/setup/", views.setup),
    path("api/health/", views.health),
    path("api/dashboard/", views.dashboard),
    path("api/reports/export/", views.export_report),
    path("api/csv-import/", views.csv_import),
    path("api/retention/", views.retention),
    path("api/", include(router.urls)),
]
