"""
URL configuration for backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.http import Http404, HttpResponse
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from dj_rest_auth.jwt_auth import get_refresh_view
import mimetypes
import os
import re

from custom_account.api.views.auth_view import GoogleLogin



def home(request):
    return HttpResponse("Welcome to my SunnyEdu backend!")


def media_stream(request, path):
    """
    Serve media files with HTTP Range support so HTML5 video can seek.
    """
    full_path = os.path.join(settings.MEDIA_ROOT, path)
    if not os.path.exists(full_path) or not os.path.isfile(full_path):
        raise Http404("File not found")

    file_size = os.path.getsize(full_path)
    content_type, _ = mimetypes.guess_type(full_path)
    content_type = content_type or "application/octet-stream"

    range_header = request.headers.get("Range") or request.META.get("HTTP_RANGE")
    if not range_header:
        resp = HttpResponse(open(full_path, "rb"), content_type=content_type)
        resp["Content-Length"] = str(file_size)
        resp["Accept-Ranges"] = "bytes"
        return resp

    range_match = re.match(r"bytes=(\d+)-(\d*)", range_header)
    if not range_match:
        # Malformed Range header: fallback to full file
        resp = HttpResponse(open(full_path, "rb"), content_type=content_type)
        resp["Content-Length"] = str(file_size)
        resp["Accept-Ranges"] = "bytes"
        return resp

    start = int(range_match.group(1))
    end = range_match.group(2)
    end = int(end) if end else file_size - 1
    end = min(end, file_size - 1)

    if start > end or start >= file_size:
        raise Http404("Invalid range")

    chunk_length = end - start + 1
    with open(full_path, "rb") as f:
        f.seek(start)
        data = f.read(chunk_length)

    resp = HttpResponse(data, status=206, content_type=content_type)
    resp["Content-Length"] = str(chunk_length)
    resp["Content-Range"] = f"bytes {start}-{end}/{file_size}"
    resp["Accept-Ranges"] = "bytes"
    return resp

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/account/', include("custom_account.urls")),
    path('api/ai_personalization/', include('ai_personalization.urls')),
    path('api/payments/', include('payments.urls')),
    path('api/content/', include('content.urls')),
    path('api/activities/', include('activities.urls')),
    path('api/events/', include('events.api.urls')),
    # path('api/assignments/', include('assignments.urls')),  # Temporarily disabled - import errors
    path('api/admin/', include('admin_api.urls')),
    path('api/teacher/', include('teacher_api.urls')),
    path('api/student/', include('student_api.urls')),
    path('api/media/stream/<path:path>', media_stream, name='media-stream'),
    path("", home),

    path("api/auth/", include("dj_rest_auth.urls")),
    path('api/auth/', include('allauth.socialaccount.urls')),
    path('api/auth/google/', GoogleLogin.as_view(), name='google_login'),

    path('api/auth/token/refresh/', get_refresh_view().as_view(), name='token_refresh'),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
