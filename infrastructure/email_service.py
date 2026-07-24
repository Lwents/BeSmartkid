"""
Email service (infrastructure layer).
Adapter pattern: support multiple backends (SMTP, SendGrid, ...).
Domain/services call EmailService.send() without knowing the backend.
"""

from typing import Any

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
import requests


class BaseEmailBackend:
    """Abstract backend interface."""

    def send(
        self,
        to: str,
        subject: str,
        body: str,
        html_body: str | None = None,
        from_email: str | None = None,
    ) -> None:
        raise NotImplementedError


class SMTPBackend(BaseEmailBackend):
    """Django SMTP backend."""

    def send(
        self,
        to: str,
        subject: str,
        body: str,
        html_body: str | None = None,
        from_email: str | None = None,
    ) -> None:
        sender = from_email or getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com")
        send_mail(
            subject=subject,
            message=body,
            from_email=sender,
            recipient_list=[to],
            fail_silently=False,
            html_message=html_body,
        )


class SendGridBackend(BaseEmailBackend):
    """SendGrid backend via REST API."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def send(
        self,
        to: str,
        subject: str,
        body: str,
        html_body: str | None = None,
        from_email: str | None = None,
    ) -> None:
        sender = from_email or getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com")
        url = "https://api.sendgrid.com/v3/mail/send"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        content = [{"type": "text/plain", "value": body}]
        if html_body:
            content.append({"type": "text/html", "value": html_body})
        data = {
            "personalizations": [{"to": [{"email": to}]}],
            "from": {"email": sender},
            "subject": subject,
            "content": content,
        }
        resp = requests.post(url, headers=headers, json=data)
        if resp.status_code >= 400:
            raise Exception(f"SendGrid error: {resp.text}")


class EmailService:
    """Main adapter that delegates to configured backend."""

    def __init__(self, backend: BaseEmailBackend):
        self.backend = backend

    def send(
        self,
        to: str,
        subject: str,
        body: str,
        html_body: str | None = None,
        from_email: str | None = None,
    ) -> None:
        self.backend.send(to, subject, body, html_body, from_email)


def render_email_template(template_name: str, context: dict[str, Any]) -> str:
    """
    Render a Django template to HTML for email usage.
    """
    return render_to_string(template_name, context)


# --- Factory (choose backend from settings) ---
def get_email_service() -> EmailService:
    backend = getattr(settings, "EMAIL_BACKEND", "smtp")

    if backend == "sendgrid":
        api_key = getattr(settings, "SENDGRID_API_KEY", None)
        if not api_key:
            raise ValueError("SENDGRID_API_KEY must be set in settings")
        return EmailService(SendGridBackend(api_key))

    # default → SMTP
    return EmailService(SMTPBackend())
