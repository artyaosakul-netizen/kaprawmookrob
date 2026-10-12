"""Vercel Serverless Function — Gemini API proxy"""

import json
import os
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler


PRIMARY_MODEL = "gemini-3.8-flash"
FALLBACK_MODEL = "gemini-3.6-flash"

# Retry เฉพาะ error ที่อาจเกิดชั่วคราว
RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


def call_gemini(model, request_data, api_key):
    """Call Gemini API and return (status_code, response_data)."""

    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/{model}:generateContent"
    )

    request = urllib.request.Request(
        url,
        data=json.dumps(request_data).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )

    # สำคัญ: ลดจาก 25 วินาที
    # เพื่อไม่ให้ Vercel function ค้างจนชน 60 วินาที
    with urllib.request.urlopen(request, timeout=10) as response:
        raw = response.read().decode("utf-8")
        data = json.loads(raw)

        return response.status, data


def call_with_retry(model, request_data, api_key):
    """
    เรียก Gemini สูงสุด 2 ครั้ง
    เพื่อไม่ให้ function ใช้เวลานานเกินไป
    """

    last_status = 503
    last_data = {
        "error": {
            "message": "Gemini request failed"
        }
    }

    for attempt in range(2):

        try:
            status, data = call_gemini(
                model,
                request_data,
                api_key
            )

            # สำเร็จ
            if status == 200:
                return status, data

            # Error ที่ไม่ควร retry
            if status not in RETRYABLE_STATUS:
                return status, data

            last_status = status
            last_data = data

        except urllib.error.HTTPError as error:

            last_status = error.code

            try:
                raw = error.read().decode(
                    "utf-8",
                    errors="replace"
                )

                last_data = json.loads(raw)

            except Exception:
                last_data = {
                    "error": {
                        "message": (
                            f"Gemini HTTP error {error.code}"
                        )
                    }
                }

            # เช่น 400, 401, 403 ไม่ต้อง retry
            if error.code not in RETRYABLE_STATUS:
                return last_status, last_data

        except urllib.error.URLError as error:

            last_status = 503

            last_data = {
                "error": {
                    "message": (
                        "Cannot connect to Gemini API",
                        "detail": str(error.reason)[:300]
                    )
                }
            }

        except TimeoutError:

            last_status = 504

            last_data = {
                "error": {
                    "message": "Gemini API request timed out"
                }
            }

        except OSError as error:

            last_status = 503

            last_data = {
                "error": {
                    "message": "Network error",
                    "detail": str(error)[:300]
                }
            }

    return last_status, last_data


class handler(BaseHTTPRequestHandler):

    def do_POST(self):

        try:

            # -----------------------------
            # อ่าน request
            # -----------------------------

            content_length = int(
                self.headers.get(
                    "Content-Length",
                    "0"
                )
            )

            if content_length <= 0:
                self._send_json(
                    400,
                    {
                        "error": {
                            "message":
                            "Request body is empty"
                        }
                    }
                )
                return

            if content_length > 10_000_000:
                self._send_json(
                    400,
                    {
                        "error": {
                            "message":
                            "Request body is too large"
                        }
                    }
                )
                return

            body = self.rfile.read(content_length)

            try:
                request_data = json.loads(body)

            except json.JSONDecodeError:

                self._send_json(
                    400,
                    {
                        "error": {
                            "message":
                            "Invalid JSON request"
                        }
                    }
                )
                return

            # -----------------------------
            # API KEY
            # -----------------------------

            api_key = os.environ.get(
                "GEMINI_API_KEY"
            )

            if not api_key:

                self._send_json(
                    500,
                    {
                        "error": {
                            "message":
                            "GEMINI_API_KEY is not configured"
                        }
                    }
                )
                return

            # -----------------------------
            # Primary model
            # -----------------------------

            status, result = call_with_retry(
                PRIMARY_MODEL,
                request_data,
                api_key
            )

            if status == 200:

                self._send_json(
                    200,
                    result
                )
                return

            # -----------------------------
            # Fallback model
            # -----------------------------

            fallback_status, fallback_result = (
                call_with_retry(
                    FALLBACK_MODEL,
                    request_data,
                    api_key
                )
            )

            if fallback_status == 200:

                self._send_json(
                    200,
                    fallback_result
                )
                return

            # -----------------------------
            # ทั้งสองตัวไม่สำเร็จ
            # -----------------------------

            self._send_json(
                503,
                {
                    "error": {
                        "message":
                        "Both Gemini models failed",

                        "primary": {
                            "model":
                            PRIMARY_MODEL,
                            "status":
                            status,
                            "error":
                            result.get(
                                "error",
                                {}
                            )
                        },

                        "fallback": {
                            "model":
                            FALLBACK_MODEL,
                            "status":
                            fallback_status,
                            "error":
                            fallback_result.get(
                                "error",
                                {}
                            )
                        }
                    }
                }
            )

        except Exception as error:

            self._send_json(
                500,
                {
                    "error": {
                        "message":
                        "Internal server error",

                        "detail":
                        str(error)[:500]
                    }
                }
            )

    def do_OPTIONS(self):

        self.send_response(200)

        self.send_header(
            "Access-Control-Allow-Origin",
            "*"
        )

        self.send_header(
            "Access-Control-Allow-Methods",
            "POST, OPTIONS"
        )

        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type"
        )

        self.end_headers()

    def _send_json(self, status, data):

        body = json.dumps(
            data,
            ensure_ascii=False
        ).encode("utf-8")

        self.send_response(status)

        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8"
        )

        self.send_header(
            "Access-Control-Allow-Origin",
            "*"
        )

        self.send_header(
            "Access-Control-Allow-Methods",
            "POST, OPTIONS"
        )

        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type"
        )

        self.send_header(
            "Content-Length",
            str(len(body))
        )

        self.end_headers()

        self.wfile.write(body)

    def log_message(self, fmt, *args):
        return
