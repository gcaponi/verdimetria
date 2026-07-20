from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
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


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value: str) -> str:
        return User.objects.normalize_email(value).lower()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        try:
            user_id = force_str(urlsafe_base64_decode(str(attrs["uid"])))
            user = User.objects.get(pk=user_id, is_active=True)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None

        if user is None or not default_token_generator.check_token(user, str(attrs["token"])):
            raise serializers.ValidationError(
                {"token": "Il link di recupero non e' valido o e' scaduto"}
            )

        try:
            validate_password(str(attrs["new_password"]), user=user)
        except DjangoValidationError as error:
            raise serializers.ValidationError({"new_password": error.messages}) from error
        attrs["user"] = user
        return attrs

    def save(self, **kwargs: object) -> User:
        user = self.validated_data["user"]
        if not isinstance(user, User):
            raise RuntimeError("Utente reset password non disponibile")
        user.set_password(str(self.validated_data["new_password"]))
        user.save(update_fields=["password"])
        return user