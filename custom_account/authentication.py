from rest_framework_simplejwt.authentication import JWTAuthentication

from custom_account.services.session_tracking import touch_presence


class PresenceTrackingJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)
        if result:
            user, _token = result
            try:
                touch_presence(user=user, request=request)
            except Exception:
                # Presence tracking must never prevent a valid API request.
                pass
        return result
