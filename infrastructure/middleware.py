import logging
import json
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
                "detail": "Hệ thống đang gặp sự cố, vui lòng thử lại sau",
            }, status=500)


class VietnameseErrorMiddleware:
    """Đổi thông báo lỗi sang tiếng Việt trước khi gửi ra ngoài.

    Bộ xử lý ngoại lệ của DRF chỉ dịch được lỗi phát sinh từ exception. Rất nhiều
    view lại trả thẳng Response({"detail": "Course not found"}, status=404), không
    đi qua đó. Middleware này quét lại phần thân JSON của mọi phản hồi lỗi nên
    không bỏ sót trường hợp nào.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.status_code < 400:
            return response
        if "application/json" not in response.get("Content-Type", ""):
            return response
        if getattr(response, "streaming", False):
            return response

        try:
            from infrastructure.vi_messages import dich_payload
            goc = json.loads(response.content.decode("utf-8"))
            moi = dich_payload(goc)
            if moi != goc:
                response.content = json.dumps(moi, ensure_ascii=False).encode("utf-8")
                response["Content-Length"] = str(len(response.content))
        except Exception:
            # Không dịch được thì trả nguyên phản hồi gốc, không làm hỏng API.
            return response
        return response