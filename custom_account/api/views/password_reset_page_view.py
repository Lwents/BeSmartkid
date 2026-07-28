from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.shortcuts import render
from django.views.decorators.csrf import csrf_protect

from custom_account.models import UserModel
from custom_account.services import auth_service


def _page_context(email, token, state="form", error=""):
    return {
        "email": email,
        "token": token,
        "state": state,
        "error": error,
    }


@csrf_protect
def password_reset_page(request):
    email = (request.POST.get("email") or request.GET.get("email") or "").strip()
    token = (request.POST.get("token") or request.GET.get("token") or "").strip()

    if not auth_service.is_password_reset_token_valid(email, token):
        return render(
            request,
            "auth/reset_password.html",
            _page_context(email, token, state="invalid"),
            status=400,
        )

    if request.method == "GET":
        return render(request, "auth/reset_password.html", _page_context(email, token))

    new_password = request.POST.get("new_password", "")
    confirm_password = request.POST.get("confirm_password", "")
    if new_password != confirm_password:
        return render(
            request,
            "auth/reset_password.html",
            _page_context(email, token, error="Hai mật khẩu chưa giống nhau."),
            status=400,
        )

    if len(new_password) < 8:
        return render(
            request,
            "auth/reset_password.html",
            _page_context(email, token, error="Mật khẩu phải có ít nhất 8 ký tự."),
            status=400,
        )

    user = UserModel.objects.filter(email=email).first()
    try:
        validate_password(new_password, user=user)
    except ValidationError as exc:
        return render(
            request,
            "auth/reset_password.html",
            _page_context(email, token, error=" ".join(exc.messages)),
            status=400,
        )

    if not auth_service.reset_password_confirm(email, token, new_password):
        return render(
            request,
            "auth/reset_password.html",
            _page_context(email, token, state="invalid"),
            status=400,
        )

    return render(
        request,
        "auth/reset_password.html",
        _page_context(email, "", state="success"),
    )
