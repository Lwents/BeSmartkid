from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken


class SafeLogoutView(APIView):
    """Blacklist a refresh token without turning malformed input into HTTP 500."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        raw_token = request.data.get("refresh")
        if not raw_token:
            return Response(
                {"detail": "Vui lòng gửi refresh token."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            RefreshToken(raw_token).blacklist()
        except TokenError:
            return Response(
                {"detail": "Phiên đăng nhập không hợp lệ hoặc đã hết hạn."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)
