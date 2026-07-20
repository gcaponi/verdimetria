from rest_framework.routers import DefaultRouter

from backend.fields.views import FieldViewSet

router = DefaultRouter()
router.register("fields", FieldViewSet, basename="field")

urlpatterns = router.urls