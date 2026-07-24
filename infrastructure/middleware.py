import logging
import traceback
from django.http import JsonResponse

logger = logging.getLogger(__name__)

class GlobalExceptionMiddleware:
    """Catch all unexpected exceptions at the middleware level."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        except Exception as e:
            logger.error(f"Unhandled exception: {e}\n{traceback.format_exc()}")
            return JsonResponse({
                "error": "Internal Server Error",
                "detail": str(e)
            }, status=500)