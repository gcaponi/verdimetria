from rest_framework.routers import DefaultRouter

from backend.fields.views import AnalysisJobViewSet, FieldViewSet

router = DefaultRouter()
router.register("fields", FieldViewSet, basename="field")
router.register("jobs", AnalysisJobViewSet, basename="analysis-job")

urlpatterns = router.urls