from rest_framework.routers import DefaultRouter
from django.urls import path

from backend.fields.views import (
    AnalysisJobViewSet,
    DemoAnalysisView,
    FieldViewSet,
    InterventionViewSet,
    JobReportView,
)

router = DefaultRouter()
router.register("fields", FieldViewSet, basename="field")
router.register("jobs", AnalysisJobViewSet, basename="analysis-job")
router.register("interventions", InterventionViewSet, basename="intervention")

urlpatterns = [
    path("demo/", DemoAnalysisView.as_view(), name="demo-analysis"),
    path("jobs/<uuid:job_id>/report.pdf", JobReportView.as_view(), name="analysis-job-report"),
    *router.urls,
]
