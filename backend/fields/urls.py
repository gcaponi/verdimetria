from rest_framework.routers import DefaultRouter
from django.urls import path

from backend.fields.views import AnalysisJobViewSet, DemoAnalysisView, FieldViewSet

router = DefaultRouter()
router.register("fields", FieldViewSet, basename="field")
router.register("jobs", AnalysisJobViewSet, basename="analysis-job")

urlpatterns = [
    path("demo/", DemoAnalysisView.as_view(), name="demo-analysis"),
    *router.urls,
]
