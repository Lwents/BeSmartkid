# from django.apps import AppConfig


# class AiPersonalizationConfig(AppConfig):
#     default_auto_field = 'django.db.models.BigAutoField'
#     name = 'ai_personalization'


# ai_personalization/apps.py
"""
App configuration for ai_personalization module.
"""
from django.apps import AppConfig


class AiPersonalizationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ai_personalization'
    verbose_name = 'AI Personalization'
    
    def ready(self):
        """Import signals when app is ready."""
        import ai_personalization.signals  # noqa
