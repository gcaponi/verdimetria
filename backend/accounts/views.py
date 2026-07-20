from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.generics import CreateAPIView
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.accounts.models import User
from backend.accounts.serializers import (
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
)


RESET_REQUEST_DETAIL = (
    "Se l'indirizzo e' associato a un account attivo, riceverai le istruzioni di recupero"
)


class RegisterView(CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = RegisterSerializer


class PasswordResetRequestView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request: Request) -> Response:
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = str(serializer.validated_data["email"])
        user = User.objects.filter(email=email, is_active=True).first()
        response_data: dict[str, object] = {"detail": RESET_REQUEST_DETAIL}

        if user is not None:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            query = urlencode({"reset_uid": uid, "reset_token": token})
            reset_url = f"{settings.FRONTEND_URL.rstrip('/')}?{query}"
            send_mail(
                subject="Recupera la password Verdimetria",
                message=(
                    "Abbiamo ricevuto una richiesta di recupero password.\n"
                    "Se non sei stato tu, ignora questo messaggio.\n\n"
                    f"Imposta una nuova password:\n{reset_url}"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
            )
            if settings.DEBUG:
                response_data["debug"] = {"uid": uid, "token": token}

        return Response(response_data)


class PasswordResetConfirmView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request: Request) -> Response:
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Password aggiornata. Ora puoi accedere."})