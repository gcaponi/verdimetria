from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError, transaction
from rest_framework import serializers

from backend.accounts.models import User


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = User
        fields = ("id", "email", "password", "first_name", "last_name")
        read_only_fields = ("id",)

    def validate_email(self, value: str) -> str:
        normalized_email = User.objects.normalize_email(value).lower()
        if User.objects.filter(email=normalized_email).exists():
            raise serializers.ValidationError("Esiste gia' un account con questa email")
        return normalized_email

    def create(self, validated_data: dict[str, object]) -> User:
        password = str(validated_data.pop("password"))
        try:
            with transaction.atomic():
                return User.objects.create_user(password=password, **validated_data)
        except IntegrityError as error:
            raise serializers.ValidationError(
                {"email": "Esiste gia' un account con questa email"}
            ) from error