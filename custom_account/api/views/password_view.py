# from rest_framework import status
# from rest_framework.response import Response
# from rest_framework.views import APIView
# from django.conf import settings
# from django.core.mail import send_mail
# from django .contrib.auth.hashers import make_password
# from django.contrib.auth.tokens import PasswordResetTokenGenerator
# from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
# from django.utils.encoding import force_bytes, force_str


# from account.models import UserModel

# class ForgotPasswordView(APIView):
#     """API endpoint to request a password reset link via email.

#     User-friendly recovery flow by sending a timed token link.
#     POST body: {"email": "user@example.com"}
#     """

#     def post(self, request):
#         email = request.data.get("email")
#         if not email:
#             return Response({"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)
        
#         try:
#             user_model = UserModel.objects.get(email=email)
#         except UserModel.DoesNotExist:
#             # Security: Don't reveal if email exists (avoids enumeration attacks)
#             return Response({"message": "If the email exists, a reset link has been sent."}, status=status.HTTP_200_OK)
        

#         # Generate secure, timed token 
#         token_generator = PasswordResetTokenGenerator()
#         token = token_generator.make_token(user_model)
#         uid = urlsafe_base64_encode(force_bytes(user_model.pk))

#         # Build reset link (your actual frontend URL)
#         # Example: http://frontend.com/reset-password?uid=uid&token=token
#         reset_link = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"
    
#         # Send email
#         send_mail(
#             subject="Password Reset Request",
#             message=f"Click the link to reset your password: {reset_link}",
#             from_email=settings.DEFAULT_FROM_EMAIL,
#             recipient_list=[email],
#             fail_silently=False,
#         )

#          # Always return success message to avoid email enumeration
#         return Response({"message": "If the email exists, a reset link has been sent."}, status=status.HTTP_200_OK)
    

# class ResetPasswordView(APIView):
#     """API endpoint to confirm and apply a password reset using the provided token.

#     Validates the token and updates the password if valid.
#     POST body: {"uid": "base64_uid", "token": "reset_token", "password": "new_password"}
#     """
#     def post(self, request):
#         uid = request.data.get("uid")
#         token = request.data.get("token")
#         new_password = request.data.get("password")

#         if not (uid and token and new_password):
#             return Response({"error": "uid, token, and password are required"}, status=status.HTTP_400_BAD_REQUEST)
            
#         token_generator = PasswordResetTokenGenerator()

#         try:
#             # Decode uid to get user
#             pk = force_str(urlsafe_base64_decode(uid))
#             user_model = UserModel.objects.get(pk=pk)

#             # Check token validity
#             if token_generator.check_token(user_model, token):
#                 # Hash and update password
#                 user_model.set_password(make_password(new_password))
#                 user_model.save()
#                 return Response({"message": "Password has been reset successfully"}, status=status.HTTP_200_OK)
#             else:
#                 return Response({"error": "Invalid or expired token"}, status=status.HTTP_400_BAD_REQUEST)
#         except (TypeError, ValueError, OverflowError, UserModel.DoesNotExist):
#             return Response({"error": "Invalid link"}, status=status.HTTP_400_BAD_REQUEST)




