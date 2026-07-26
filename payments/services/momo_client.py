import json
import uuid
import hmac
import hashlib
from datetime import timedelta
from typing import Dict, Tuple

import requests
from django.conf import settings
from django.utils import timezone


class MoMoAIOClient:
    """
    Lightweight client for MoMo AIO (All-In-One) payments.
    Handles signature generation/verification and HTTP calls.
    """

    CREATE_ENDPOINT = "https://test-payment.momo.vn/v2/gateway/api/create"
    POS_ENDPOINT = "https://test-payment.momo.vn/v2/gateway/api/pos"
    QUERY_ENDPOINT = "https://test-payment.momo.vn/v2/gateway/api/query"

    def __init__(
        self,
        partner_code: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        endpoint: str | None = None,
    ) -> None:
        self.partner_code = partner_code or settings.MOMO_PARTNER_CODE
        self.access_key = access_key or settings.MOMO_ACCESS_KEY
        self.secret_key = secret_key or settings.MOMO_SECRET_KEY
        self.endpoint = endpoint or getattr(settings, "MOMO_CREATE_ENDPOINT", self.CREATE_ENDPOINT)
        self.pos_endpoint = getattr(settings, "MOMO_POS_ENDPOINT", self.POS_ENDPOINT)
        self.partner_name = getattr(settings, "MOMO_PARTNER_NAME", "SmartKid")
        self.store_id = getattr(settings, "MOMO_STORE_ID", "SmartKidStore")
        self.query_endpoint = getattr(settings, "MOMO_QUERY_ENDPOINT", self.QUERY_ENDPOINT)

        # Validate required credentials
        if not self.partner_code or not self.partner_code.strip():
            raise ValueError("MOMO_PARTNER_CODE is required but not set. Please configure it in environment variables.")
        if not self.access_key or not self.access_key.strip():
            raise ValueError("MOMO_ACCESS_KEY is required but not set. Please configure it in environment variables.")
        if not self.secret_key or not self.secret_key.strip():
            raise ValueError("MOMO_SECRET_KEY is required but not set. Please configure it in environment variables.")

    def _sign(self, raw_data: str) -> str:
        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            raw_data.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return signature

    @staticmethod
    def _build_raw(data: Dict[str, str], order: Tuple[str, ...]) -> str:
        return "&".join(f"{key}={data.get(key, '')}" for key in order)

    def _request(self, url: str, payload: Dict[str, str]) -> Dict[str, str]:
        response_content = None
        try:
            resp = requests.post(url, json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except requests.HTTPError as exc:  # pragma: no cover - IO bound
            response_content = exc.response.text if exc.response is not None else ""
            raise ValueError(f"MoMo request failed: {exc} | {response_content}") from exc
        except requests.RequestException as exc:  # pragma: no cover - IO bound
            raise ValueError(f"MoMo request failed: {exc}") from exc
        except json.JSONDecodeError as exc:  # pragma: no cover - IO bound
            raise ValueError("MoMo returned invalid JSON.") from exc
        if data.get("resultCode") != 0:
            raise ValueError(data.get("message") or "MoMo rejected the request.")
        return data

    def create_payment(
        self,
        amount: int,
        order_id: str,
        order_info: str,
        redirect_url: str,
        ipn_url: str,
        extra_data: str = "",
        request_type: str = "captureWallet",
    ) -> Dict[str, str]:
        """
        Initialize a MoMo payment session.
        Returns MoMo response (payUrl, deeplink, qrCodeUrl, etc.).
        """
        request_id = uuid.uuid4().hex
        payload = {
            "partnerCode": self.partner_code,
            "partnerName": self.partner_name,
            "storeId": self.store_id,
            "accessKey": self.access_key,
            "requestId": request_id,
            "amount": str(int(amount)),
            "orderId": order_id,
            "orderInfo": order_info,
            "redirectUrl": redirect_url,
            "ipnUrl": ipn_url,
            "lang": "vi",
            "extraData": extra_data,
            "requestType": request_type,
            # allow FE to set TTL via env if needed
            "orderExpireTime": int((timezone.now() + timedelta(minutes=15)).timestamp() * 1000),
        }

        raw_signature = self._build_raw(
            payload,
            (
                "accessKey",
                "amount",
                "extraData",
                "ipnUrl",
                "orderId",
                "orderInfo",
                "partnerCode",
                "redirectUrl",
                "requestId",
                "requestType",
            ),
        )
        payload["signature"] = self._sign(raw_signature)

        return self._request(self.endpoint, payload)

    def create_pay_with_method(
        self,
        amount: int,
        order_id: str,
        order_info: str,
        redirect_url: str,
        ipn_url: str,
        extra_data: str = "",
        auto_capture: bool = True,
        lang: str = "vi",
    ) -> Dict[str, str]:
        request_id = uuid.uuid4().hex
        payload = {
            "partnerCode": self.partner_code,
            "partnerName": self.partner_name,
            "storeId": self.store_id,
            "accessKey": self.access_key,
            "requestId": request_id,
            "amount": str(int(amount)),
            "orderId": order_id,
            "orderInfo": order_info,
            "redirectUrl": redirect_url,
            "ipnUrl": ipn_url,
            "requestType": "payWithMethod",
            "lang": lang,
            "extraData": extra_data,
            "autoCapture": auto_capture,
            "orderGroupId": "",
        }
        raw_signature = self._build_raw(
            payload,
            (
                "accessKey",
                "amount",
                "extraData",
                "ipnUrl",
                "orderId",
                "orderInfo",
                "partnerCode",
                "redirectUrl",
                "requestId",
                "requestType",
            ),
        )
        payload["signature"] = self._sign(raw_signature)
        return self._request(self.endpoint, payload)

    def create_pos_payment(
        self,
        amount: int,
        order_id: str,
        order_info: str,
        payment_code: str,
        ipn_url: str,
        extra_data: str = "",
        lang: str = "vi",
    ) -> Dict[str, str]:
        if not payment_code:
            raise ValueError("payment_code is required for MoMo POS flow.")
        request_id = uuid.uuid4().hex
        payload = {
            "partnerCode": self.partner_code,
            "accessKey": self.access_key,
            "requestId": request_id,
            "amount": str(int(amount)),
            "orderId": order_id,
            "orderInfo": order_info,
            "paymentCode": payment_code,
            "lang": lang,
            "ipnUrl": ipn_url,
            "storeId": self.store_id,
            "partnerName": self.partner_name,
            "orderGroupId": "",
            "autoCapture": True,
            "extraData": extra_data,
        }
        raw_signature = self._build_raw(
            payload,
            (
                "accessKey",
                "amount",
                "extraData",
                "orderId",
                "orderInfo",
                "partnerCode",
                "paymentCode",
                "requestId",
            ),
        )
        payload["signature"] = self._sign(raw_signature)
        return self._request(self.pos_endpoint, payload)

    def query_status(self, order_id: str, request_id: str | None = None, lang: str = "vi") -> dict:
        """Query transaction status from MoMo and return response dict."""
        req_id = request_id or uuid.uuid4().hex
        payload = {
            "partnerCode": self.partner_code,
            "accessKey": self.access_key,
            "requestId": req_id,
            "orderId": order_id,
            "lang": lang,
        }
        raw_signature = self._build_raw(
            payload,
            (
                "accessKey",
                "orderId",
                "partnerCode",
                "requestId",
            ),
        )
        payload["signature"] = self._sign(raw_signature)
        return self._request(self.query_endpoint, payload)

    def verify_ipn(self, payload: Dict[str, str]) -> bool:
        """
        Validate IPN signature from MoMo.
        """
        fields = (
            "accessKey",
            "amount",
            "extraData",
            "message",
            "orderId",
            "orderInfo",
            "orderType",
            "partnerCode",
            "payType",
            "requestId",
            "responseTime",
            "resultCode",
            "transId",
        )
        raw_signature = self._build_raw(payload, fields)
        expected = self._sign(raw_signature)
        return expected == payload.get("signature")
