from typing import Any

from django.db.models import QuerySet
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from backend.fields.models import Field
from backend.fields.serializers import (
    BoundaryCreateSerializer,
    BoundaryVersionSerializer,
    FieldSerializer,
)


class FieldViewSet(viewsets.ModelViewSet):
    serializer_class = FieldSerializer
    http_method_names = ("get", "post", "head", "options")

    def get_queryset(self) -> QuerySet[Field]:
        if self.request.user.is_anonymous:
            return Field.objects.none()
        return Field.objects.filter(owner=self.request.user).prefetch_related("boundaries")

    @action(detail=True, methods=("post",), url_path="boundaries")
    def create_boundary(self, request: Request, **kwargs: Any) -> Response:
        field = self.get_object()
        serializer = BoundaryCreateSerializer(
            data=request.data,
            context={"request": request, "field": field},
        )
        serializer.is_valid(raise_exception=True)
        boundary = serializer.save()
        return Response(BoundaryVersionSerializer(boundary).data, status=status.HTTP_201_CREATED)