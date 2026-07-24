"""
AI Settings View - Hidden admin endpoint for managing AI configuration
"""
import os
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.conf import settings


class AdminAISettingsView(APIView):
    """
    GET/POST /api/admin/system/ai-settings/
    Hidden endpoint for managing AI API keys and settings
    """
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        """Get current AI settings (keys are masked)"""
        openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
        deepseek_key = os.getenv("DEEPSEEK_API_KEY", "")
        default_model = os.getenv("OPENROUTER_MODEL") or os.getenv("DEEPSEEK_MODEL") or "openai/gpt-4o"
        
        # Get from database if available
        try:
            from django.core.cache import cache
            cached = cache.get("ai_settings")
            if cached:
                return Response({
                    "enabled": cached.get("enabled", True),
                    "openrouter_key": self._mask_key(cached.get("openrouter_key", openrouter_key)),
                    "deepseek_key": self._mask_key(cached.get("deepseek_key", deepseek_key)),
                    "default_model": cached.get("default_model", default_model)
                })
        except Exception:
            pass
        
        return Response({
            "enabled": True,
            "openrouter_key": self._mask_key(openrouter_key),
            "deepseek_key": self._mask_key(deepseek_key),
            "default_model": default_model
        })

    def post(self, request):
        """Update AI settings"""
        enabled = request.data.get("enabled", True)
        openrouter_key = request.data.get("openrouter_key", "")
        deepseek_key = request.data.get("deepseek_key", "")
        default_model = request.data.get("default_model", "openai/gpt-4o")
        
        # Store in cache (or database in production)
        try:
            from django.core.cache import cache
            
            # Don't overwrite if masked key is sent
            current = cache.get("ai_settings") or {}
            
            if openrouter_key and not openrouter_key.startswith("***"):
                current["openrouter_key"] = openrouter_key
                # Also set environment variable for current process
                os.environ["OPENROUTER_API_KEY"] = openrouter_key
            
            if deepseek_key and not deepseek_key.startswith("***"):
                current["deepseek_key"] = deepseek_key
                os.environ["DEEPSEEK_API_KEY"] = deepseek_key
            
            current["enabled"] = enabled
            current["default_model"] = default_model
            
            if default_model:
                os.environ["OPENROUTER_MODEL"] = default_model
            
            cache.set("ai_settings", current, timeout=None)  # Never expire
            
            return Response({"detail": "Đã lưu cài đặt AI"})
        except Exception as e:
            return Response(
                {"detail": f"Lỗi lưu cài đặt: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _mask_key(self, key: str) -> str:
        """Mask API key for display"""
        if not key:
            return ""
        if len(key) <= 8:
            return "***"
        return key[:4] + "***" + key[-4:]
